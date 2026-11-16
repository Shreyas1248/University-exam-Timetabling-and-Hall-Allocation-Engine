from .base_report import BaseReport
from engine.time_utils import exam_end_time

class TimetableReport(BaseReport):
    FIELDS = ["course_code", "date", "session", "start_time", "end_time",
              "duration_hours", "enrolment_count", "status", "soft_violations"]

    def generate(self, assignments, data):
        window = {(r["date"], r["session"]): r for r in data["exam_window"]}
        courses = data["course_by_code"]
        rows = []
        scheduled_codes = {assignment.course_code for assignment in assignments}
        for a in sorted(assignments, key=lambda x:(x.date, 0 if x.session=="FN" else 1, x.course_code)):
            slot = window.get((a.date, a.session), {})
            rows.append({
                "course_code": a.course_code,
                "date": a.date,
                "session": a.session,
                "start_time": slot.get("start_time", ""),
                "end_time": exam_end_time(
                    data, a.date, a.session, a.duration
                ),
                "duration_hours": a.duration,
                "enrolment_count": len(a.students),
                "status": "SCHEDULED",
                "soft_violations": " | ".join(a.soft_violations)
            })
        for code, course in sorted(courses.items()):
            if code in scheduled_codes:
                continue
            rows.append({
                "course_code": code,
                "date": "",
                "session": "",
                "start_time": "",
                "end_time": "",
                "duration_hours": course.get("exam_duration_hours", ""),
                "enrolment_count": len(data["course_students"].get(code, [])),
                "status": "UNSCHEDULED",
                "soft_violations": "",
            })
        rows.sort(key=lambda row: (
            row["status"] != "SCHEDULED",
            row["date"],
            0 if row["session"] == "FN" else 1,
            row["course_code"],
        ))
        path = self.write_csv("timetable.csv", rows, self.FIELDS)
        lines = ["UNIVERSITY EXAMINATION TIMETABLE", "=" * 70, ""]
        for r in rows:
            lines.append(
                (
                    f'{r["date"]} {r["session"]} '
                    f'({r["start_time"]}-{r["end_time"]}) | '
                    f'{r["course_code"]:<12} | {r["enrolment_count"]:>4} students | '
                    f'{r["duration_hours"]} hours'
                    if r["status"] == "SCHEDULED"
                    else f'{r["course_code"]:<12} | UNSCHEDULED | '
                    f'{r["enrolment_count"]:>4} students'
                )
            )
            if r["soft_violations"]:
                lines.append(f'  SOFT VIOLATION: {r["soft_violations"]}')
        self.write_text("timetable.txt", "\n".join(lines) + "\n")
        return path
