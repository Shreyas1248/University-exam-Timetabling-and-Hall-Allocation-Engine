from collections import defaultdict
from datetime import date
from math import ceil

from .time_utils import exam_end_time, exam_start_time


class InvigilatorAllocator:
    """Allocates invigilators with workload accounting and incremental rebuilds."""

    def __init__(self, data):
        self.data = data
        self.violations = []

    @staticmethod
    def _week_key(date_text):
        parsed = date.fromisoformat(date_text)
        iso = parsed.isocalendar()
        return (iso.year, iso.week)

    @staticmethod
    def _time_conflict(invigilator, exam_date, exam_start, exam_end):
        periods = []
        for field in ("unavailable_periods", "other_duties"):
            periods.extend(
                (field, item.strip())
                for item in invigilator.get(field, "").split(";")
                if item.strip()
            )

        exam_start_minutes = InvigilatorAllocator._minutes(exam_start)
        exam_end_minutes = InvigilatorAllocator._minutes(exam_end)
        for field, period in periods:
            parts = [part.strip() for part in period.split("|")]
            if len(parts) != 3:
                raise ValueError(
                    f"Invalid {field} entry {period!r}; expected "
                    "YYYY-MM-DD|HH:MM|HH:MM"
                )
            period_date, start, end = parts
            if period_date == exam_date:
                if (
                    InvigilatorAllocator._minutes(start) < exam_end_minutes
                    and InvigilatorAllocator._minutes(end) > exam_start_minutes
                ):
                    return True
        return False

    @staticmethod
    def _minutes(value):
        hours, minutes = (int(part) for part in value.split(":"))
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            raise ValueError(f"Invalid time value: {value}")
        return hours * 60 + minutes

    def _duty_times(self, hall_assignment):
        start = exam_start_time(
            self.data, hall_assignment.date, hall_assignment.session
        )
        has_special_needs = any(
            str(self.data["student_by_id"].get(sid, {}).get("special_needs", "NO"))
            .strip().upper() == "YES"
            for sid in hall_assignment.students
        )
        end = hall_assignment.extended_end or exam_end_time(
            self.data,
            hall_assignment.date,
            hall_assignment.session,
            hall_assignment.duration,
            20 if has_special_needs else 0,
        )
        return start, end

    def _unavailable_on_date(self, invigilator, exam_date, start, end):
        unavailable_dates = {
            value.strip()
            for value in invigilator.get("unavailable_dates", "").split(";")
            if value.strip()
        }
        return (
            exam_date in unavailable_dates
            or self._time_conflict(invigilator, exam_date, start, end)
        )

    def allocate(self, hall_assignments):
        all_keys = {(ha.date, ha.session) for ha in hall_assignments}
        return self.allocate_incremental(hall_assignments, [], all_keys)

    def allocate_incremental(self, hall_assignments, existing_roster, affected_sessions):
        self.violations = []
        affected_sessions = set(affected_sessions)
        preserved = [
            row for row in existing_roster
            if (row.get("date"), row.get("session")) not in affected_sessions
        ]

        weekly_load = defaultdict(int)
        daily_load = defaultdict(int)
        session_load = defaultdict(int)
        assigned_total = defaultdict(int)

        inv_by_id = {
            inv["invigilator_id"]: inv for inv in self.data["invigilators"]
        }

        for row in preserved:
            iid = row["invigilator_id"]
            if iid not in inv_by_id:
                continue
            weekly_load[(iid, self._week_key(row["date"]))] += 1
            daily_load[(iid, row["date"])] += 1
            session_load[(iid, row["date"], row["session"])] += 1
            assigned_total[iid] += 1

        affected_halls = [
            ha for ha in hall_assignments
            if (ha.date, ha.session) in affected_sessions
        ]
        affected_halls.sort(key=lambda ha: (ha.date, ha.session, ha.hall_id))

        new_rows = []
        for ha in affected_halls:
            hall = self.data["hall_by_id"][ha.hall_id]
            required = max(1, ceil(len(ha.students) / 30))
            duty_start, duty_end = self._duty_times(ha)
            course_departments = {
                self.data["course_by_code"][code]["department"]
                for code in ha.courses
            }
            eligible = []

            for inv in self.data["invigilators"]:
                iid = inv["invigilator_id"]
                week = self._week_key(ha.date)
                if inv["department"] in course_departments:
                    continue
                if self._unavailable_on_date(
                    inv, ha.date, duty_start, duty_end
                ):
                    continue
                if daily_load[(iid, ha.date)] >= 2:
                    continue
                if session_load[(iid, ha.date, ha.session)]:
                    continue
                if weekly_load[(iid, week)] >= int(inv["max_sessions_per_week"]):
                    continue
                eligible.append(inv)

            eligible.sort(key=lambda inv: (
                assigned_total[inv["invigilator_id"]],
                inv["department"],
                inv["invigilator_id"],
            ))
            selected = eligible[:required]

            for inv in selected:
                iid = inv["invigilator_id"]
                new_rows.append({
                    "date": ha.date,
                    "session": ha.session,
                    "hall_id": ha.hall_id,
                    "invigilator_id": iid,
                    "role": "INVIGILATOR",
                    "status": "ASSIGNED",
                })
                weekly_load[(iid, self._week_key(ha.date))] += 1
                daily_load[(iid, ha.date)] += 1
                session_load[(iid, ha.date, ha.session)] += 1
                assigned_total[iid] += 1

            if len(selected) < required:
                for _ in range(required - len(selected)):
                    new_rows.append({
                        "date": ha.date,
                        "session": ha.session,
                        "hall_id": ha.hall_id,
                        "invigilator_id": "",
                        "role": "INVIGILATOR",
                        "status": "UNSTAFFED",
                    })
                self.violations.append({
                    "rule_id": "BR-08",
                    "severity": "HARD",
                    "entity": ha.hall_id,
                    "message": (
                        f"UNSTAFFED: required {required}, assigned {len(selected)}"
                    ),
                })

        # One chief per building/session. Check all course departments in that
        # building/session, not just the first hall encountered.
        building_groups = defaultdict(list)
        for ha in affected_halls:
            building = self.data["hall_by_id"][ha.hall_id]["building"]
            building_groups[(ha.date, ha.session, building)].append(ha)

        for (exam_date, session, building), halls in sorted(building_groups.items()):
            building_departments = {
                self.data["course_by_code"][code]["department"]
                for ha in halls for code in ha.courses
            }
            candidates = []
            duty_start = min(
                self._duty_times(ha)[0] for ha in halls
            )
            duty_end = max(
                self._duty_times(ha)[1] for ha in halls
            )

            for inv in self.data["invigilators"]:
                iid = inv["invigilator_id"]
                if str(inv.get("is_chief_eligible", "NO")).upper() != "YES":
                    continue
                if inv["department"] in building_departments:
                    continue
                if self._unavailable_on_date(
                    inv, exam_date, duty_start, duty_end
                ):
                    continue
                if daily_load[(iid, exam_date)] >= 2:
                    continue
                if session_load[(iid, exam_date, session)]:
                    continue
                if weekly_load[(iid, self._week_key(exam_date))] >= int(inv["max_sessions_per_week"]):
                    continue
                candidates.append(inv)

            candidates.sort(key=lambda inv: (
                assigned_total[inv["invigilator_id"]],
                inv["department"],
                inv["invigilator_id"],
            ))

            if candidates:
                inv = candidates[0]
                iid = inv["invigilator_id"]
                # Attach the chief to the first hall in the building.
                chief_hall = sorted(halls, key=lambda ha: ha.hall_id)[0]
                new_rows.append({
                    "date": exam_date,
                    "session": session,
                    "hall_id": chief_hall.hall_id,
                    "invigilator_id": iid,
                    "role": "CHIEF",
                    "status": "ASSIGNED",
                })
                weekly_load[(iid, self._week_key(exam_date))] += 1
                daily_load[(iid, exam_date)] += 1
                session_load[(iid, exam_date, session)] += 1
                assigned_total[iid] += 1
            else:
                new_rows.append({
                    "date": exam_date,
                    "session": session,
                    "hall_id": sorted(halls, key=lambda ha: ha.hall_id)[0].hall_id,
                    "invigilator_id": "",
                    "role": "CHIEF",
                    "status": "UNSTAFFED",
                })
                self.violations.append({
                    "rule_id": "BR-08",
                    "severity": "HARD",
                    "entity": building,
                    "message": "UNSTAFFED: no eligible chief available",
                })

        return preserved + new_rows
