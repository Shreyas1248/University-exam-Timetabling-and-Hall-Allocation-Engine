from .models import HallAssignment
from .seating_engine import SeatingEngine
from .time_utils import exam_end_time


def _course_meta(data, assignment):
    course = data["course_by_code"].get(assignment.course_code, {})
    return {
        "assignment": assignment,
        "code": assignment.course_code,
        "department": course.get("department", ""),
        "duration": int(assignment.duration),
        "students": list(assignment.students),
    }


def make_hall_assignment(data, date, session, hall, courses, students_by_course,
                         duration):
    students = [
        sid for code in courses for sid in students_by_course.get(code, [])
    ]
    has_special_needs = any(
        str(data["student_by_id"].get(sid, {}).get("special_needs", "NO"))
        .strip().upper() == "YES"
        for sid in students
    )
    extended_end = (
        exam_end_time(data, date, session, duration, 20)
        if has_special_needs else None
    )
    return HallAssignment(
        date=date,
        session=session,
        hall_id=hall["hall_id"],
        courses=list(courses),
        students=students,
        duration=duration,
        extended_end=extended_end,
        students_by_course={
            code: list(students_by_course.get(code, [])) for code in courses
        },
    )


def _pack_session(data, assignments, halls, unavailable=None):
    unavailable = unavailable or set()
    if not assignments:
        return [], []
    date, session = assignments[0].date, assignments[0].session
    available_halls = [
        hall for hall in halls
        if (hall["hall_id"], date, session) not in unavailable
    ]
    bins = [
        {
            "hall": hall,
            "remaining": int(hall["capacity"]),
            "duration": None,
            "departments": set(),
            "courses": [],
            "students_by_course": {},
        }
        for hall in sorted(
            available_halls,
            key=lambda item: (-int(item["capacity"]), item["hall_id"]),
        )
    ]

    items = [_course_meta(data, assignment) for assignment in assignments]
    items.sort(key=lambda item: (
        -len(item["students"]), -item["duration"], item["code"]
    ))
    seating_engine = SeatingEngine(data)
    failures = []

    for item in items:
        candidates = []
        for bin_ in bins:
            if bin_["remaining"] < len(item["students"]):
                continue
            if len(bin_["courses"]) >= 2:
                continue
            if bin_["duration"] is not None and bin_["duration"] != item["duration"]:
                continue
            if (
                bin_["courses"]
                and item["department"] in bin_["departments"]
            ):
                continue

            courses = bin_["courses"] + [item["code"]]
            students_by_course = {
                code: list(bin_["students_by_course"].get(code, []))
                for code in bin_["courses"]
            }
            students_by_course[item["code"]] = list(item["students"])
            provisional = make_hall_assignment(
                data, date, session, bin_["hall"], courses,
                students_by_course, item["duration"]
            )
            if seating_engine.can_seat(provisional):
                candidates.append(bin_)

        if not candidates:
            failures.append((
                item["code"],
                f"{len(item['students'])} students have no compatible hall "
                f"with valid seats on {date} {session}",
            ))
            continue

        candidates.sort(key=lambda bin_: (
            0 if bin_["courses"] else 1,
            -int(bin_["hall"]["capacity"]),
            bin_["hall"]["hall_id"],
        ))
        chosen = candidates[0]
        chosen["remaining"] -= len(item["students"])
        chosen["duration"] = item["duration"]
        chosen["departments"].add(item["department"])
        chosen["courses"].append(item["code"])
        chosen["students_by_course"][item["code"]] = list(item["students"])

    for bin_ in bins:
        if len(bin_["courses"]) == 1:
            code = bin_["courses"][0]
            if len(bin_["students_by_course"][code]) < 10:
                failures.append((
                    code,
                    "Courses with fewer than 10 students must share a hall "
                    "with a different department",
                ))

    return bins, failures


def pack_courses(data, assignments, halls, unavailable=None):
    if not assignments:
        return True
    grouped = {}
    for assignment in assignments:
        grouped.setdefault((assignment.date, assignment.session), []).append(assignment)
    for (date, session), session_assignments in grouped.items():
        _, failures = _pack_session(
            data, session_assignments, halls, unavailable
        )
        if failures:
            return False
    return True


class HallAllocator:
    """Allocates each session using the same seating and hall feasibility rules."""

    def __init__(self, data):
        self.data = data
        self.violations = []

    def allocate(self, assignments, unavailable=None):
        self.violations = []
        unavailable = unavailable or set()
        grouped = {}
        for assignment in assignments:
            grouped.setdefault((assignment.date, assignment.session), []).append(assignment)

        result = []
        for (date, session), session_assignments in sorted(grouped.items()):
            bins, failures = _pack_session(
                self.data, session_assignments, self.data["halls"], unavailable
            )
            for code, message in failures:
                rule_id = "BR-05" if "fewer than 10" in message else "BR-06"
                self.violations.append({
                    "rule_id": rule_id,
                    "severity": "HARD",
                    "entity": code,
                    "message": message,
                })

            for bin_ in bins:
                if not bin_["courses"]:
                    continue
                result.append(make_hall_assignment(
                    self.data,
                    date,
                    session,
                    bin_["hall"],
                    bin_["courses"],
                    bin_["students_by_course"],
                    int(bin_["duration"]),
                ))
        return result
