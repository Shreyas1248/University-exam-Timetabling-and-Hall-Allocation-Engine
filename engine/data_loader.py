import csv
import os

class DataLoader:
    """Loads PS-067 CSV inputs and builds indexed in-memory data."""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.data = {}

    def _read(self, filename, required=True):
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            if required:
                raise FileNotFoundError(f"Required input file not found: {path}")
            return []
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def load_all(self):
        names = {
            "courses": "courses.csv",
            "students": "students.csv",
            "enrolments": "enrolments.csv",
            "halls": "halls.csv",
            "invigilators": "invigilators.csv",
            "exam_window": "exam_window.csv",
        }
        for key, filename in names.items():
            self.data[key] = self._read(filename)
        self.data["holidays"] = self._read("holidays.csv", False)
        self.data["invigilator_unavailability"] = self._read(
            "invigilator_unavailability.csv", False
        )
        self.data["late_students"] = self._read("late_students.csv", False)
        self.data["late_enrolments"] = self._read("late_enrolments.csv", False)
        if os.path.exists(os.path.join(self.data_dir, "change_commands.csv")):
            self.data["change_commands"] = self._read("change_commands.csv")
        else:
            self.data["change_commands"] = []
        self._normalize_inputs()
        self._build_indexes()
        return self.data

    @staticmethod
    def _yes_no(value, default="NO"):
        normalized = str(value if value is not None else default).strip().upper()
        if normalized in ("TRUE", "YES", "1"):
            return "YES"
        if normalized in ("FALSE", "NO", "0", ""):
            return "NO"
        return normalized

    def _normalize_inputs(self):
        for course in self.data["courses"]:
            exam_type = str(course.get("exam_type", "REGULAR")).strip().upper()
            if exam_type == "SUPPLEMENTARY":
                course["exam_type"] = "BACKLOG"
            else:
                course["exam_type"] = exam_type

        for student in self.data["students"]:
            student.setdefault("student_id", student.get("register_no", ""))
            student.setdefault(
                "register_number", student.get("register_no", student["student_id"])
            )
            student.setdefault("name", student.get("student_name", ""))
            student.setdefault(
                "department",
                student.get("programme", student.get("department", "")),
            )
            student["special_needs"] = self._yes_no(
                student.get("special_needs")
            )
            student["backlog_consent"] = self._yes_no(
                student.get("backlog_consent")
            )

        for enrolment in self.data["enrolments"]:
            enrolment.setdefault(
                "student_id", enrolment.get("register_no", "")
            )
            enrolment["enrolment_type"] = str(
                enrolment.get("enrolment_type", "REGULAR")
            ).strip().upper()

        for hall in self.data["halls"]:
            floor = str(hall.get("floor", "")).strip().upper()
            hall["floor"] = {
                "0": "GROUND",
                "1": "FIRST",
                "2": "SECOND",
            }.get(floor, floor)
            hall["available"] = self._yes_no(hall.get("available"), "YES")

        for invigilator in self.data["invigilators"]:
            invigilator.setdefault(
                "name", invigilator.get("invigilator_name", "")
            )
            invigilator.setdefault("unavailable_dates", "")
            invigilator.setdefault("unavailable_periods", "")
            invigilator.setdefault("is_chief_eligible", "YES")

        if self.data["exam_window"] and "session" not in self.data["exam_window"][0]:
            expanded = []
            for row in self.data["exam_window"]:
                for session, available_field, start, end in (
                    ("FN", "fn_available", "09:30", "12:30"),
                    ("AN", "an_available", "14:00", "17:00"),
                ):
                    expanded.append({
                        "date": row["date"],
                        "session": session,
                        "start_time": start,
                        "end_time": end,
                        "available": self._yes_no(row.get(available_field)),
                    })
            self.data["exam_window"] = expanded

        if not self.data["holidays"]:
            self.data["holidays"] = [
                {"date": day}
                for day in sorted({
                    row["date"] for row in self.data["exam_window"]
                })
                if not any(
                    row["date"] == day
                    and self._yes_no(row.get("available")) == "YES"
                    for row in self.data["exam_window"]
                )
            ]

        invigilators = {
            inv["invigilator_id"]: inv for inv in self.data["invigilators"]
        }
        for row in self.data["invigilator_unavailability"]:
            invigilator = invigilators.get(row.get("invigilator_id"))
            if invigilator is None:
                continue
            start = str(row.get("from_time", "")).strip()
            end = str(row.get("to_time", "")).strip()
            if start == "00:00" and end in ("23:59", "24:00"):
                dates = [
                    value for value in invigilator["unavailable_dates"].split(";")
                    if value
                ]
                if row["date"] not in dates:
                    dates.append(row["date"])
                invigilator["unavailable_dates"] = ";".join(dates)
            else:
                periods = [
                    value for value in invigilator["unavailable_periods"].split(";")
                    if value
                ]
                periods.append(f"{row['date']}|{start}|{end}")
                invigilator["unavailable_periods"] = ";".join(periods)

    def _build_indexes(self):
        courses = {r["course_code"]: r for r in self.data["courses"]}
        students = {r["student_id"]: r for r in self.data["students"]}
        course_students = {code: [] for code in courses}
        student_courses = {sid: [] for sid in students}
        enrolment_by_student_course = {}
        for row in self.data["enrolments"]:
            code, sid = row["course_code"], row["student_id"]
            if code in course_students and sid in student_courses:
                course_students[code].append(sid)
                student_courses[sid].append(code)
                enrolment_by_student_course[(sid, code)] = row
        for code, course in courses.items():
            course["enrolment_count"] = str(len(course_students[code]))
        self.data.update({
            "course_by_code": courses,
            "student_by_id": students,
            "course_students": course_students,
            "student_courses": student_courses,
            "enrolment_by_student_course": enrolment_by_student_course,
            "hall_by_id": {r["hall_id"]: r for r in self.data["halls"]},
            "invigilator_by_id": {r["invigilator_id"]: r for r in self.data["invigilators"]},
        })
