from dataclasses import replace

from .constraint_checker import ConstraintChecker
from .hall_allocator import HallAllocator, make_hall_assignment, pack_courses
from .incremental_scheduler import IncrementalScheduler
from .invigilator_allocator import InvigilatorAllocator
from .seating_engine import SeatingEngine
from .time_utils import exam_end_time


class ChangeManager:
    """Applies changes and rebuilds only the affected sessions."""

    def __init__(self, data, assignments, hall_assignments=None, roster=None,
                 unavailable_halls=None):
        self.data = data
        self.assignments = assignments
        self.hall_assignments = list(hall_assignments or [])
        self.roster = list(roster or [])
        self.unavailable_halls = set(unavailable_halls or ())
        self.violations = []

    def _session_halls(self, date, session):
        return [
            h for h in self.data["halls"]
            if str(h.get("available", "YES")).strip().upper()
            in ("YES", "TRUE", "1")
            and (h["hall_id"], date, session) not in self.unavailable_halls
        ]

    def _rebuild_sessions(self, affected):
        affected = set(affected)
        if not affected:
            return

        retained_halls = [
            h for h in self.hall_assignments
            if (h.date, h.session) not in affected
        ]
        affected_assignments = [
            a for a in self.assignments
            if (a.date, a.session) in affected
        ]

        allocator = HallAllocator(self.data)
        rebuilt = allocator.allocate(affected_assignments, self.unavailable_halls)
        self.hall_assignments = retained_halls + rebuilt
        self.violations.extend(allocator.violations)

        # Rebuild only affected roster rows. Existing roster rows in other
        # sessions are retained. Import locally to avoid unnecessary dependency.
        from .invigilator_allocator import InvigilatorAllocator
        inv_allocator = InvigilatorAllocator(self.data)
        self.roster = inv_allocator.allocate_incremental(
            self.hall_assignments, self.roster, affected
        )
        self.violations.extend(inv_allocator.violations)

    def postpone(self, course_code, target_date=None, target_session=None):
        current = next((a for a in self.assignments if a.course_code == course_code), None)
        if current is None:
            return {"status": "REJECTED_UNKNOWN_COURSE", "course_code": course_code}

        old = replace(current)
        course = self.data["course_by_code"][course_code]
        remaining = [a for a in self.assignments if a.course_code != course_code]
        checker = ConstraintChecker(self.data)
        checker.clear_and_rebuild(remaining)

        slots = sorted(
            [
                row for row in self.data["exam_window"]
                if str(row.get("available", "")).strip().upper() in ("YES", "TRUE", "1")
                and (row["date"], 0 if row["session"] == "FN" else 1)
                > (current.date, 0 if current.session == "FN" else 1)
            ],
            key=lambda row: (row["date"], 0 if row["session"] == "FN" else 1)
        )
        if target_date:
            slots = [s for s in slots if s["date"] >= target_date]
        if target_session:
            slots = [s for s in slots if s["session"] == target_session]

        backlog = str(course.get("exam_type", "REGULAR")).upper() == "BACKLOG"
        calendar_dates = sorted({r["date"] for r in self.data["exam_window"]})
        final_three = set(calendar_dates[-3:])

        selected = None
        soft_fallback = None
        for slot in slots:
            if backlog and not (
                slot["date"] in final_three
                and (slot["session"] == "AN" or (len(current.students) > 50 and slot["session"] == "FN"))
            ):
                continue

            candidate = replace(current, date=slot["date"], session=slot["session"])
            ok, soft, _ = checker.can_assign(
                course, slot["date"], slot["session"], remaining
            )
            if not ok:
                ok, soft, _ = checker.can_assign(
                    course, slot["date"], slot["session"], remaining,
                    allow_gap_violation=True
                )
                if not ok or not soft:
                    continue

            session_assignments = [
                a for a in remaining
                if (a.date, a.session) == (slot["date"], slot["session"])
            ] + [candidate]
            halls = self._session_halls(slot["date"], slot["session"])
            capacity = int(sum(int(h["capacity"]) for h in halls) * 0.90)
            if sum(len(a.students) for a in session_assignments) > capacity:
                continue
            if not pack_courses(self.data, session_assignments, self.data["halls"], self.unavailable_halls):
                continue

            if soft:
                if soft_fallback is None:
                    soft_fallback = (slot, soft)
            else:
                selected = (slot, soft)
                break

        if selected is None:
            selected = soft_fallback
        if selected is None:
            return {"status": "REJECTED_NO_VALID_LATER_SESSION", "course_code": course_code}

        slot, soft = selected
        current.date = slot["date"]
        current.session = slot["session"]
        current.soft_violations = list(soft)
        affected = IncrementalScheduler.affected_sessions(old, current)
        self._rebuild_sessions(affected)
        return {
            "status": "POSTPONED",
            "course_code": course_code,
            "from": [old.date, old.session],
            "to": [current.date, current.session],
            "affected_sessions": sorted(affected),
        }

    def mark_hall_unavailable(self, hall_id, date, session="ALL"):
        if hall_id not in self.data["hall_by_id"]:
            return {"status": "REJECTED_UNKNOWN_HALL", "hall_id": hall_id}

        sessions = {
            row["session"] for row in self.data["exam_window"]
            if row["date"] == date
            and str(row.get("available", "")).strip().upper() in ("YES", "TRUE", "1")
        }
        if session != "ALL":
            sessions = {session}
        affected = {(date, s) for s in sessions}
        if not affected:
            return {"status": "REJECTED_NO_AVAILABLE_SESSION", "hall_id": hall_id}

        for exam_date, exam_session in affected:
            self.unavailable_halls.add((hall_id, exam_date, exam_session))

        # If the session no longer fits, move the smallest course(s) to later
        # feasible sessions before rebuilding halls.
        for exam_date, exam_session in sorted(affected):
            session_assignments = [
                a for a in self.assignments
                if (a.date, a.session) == (exam_date, exam_session)
            ]
            while session_assignments and not self._session_fits(
                exam_date, exam_session, session_assignments
            ):
                movable = sorted(
                    session_assignments,
                    key=lambda a: (len(a.students), a.course_code)
                )
                moved = False
                for candidate in movable:
                    course = self.data["course_by_code"][candidate.course_code]
                    remaining = [a for a in self.assignments if a is not candidate]
                    new_slot = self._find_later_slot(candidate, course, remaining)
                    if new_slot:
                        old_date, old_session = candidate.date, candidate.session
                        candidate.date, candidate.session = new_slot
                        self.violations.append({
                            "rule_id": "BR-10",
                            "severity": "WARNING",
                            "entity": candidate.course_code,
                            "message": (
                                f"Moved from {old_date} {old_session} to "
                                f"{new_slot[0]} {new_slot[1]} after hall closure"
                            ),
                        })
                        affected.add((old_date, old_session))
                        affected.add(new_slot)
                        moved = True
                        break
                if not moved:
                    self.violations.append({
                        "rule_id": "BR-10",
                        "severity": "HARD",
                        "entity": f"{exam_date} {exam_session}",
                        "message": "Session exceeds available hall capacity after hall closure",
                    })
                    break
                session_assignments = [
                    a for a in self.assignments
                    if (a.date, a.session) == (exam_date, exam_session)
                ]

        self._rebuild_sessions(affected)
        return {
            "status": "HALL_MARKED_UNAVAILABLE",
            "hall_id": hall_id,
            "date": date,
            "session": session,
            "affected_sessions": sorted(affected),
        }

    def _session_fits(self, date, session, assignments):
        halls = self._session_halls(date, session)
        total_capacity = int(sum(int(h["capacity"]) for h in halls) * 0.90)
        if sum(len(a.students) for a in assignments) > total_capacity:
            return False
        return pack_courses(self.data, assignments, self.data["halls"], self.unavailable_halls)

    def _find_later_slot(self, assignment, course, remaining):
        checker = ConstraintChecker(self.data)
        checker.clear_and_rebuild(remaining)
        slots = sorted(
            [
                row for row in self.data["exam_window"]
                if str(row.get("available", "")).strip().upper() in ("YES", "TRUE", "1")
                and (row["date"], 0 if row["session"] == "FN" else 1)
                > (assignment.date, 0 if assignment.session == "FN" else 1)
            ],
            key=lambda row: (row["date"], 0 if row["session"] == "FN" else 1)
        )
        backlog = str(course.get("exam_type", "REGULAR")).upper() == "BACKLOG"
        calendar_dates = sorted({r["date"] for r in self.data["exam_window"]})
        final_three = set(calendar_dates[-3:])

        for slot in slots:
            if backlog and not (
                slot["date"] in final_three
                and (slot["session"] == "AN" or (len(assignment.students) > 50 and slot["session"] == "FN"))
            ):
                continue
            ok, soft, _ = checker.can_assign(course, slot["date"], slot["session"], remaining)
            if not ok:
                ok, soft, _ = checker.can_assign(
                    course, slot["date"], slot["session"], remaining,
                    allow_gap_violation=True
                )
                if not ok:
                    continue
            candidate = replace(assignment, date=slot["date"], session=slot["session"])
            group = [
                a for a in remaining
                if (a.date, a.session) == (slot["date"], slot["session"])
            ] + [candidate]
            halls = self._session_halls(slot["date"], slot["session"])
            if sum(len(a.students) for a in group) > int(sum(int(h["capacity"]) for h in halls) * 0.90):
                continue
            if pack_courses(self.data, group, self.data["halls"], self.unavailable_halls):
                return (slot["date"], slot["session"])
        return None

    def add_late_registrant(self, student, course_code):
        if course_code not in self.data["course_by_code"]:
            return {"status": "REJECTED_UNKNOWN_COURSE", "course_code": course_code}
        sid = str(student.get("student_id", "")).strip()
        if not sid:
            return {"status": "REJECTED_UNKNOWN_STUDENT", "student_id": sid}
        student = dict(student)
        student["student_id"] = sid
        assignment = next((a for a in self.assignments if a.course_code == course_code), None)
        if assignment is None:
            return {"status": "REJECTED_UNSCHEDULED_COURSE", "course_code": course_code}
        if (
            sid in assignment.students
            or sid in self.data["course_students"].get(course_code, [])
        ):
            return {"status": "REJECTED_ALREADY_ENROLLED", "student_id": sid}

        conflicts = self._late_registration_conflicts(
            sid, student, course_code, assignment
        )
        if conflicts:
            return {
                "status": "REJECTED_CLASH",
                "student_id": sid,
                "course_codes": [course_code] + [a.course_code for a in conflicts],
            }

        old_student = self.data["student_by_id"].get(sid)
        if old_student is not None:
            student = old_student
        self.data["student_by_id"][sid] = student
        session_key = (assignment.date, assignment.session)
        current_halls = [
            hall_assignment for hall_assignment in self.hall_assignments
            if (hall_assignment.date, hall_assignment.session) == session_key
        ]
        if not current_halls:
            current_halls = HallAllocator(self.data).allocate(
                [
                    item for item in self.assignments
                    if (item.date, item.session) == session_key
                ],
                self.unavailable_halls,
            )

        available_halls = self._session_halls(*session_key)
        if sum(len(item.students) for item in self.assignments
               if (item.date, item.session) == session_key) + 1 > int(
                   sum(int(hall["capacity"]) for hall in available_halls) * 0.90
               ):
            if old_student is None:
                self.data["student_by_id"].pop(sid, None)
            else:
                self.data["student_by_id"][sid] = old_student
            return {"status": "REJECTED_NO_SEAT", "student_id": sid}

        course = self.data["course_by_code"][course_code]
        course_size = len(self.data["course_students"].get(course_code, [])) + 1
        candidates = []
        seating_engine = SeatingEngine(self.data)
        for hall in available_halls:
            existing = next(
                (item for item in current_halls if item.hall_id == hall["hall_id"]),
                None,
            )
            courses, students_by_course = self._hall_course_groups(existing)
            if course_code not in courses:
                if len(courses) >= 2:
                    continue
                if any(
                    self.data["course_by_code"][code]["department"]
                    == course.get("department")
                    for code in courses
                ):
                    continue
                if existing and existing.duration != int(assignment.duration):
                    continue
                courses.append(course_code)
                students_by_course[course_code] = []
            if course_size < 10 and (
                len(courses) != 2
                or any(
                    self.data["course_by_code"][code]["department"]
                    == course.get("department")
                    for code in courses if code != course_code
                )
            ):
                continue

            students_by_course.setdefault(course_code, []).append(sid)
            duration = int(assignment.duration)
            provisional = make_hall_assignment(
                self.data,
                assignment.date,
                assignment.session,
                hall,
                courses,
                students_by_course,
                duration,
            )
            if not seating_engine.can_seat(provisional):
                continue
            free_seats = int(hall["capacity"]) - (
                len(existing.students) if existing else 0
            )
            candidates.append((free_seats, hall["hall_id"], provisional))

        if not candidates:
            if old_student is None:
                self.data["student_by_id"].pop(sid, None)
            else:
                self.data["student_by_id"][sid] = old_student
            return {"status": "REJECTED_NO_SEAT", "student_id": sid}

        _, selected_hall_id, selected_hall = min(
            candidates, key=lambda item: (-item[0], item[1])
        )

        if old_student is None:
            self.data.setdefault("students", []).append(student)
        self.data.setdefault("course_students", {}).setdefault(
            course_code, []
        ).append(sid)
        self.data.setdefault("student_courses", {}).setdefault(sid, []).append(
            course_code
        )
        new_enrolment = {
            "course_code": course_code,
            "student_id": sid,
            "enrolment_type": (
                "BACKLOG" if str(course.get("exam_type", "")).upper() == "BACKLOG"
                else "REGULAR"
            ),
        }
        self.data.setdefault("enrolments", []).append(new_enrolment)
        self.data.setdefault("enrolment_by_student_course", {})[
            (sid, course_code)
        ] = new_enrolment
        course["enrolment_count"] = str(
            len(self.data["course_students"][course_code])
        )
        assignment.students.append(sid)
        affected = {(assignment.date, assignment.session)}
        retained = [
            hall_assignment for hall_assignment in self.hall_assignments
            if (hall_assignment.date, hall_assignment.session) != session_key
        ]
        current_halls = [
            hall_assignment for hall_assignment in current_halls
            if hall_assignment.hall_id != selected_hall_id
        ]
        self.hall_assignments = retained + current_halls + [selected_hall]
        invigilator_allocator = InvigilatorAllocator(self.data)
        self.roster = invigilator_allocator.allocate_incremental(
            self.hall_assignments, self.roster, affected
        )
        self.violations.extend(invigilator_allocator.violations)
        return {
            "status": "ADDED",
            "student_id": sid,
            "course_code": course_code,
            "hall_id": selected_hall_id,
            "affected_sessions": sorted(affected),
        }

    def _late_registration_conflicts(self, sid, student, course_code, assignment):
        same_day = [
            item for item in self.assignments
            if item.course_code != course_code
            and sid in item.students
            and item.date == assignment.date
        ]
        same_session = [
            item for item in same_day if item.session == assignment.session
        ]
        if same_session or len(same_day) >= 2:
            return same_session or same_day
        if not same_day:
            return []

        consent = str(student.get("backlog_consent", "NO")).strip().upper() == "YES"
        checker = ConstraintChecker(self.data)
        backlog_pair = (
            checker._is_backlog_for_student(sid, same_day[0].course_code)
            or checker._is_backlog_for_student(sid, course_code)
        )
        if consent and backlog_pair and same_day[0].session != assignment.session:
            return []
        return same_day

    def _hall_course_groups(self, hall_assignment):
        if hall_assignment is None:
            return [], {}
        if hall_assignment.students_by_course:
            return (
                list(hall_assignment.courses),
                {
                    code: list(hall_assignment.students_by_course.get(code, []))
                    for code in hall_assignment.courses
                },
            )

        groups = {}
        assigned = set(hall_assignment.students)
        for code in hall_assignment.courses:
            members = set(self.data["course_students"].get(code, []))
            groups[code] = [
                sid for sid in hall_assignment.students if sid in members
            ]
            assigned.difference_update(groups[code])
        if assigned and hall_assignment.courses:
            groups[hall_assignment.courses[0]].extend(sorted(assigned))
        return list(hall_assignment.courses), groups
