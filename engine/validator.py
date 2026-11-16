from datetime import datetime


class DataValidator:
    def validate(self, data):
        errors = []
        warnings = []
        self._unique(data["courses"], "course_code", "courses", errors)
        self._unique(data["students"], "student_id", "students", errors)
        self._unique(data["students"], "register_number", "students", errors)
        self._unique(data["halls"], "hall_id", "halls", errors)
        self._unique(data["invigilators"], "invigilator_id", "invigilators", errors)

        course_codes = set(data["course_by_code"])
        student_ids = set(data["student_by_id"])
        seen_enrolments = set()
        for i, row in enumerate(data["enrolments"], 2):
            if row["course_code"] not in course_codes:
                errors.append(f"enrolments.csv row {i}: unknown course {row['course_code']}")
            if row["student_id"] not in student_ids:
                errors.append(f"enrolments.csv row {i}: unknown student {row['student_id']}")
            enrolment = (row["course_code"], row["student_id"])
            if enrolment in seen_enrolments:
                errors.append(
                    f"enrolments.csv row {i}: duplicate enrolment "
                    f"{row['course_code']}/{row['student_id']}"
                )
            seen_enrolments.add(enrolment)
            if str(row.get("enrolment_type", "")).strip().upper() not in (
                "REGULAR", "BACKLOG", "LATE"
            ):
                errors.append(f"enrolments.csv row {i}: invalid enrolment type")

        for course in data["courses"]:
            try:
                duration = int(course["exam_duration_hours"])
                if duration not in (2, 3):
                    errors.append(f"{course['course_code']}: duration must be 2 or 3")
            except (ValueError, KeyError):
                errors.append(f"{course.get('course_code', '?')}: invalid exam duration")
            try:
                if int(course["credits"]) <= 0:
                    errors.append(f"{course['course_code']}: credits must be positive")
            except (ValueError, KeyError):
                errors.append(f"{course.get('course_code', '?')}: invalid credits")
            if str(course.get("exam_type", "REGULAR")).strip().upper() not in (
                "REGULAR", "BACKLOG"
            ):
                errors.append(
                    f"{course.get('course_code', '?')}: invalid exam type"
                )

        for hall in data["halls"]:
            try:
                capacity = int(hall["capacity"])
                rows = int(hall["rows"])
                columns = int(hall["columns"])
                if capacity <= 0:
                    errors.append(f"{hall['hall_id']}: capacity must be positive")
                if rows <= 0 or columns <= 0:
                    errors.append(f"{hall['hall_id']}: rows and columns must be positive")
                elif capacity > rows * columns:
                    errors.append(
                        f"{hall['hall_id']}: capacity exceeds rows x columns"
                    )
            except (ValueError, KeyError):
                errors.append(f"{hall.get('hall_id', '?')}: invalid hall dimensions or capacity")

        for student in data["students"]:
            for field in ("special_needs", "backlog_consent"):
                if str(student.get(field, "NO")).strip().upper() not in ("YES", "NO"):
                    errors.append(
                        f"{student.get('student_id', '?')}: {field} must be YES or NO"
                    )

        late_students = data.get("late_students", [])
        self._unique(late_students, "student_id", "late_students", errors)
        for student in late_students:
            if student.get("student_id") in student_ids:
                errors.append(
                    f"late_students: duplicate student_id {student.get('student_id')}"
                )
            for field in ("special_needs", "backlog_consent"):
                if str(student.get(field, "NO")).strip().upper() not in ("YES", "NO"):
                    errors.append(
                        f"{student.get('student_id', '?')}: {field} must be YES or NO"
                    )

        seen_late_enrolments = set()
        late_student_ids = {
            student.get("student_id") for student in late_students
        } | student_ids
        for i, row in enumerate(data.get("late_enrolments", []), 2):
            if row.get("student_id") not in late_student_ids:
                errors.append(
                    f"late_enrolments.csv row {i}: unknown student {row.get('student_id')}"
                )
            if row.get("course_code") not in course_codes:
                errors.append(
                    f"late_enrolments.csv row {i}: unknown course {row.get('course_code')}"
                )
            key = (row.get("student_id"), row.get("course_code"))
            if key in seen_late_enrolments:
                errors.append(
                    f"late_enrolments.csv row {i}: duplicate enrolment "
                    f"{row.get('student_id')}/{row.get('course_code')}"
                )
            seen_late_enrolments.add(key)

        valid_availability = {"YES", "TRUE", "1", "NO", "FALSE", "0"}
        seen_slots = set()
        for row in data["exam_window"]:
            slot = (row.get("date"), row.get("session"))
            if slot in seen_slots:
                errors.append(
                    f"Duplicate exam-window session {row.get('date')} {row.get('session')}"
                )
            seen_slots.add(slot)
            try:
                datetime.strptime(row["date"], "%Y-%m-%d")
                if row["session"] not in ("FN", "AN"):
                    errors.append(f"Invalid session {row['session']} on {row['date']}")
                start = datetime.strptime(row["start_time"], "%H:%M")
                end = datetime.strptime(row["end_time"], "%H:%M")
                if end <= start:
                    errors.append(
                        f"Invalid exam-window time range on {row['date']} {row['session']}"
                    )
            except (ValueError, KeyError):
                errors.append(
                    f"Invalid exam-window date or time: {row.get('date')}"
                )
            if str(row.get("available", "")).strip().upper() not in valid_availability:
                errors.append(
                    f"Invalid availability on {row.get('date')} {row.get('session')}"
                )

        seen_holidays = set()
        for row in data["holidays"]:
            try:
                datetime.strptime(row["date"], "%Y-%m-%d")
            except (ValueError, KeyError):
                errors.append(f"Invalid holiday date: {row.get('date')}")
            holiday_date = row.get("date")
            if holiday_date in seen_holidays:
                errors.append(f"Duplicate holiday date: {holiday_date}")
            seen_holidays.add(holiday_date)
            if any(
                exam.get("date") == holiday_date
                and str(exam.get("available", "")).strip().upper()
                in ("YES", "TRUE", "1")
                for exam in data["exam_window"]
            ):
                errors.append(
                    f"Exam session is available on holiday {holiday_date}"
                )

        for invigilator in data["invigilators"]:
            try:
                weekly_limit = int(invigilator["max_sessions_per_week"])
                if not 4 <= weekly_limit <= 8:
                    errors.append(
                        f"{invigilator['invigilator_id']}: weekly maximum must be 4 to 8"
                    )
            except (ValueError, KeyError):
                errors.append(
                    f"{invigilator.get('invigilator_id', '?')}: invalid weekly maximum"
                )
            if str(invigilator.get("is_chief_eligible", "NO")).strip().upper() not in (
                "YES", "NO"
            ):
                errors.append(
                    f"{invigilator.get('invigilator_id', '?')}: "
                    "is_chief_eligible must be YES or NO"
                )
            for unavailable_date in invigilator.get(
                "unavailable_dates", ""
            ).split(";"):
                if not unavailable_date.strip():
                    continue
                try:
                    datetime.strptime(unavailable_date.strip(), "%Y-%m-%d")
                except ValueError:
                    errors.append(
                        f"{invigilator.get('invigilator_id', '?')}: invalid "
                        f"unavailable date {unavailable_date.strip()!r}"
                    )
            for field in ("unavailable_periods", "other_duties"):
                for entry in invigilator.get(field, "").split(";"):
                    if not entry.strip():
                        continue
                    parts = [part.strip() for part in entry.split("|")]
                    try:
                        if len(parts) != 3:
                            raise ValueError
                        datetime.strptime(parts[0], "%Y-%m-%d")
                        start = datetime.strptime(parts[1], "%H:%M")
                        end = datetime.strptime(parts[2], "%H:%M")
                        if end <= start:
                            raise ValueError
                    except ValueError:
                        errors.append(
                            f"{invigilator.get('invigilator_id', '?')}: invalid "
                            f"{field} entry {entry.strip()!r}"
                        )

        return {"valid": not errors, "errors": errors, "warnings": warnings}

    @staticmethod
    def _unique(rows, field, label, errors):
        seen = set()
        for row in rows:
            value = row.get(field)
            if not value:
                errors.append(f"{label}: missing {field}")
            elif value in seen:
                errors.append(f"{label}: duplicate {field} {value}")
            seen.add(value)
