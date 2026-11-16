import csv
import os

from engine.change_manager import ChangeManager
from engine.constraint_checker import ConstraintChecker
from engine.hall_allocator import HallAllocator
from engine.invigilator_allocator import InvigilatorAllocator
from engine.models import Violation
from engine.scheduler import ExamScheduler
from engine.seating_engine import SeatingEngine
from engine.time_utils import exam_end_time


class PS067Runner:
    """Executes the official pipe-delimited command stream and writes snapshots."""

    TIMETABLE_FIELDS = [
        "snapshot", "course_code", "date", "session", "start_time", "end_time",
        "students",
    ]
    HALL_PLAN_FIELDS = [
        "date", "session", "hall_id", "seat_no", "row", "column", "register_no",
        "course_code", "extra_minutes",
    ]
    ROSTER_FIELDS = [
        "date", "session", "hall_id", "invigilator_id", "role",
    ]
    VIOLATION_FIELDS = [
        "snapshot", "type", "course_code", "register_no", "date", "session",
        "detail",
    ]
    CHANGE_FIELDS = ["line_no", "command", "status", "detail"]
    CHANGE_COMMANDS = {"POSTPONE", "HALL_UNAVAILABLE", "LATE_REGISTER"}

    def __init__(self, data, output_dir):
        self.data = data
        self.output_dir = output_dir
        self.assignments = []
        self.hall_assignments = []
        self.roster = []
        self.schedule_violations = []
        self.allocation_violations = []
        self.runner_violations = []
        self.change_manager = None
        self.unavailable_halls = set()
        self.timetable_rows = []
        self.hall_plan_rows = []
        self.roster_rows = []
        self.violation_rows = []
        self.change_rows = []
        self.timetable_snapshot = 0
        self.violation_snapshot = 0
        self.generated = False
        self.allocated = False
        self.assigned_invigilators = False

    def process_file(self, path):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Command file not found: {path}")
        with open(path, encoding="utf-8-sig") as handle:
            lines = handle.readlines()

        for line_no, raw_line in enumerate(lines, 1):
            text = raw_line.strip()
            if not text or text.startswith("#"):
                continue
            parts = [part.strip() for part in text.split("|")]
            command, args = parts[0].upper(), parts[1:]
            if command in self.CHANGE_COMMANDS:
                self._process_change(line_no, command, args)
            else:
                self._process_operation(command, args)

        self._write_outputs()
        return self.change_rows

    def _process_operation(self, command, args):
        if command == "GENERATE_TIMETABLE":
            self._generate_timetable(args)
        elif command == "ALLOCATE_HALLS":
            self._allocate_halls()
        elif command == "ASSIGN_INVIGILATORS":
            self._assign_invigilators()
        elif command == "PRINT_TIMETABLE":
            self._print_timetable()
        elif command == "PRINT_VIOLATIONS":
            self._print_violations()
        elif command == "PRINT_HALL_PLAN":
            self._print_hall_plan(args)
        elif command == "PRINT_ROSTER":
            self._print_roster()
        else:
            raise ValueError(f"Unsupported command: {command}")

    def _generate_timetable(self, args):
        if len(args) != 2 or not all(args):
            raise ValueError("GENERATE_TIMETABLE requires from_date and to_date")
        start_date, end_date = args
        if start_date > end_date:
            raise ValueError("GENERATE_TIMETABLE from_date must not exceed to_date")
        self.data["exam_window"] = [
            row for row in self.data["exam_window"]
            if start_date <= row["date"] <= end_date
        ]
        self.schedule_violations = []
        scheduler = ExamScheduler(self.data)
        self.assignments = scheduler.generate()
        self.schedule_violations = list(scheduler.violations)
        self.generated = True
        self.allocated = False
        self.assigned_invigilators = False
        self.change_manager = None

    def _allocate_halls(self):
        self._require_generated("ALLOCATE_HALLS")
        allocator = HallAllocator(self.data)
        self.hall_assignments = allocator.allocate(
            self.assignments, self.unavailable_halls
        )
        self.allocation_violations = list(allocator.violations)
        self.allocated = True
        self.assigned_invigilators = False

    def _assign_invigilators(self):
        if not self.allocated:
            raise ValueError("ASSIGN_INVIGILATORS requires ALLOCATE_HALLS first")
        allocator = InvigilatorAllocator(self.data)
        self.roster = allocator.allocate(self.hall_assignments)
        self.runner_violations = list(allocator.violations)
        self.assigned_invigilators = True
        self.change_manager = ChangeManager(
            self.data,
            self.assignments,
            self.hall_assignments,
            self.roster,
            unavailable_halls=self.unavailable_halls,
        )

    def _process_change(self, line_no, command, args):
        if self.change_manager is None:
            raise ValueError(
                f"{command} on line {line_no} requires timetable, halls and "
                "invigilators to be initialized"
            )
        detail = ""
        try:
            if command == "POSTPONE":
                if len(args) < 1 or not args[0]:
                    raise ValueError("POSTPONE requires a course_code")
                result = self.change_manager.postpone(args[0])
            elif command == "HALL_UNAVAILABLE":
                if len(args) < 3 or not all(args[:3]):
                    raise ValueError(
                        "HALL_UNAVAILABLE requires hall_id, date and session"
                    )
                result = self.change_manager.mark_hall_unavailable(
                    args[0], args[1], args[2].upper()
                )
            else:
                if len(args) != 2 or not all(args):
                    raise ValueError(
                        "LATE_REGISTER requires register_no and course_code"
                    )
                student = self.data["student_by_id"].get(args[0])
                if student is None:
                    result = {
                        "status": "REJECTED_UNKNOWN_STUDENT",
                        "student_id": args[0],
                    }
                else:
                    result = self.change_manager.add_late_registrant(
                        student, args[1]
                    )
            status = str(result.get("status", "PROCESSED"))
            accepted = not status.startswith("REJECTED")
            detail = self._change_detail(result)
            if accepted:
                self._sync_manager()
            elif status == "REJECTED_CLASH":
                self.runner_violations.append({
                    "rule_id": "BR-11",
                    "severity": "HARD",
                    "entity": result.get("student_id", ""),
                    "message": (
                        "REJECTED_CLASH: " + ", ".join(
                            result.get("course_codes", [])
                        )
                    ),
                    "type": "REJECTED_CLASH",
                    "course_code": args[-1],
                    "register_no": result.get("student_id", ""),
                })
            self.change_rows.append({
                "line_no": line_no,
                "command": command,
                "status": "OK" if accepted else "REJECTED",
                "detail": detail,
            })
        except (ValueError, KeyError, IndexError) as exc:
            self.change_rows.append({
                "line_no": line_no,
                "command": command,
                "status": "REJECTED",
                "detail": str(exc),
            })

    @staticmethod
    def _change_detail(result):
        status = result.get("status", "PROCESSED")
        if status == "POSTPONED":
            old_date, old_session = result["from"]
            new_date, new_session = result["to"]
            return (
                f"{result['course_code']} moved from {old_date} {old_session} "
                f"to {new_date} {new_session}"
            )
        if status == "HALL_MARKED_UNAVAILABLE":
            return (
                f"{result['hall_id']} unavailable on {result['date']} "
                f"{result['session']}"
            )
        if status == "ADDED":
            return (
                f"{result['student_id']} added to {result['course_code']} "
                f"in {result['hall_id']}"
            )
        details = [
            f"{key}={value}" for key, value in sorted(result.items())
            if key != "status"
        ]
        return f"{status}: " + "; ".join(details)

    def _sync_manager(self):
        self.assignments = self.change_manager.assignments
        self.hall_assignments = self.change_manager.hall_assignments
        self.roster = self.change_manager.roster
        self.unavailable_halls = self.change_manager.unavailable_halls
        self.runner_violations.extend(self.change_manager.violations)

    def _print_timetable(self):
        self._require_generated("PRINT_TIMETABLE")
        self.timetable_snapshot += 1
        by_code = {assignment.course_code: assignment for assignment in self.assignments}
        window = {
            (row["date"], row["session"]): row for row in self.data["exam_window"]
        }
        snapshot_rows = []
        for course in self.data["courses"]:
            code = course["course_code"]
            assignment = by_code.get(code)
            if assignment is None:
                row = {
                    "snapshot": self.timetable_snapshot,
                    "course_code": code,
                    "date": "",
                    "session": "",
                    "start_time": "",
                    "end_time": "",
                    "students": len(self.data["course_students"].get(code, [])),
                }
            else:
                slot = window[(assignment.date, assignment.session)]
                row = {
                    "snapshot": self.timetable_snapshot,
                    "course_code": code,
                    "date": assignment.date,
                    "session": assignment.session,
                    "start_time": slot["start_time"],
                    "end_time": exam_end_time(
                        self.data, assignment.date, assignment.session,
                        assignment.duration,
                    ),
                    "students": len(assignment.students),
                }
            snapshot_rows.append(row)
        snapshot_rows.sort(key=lambda row: (
            row["date"] == "",
            row["date"],
            0 if row["session"] == "FN" else 1,
            row["course_code"],
        ))
        self.timetable_rows.extend(snapshot_rows)

    def _print_hall_plan(self, args):
        if not self.allocated:
            raise ValueError("PRINT_HALL_PLAN requires ALLOCATE_HALLS first")
        if len(args) != 2 or not all(args):
            raise ValueError("PRINT_HALL_PLAN requires date and session")
        exam_date, session = args[0], args[1].upper()
        plan = SeatingEngine(self.data).create_seating_plan(
            self.hall_assignments
        )
        rows = []
        for seat in plan:
            if (
                seat["date"] != exam_date
                or seat["session"] != session
                or seat["status"] != "ASSIGNED"
            ):
                continue
            student = self.data["student_by_id"][seat["student_id"]]
            rows.append({
                "date": exam_date,
                "session": session,
                "hall_id": seat["hall_id"],
                "seat_no": f"{seat['hall_id']}-{int(seat['seat_number']):03d}",
                "row": seat["row"],
                "column": seat["column"],
                "register_no": student["register_number"],
                "course_code": seat["course_code"],
                "extra_minutes": (
                    20 if str(student.get("special_needs", "NO")).upper() == "YES"
                    else 0
                ),
            })
        rows.sort(key=lambda row: (
            row["hall_id"], int(row["row"]), int(row["column"]),
            row["register_no"],
        ))
        self.hall_plan_rows.extend(rows)

    def _print_roster(self):
        if not self.assigned_invigilators:
            raise ValueError("PRINT_ROSTER requires ASSIGN_INVIGILATORS first")
        self.roster_rows = [
            {
                "date": row["date"],
                "session": row["session"],
                "hall_id": row["hall_id"],
                "invigilator_id": row["invigilator_id"],
                "role": row["role"],
            }
            for row in self.roster
            if row.get("status") == "ASSIGNED" and row.get("invigilator_id")
        ]
        self.roster_rows.sort(key=lambda row: (
            row["date"], 0 if row["session"] == "FN" else 1,
            row["hall_id"], row["role"], row["invigilator_id"],
        ))

    def _print_violations(self):
        self._require_generated("PRINT_VIOLATIONS")
        self.violation_snapshot += 1
        rows = self._current_violations()
        for row in rows:
            self.violation_rows.append({
                "snapshot": self.violation_snapshot,
                "type": row["type"],
                "course_code": row.get("course_code", ""),
                "register_no": row.get("register_no", ""),
                "date": row.get("date", ""),
                "session": row.get("session", ""),
                "detail": row.get("detail", ""),
            })

    def _current_violations(self):
        rows = []
        for violation in (
            list(self.schedule_violations)
            + list(self.allocation_violations)
            + list(self.runner_violations)
        ):
            if isinstance(violation, Violation):
                violation = violation.__dict__
            rule_id = violation.get("rule_id", "")
            message = violation.get("message", "")
            explicit_type = violation.get("type")
            if explicit_type:
                violation_type = explicit_type
            elif rule_id == "BR-02" or violation.get("severity") == "SOFT":
                violation_type = "SOFT_VIOLATION"
            elif "UNSTAFFED" in message or rule_id == "BR-08":
                violation_type = "UNSTAFFED"
            elif rule_id == "BR-10" or rule_id in ("BR-05", "BR-06"):
                violation_type = "MOVED_CAPACITY"
            else:
                continue
            entity = str(violation.get("entity", ""))
            rows.append({
                "type": violation_type,
                "course_code": violation.get(
                    "course_code",
                    entity if entity in self.data["course_by_code"] else "",
                ),
                "register_no": violation.get(
                    "register_no",
                    entity if entity in self.data["student_by_id"] else "",
                ),
                "date": violation.get("date", ""),
                "session": violation.get("session", ""),
                "detail": message,
            })

        rows.extend(self._consent_double_days())
        rows.sort(key=lambda row: (
            row["type"], row.get("date", ""), row.get("session", ""),
            row.get("course_code", ""), row.get("register_no", ""),
            row.get("detail", ""),
        ))
        return rows

    def _consent_double_days(self):
        exams_by_student_day = {}
        checker = ConstraintChecker(self.data)
        for assignment in self.assignments:
            for student_id in assignment.students:
                exams_by_student_day.setdefault(
                    (student_id, assignment.date), []
                ).append(assignment)
        rows = []
        for (student_id, exam_date), exams in exams_by_student_day.items():
            if len(exams) < 2:
                continue
            student = self.data["student_by_id"].get(student_id, {})
            if str(student.get("backlog_consent", "NO")).upper() != "YES":
                continue
            has_backlog = any(
                checker._is_backlog_for_student(
                    student_id, exam.course_code
                )
                for exam in exams
            )
            sessions = {exam.session for exam in exams}
            if not has_backlog or len(sessions) != len(exams):
                continue
            codes = sorted(exam.course_code for exam in exams)
            rows.append({
                "type": "CONSENT_DOUBLE_DAY",
                "course_code": "|".join(codes),
                "register_no": student_id,
                "date": exam_date,
                "session": "|".join(sorted(sessions)),
                "detail": (
                    "BACKLOG_CONSENT permits multiple exams in separate sessions: "
                    + ", ".join(codes)
                ),
            })
        return rows

    def _require_generated(self, command):
        if not self.generated:
            raise ValueError(f"{command} requires GENERATE_TIMETABLE first")

    def _write_outputs(self):
        os.makedirs(self.output_dir, exist_ok=True)
        self._write_csv("timetable.csv", self.timetable_rows, self.TIMETABLE_FIELDS)
        self._write_csv("hall_plan.csv", self.hall_plan_rows, self.HALL_PLAN_FIELDS)
        self._write_csv("roster.csv", self.roster_rows, self.ROSTER_FIELDS)
        self._write_csv("violations.csv", self.violation_rows, self.VIOLATION_FIELDS)
        self._write_csv("change_results.csv", self.change_rows, self.CHANGE_FIELDS)

    def _write_csv(self, filename, rows, fields):
        path = os.path.join(self.output_dir, filename)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path
