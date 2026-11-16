from datetime import datetime


class ConstraintChecker:
    """Checks student clashes, daily limits and programme-semester core gaps."""

    def __init__(self, data):
        self.data = data
        self.student_daily = {}
        self.student_session = {}

    def _course_cohorts(self, course):
        code = course["course_code"]
        cohorts = set()
        for sid in self.data["course_students"].get(code, []):
            student = self.data["student_by_id"].get(sid, {})
            programme = (
                student.get("programme")
                or student.get("department")
                or course.get("department", "")
            )
            semester = student.get("semester") or course.get("semester", "")
            cohorts.add((str(programme).strip(), str(semester).strip()))
        if not cohorts:
            cohorts.add((
                str(course.get("department", "")).strip(),
                str(course.get("semester", "")).strip(),
            ))
        return cohorts

    def can_assign(self, course, date, session, assignments, allow_gap_violation=False):
        code = course["course_code"]
        students = self.data["course_students"].get(code, [])
        soft = []

        for sid in students:
            if (sid, date, session) in self.student_session:
                return False, [], f"student {sid} has a session clash"

            same_day = {
                (a.course_code, a.session)
                for a in assignments
                if sid in a.students and a.date == date
            }
            same_day.update(
                (course_code, registered_session)
                for (registered_sid, registered_date, registered_session), course_code
                in self.student_session.items()
                if registered_sid == sid and registered_date == date
            )
            if len(same_day) >= 2:
                return False, [], f"student {sid} exceeds two exams per day"

            if len(same_day) == 1:
                student = self.data["student_by_id"].get(sid, {})
                consent = str(student.get("backlog_consent", "NO")).strip().upper() == "YES"
                candidate_backlog = str(course.get("exam_type", "REGULAR")).strip().upper() == "BACKLOG"
                existing_code, existing_session = next(iter(same_day))
                existing_course = self.data["course_by_code"].get(existing_code, {})
                existing_backlog = str(existing_course.get("exam_type", "REGULAR")).strip().upper() == "BACKLOG"
                if not (
                    consent
                    and (candidate_backlog or existing_backlog)
                    and existing_session != session
                ):
                    return False, [], f"student {sid} exceeds one exam per day"

        candidate_cohorts = self._course_cohorts(course)
        if int(course.get("credits", 0)) >= 4:
            current = datetime.strptime(date, "%Y-%m-%d").date()
            for assignment in assignments:
                other = self.data["course_by_code"].get(assignment.course_code, {})
                if int(other.get("credits", 0)) < 4:
                    continue
                if not candidate_cohorts.intersection(
                    self._course_cohorts(other)
                ):
                    continue
                previous = datetime.strptime(assignment.date, "%Y-%m-%d").date()
                if abs((current - previous).days) < 2:
                    if allow_gap_violation:
                        soft.append("BR-02: core exams have fewer than one full day between them")
                    else:
                        return False, [], "core-course gap rule"

        return True, soft, None

    def register(self, course, date, session):
        code = course["course_code"]
        for sid in self.data["course_students"].get(code, []):
            self.student_session[(sid, date, session)] = code
            self.student_daily.setdefault((sid, date), []).append(code)

    def clear_and_rebuild(self, assignments):
        self.student_daily.clear()
        self.student_session.clear()
        for assignment in assignments:
            course = self.data["course_by_code"][assignment.course_code]
            self.register(course, assignment.date, assignment.session)
