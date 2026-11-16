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
        "students": sorted(
            assignment.students,
            key=lambda sid: data["student_by_id"].get(sid, {}).get(
                "register_number", sid
            ),
        ),
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
        if str(hall.get("available", "YES")).strip().upper()
        in ("YES", "TRUE", "1")
        and (hall["hall_id"], date, session) not in unavailable
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
        0 if len(item["students"]) < 10 else 1,
        -len(item["students"]), -item["duration"], item["code"]
    ))
    seating_engine = SeatingEngine(data)
    failures = []

    for item in items:
        remaining = list(item["students"])
        candidates = [
            bin_ for bin_ in bins
            if bin_["remaining"] > 0
            and len(bin_["courses"]) < 2
            and (
                bin_["duration"] is None
                or bin_["duration"] == item["duration"]
            )
            and (
                not bin_["courses"]
                or item["department"] not in bin_["departments"]
            )
        ]

        for bin_ in candidates:
            if not remaining:
                break
            hall = bin_["hall"]
            if str(hall.get("floor", "")).strip().upper() == "GROUND":
                special_students = [
                    sid for sid in remaining
                    if str(
                        data["student_by_id"].get(sid, {}).get(
                            "special_needs", "NO"
                        )
                    ).strip().upper() == "YES"
                ]
                regular_students = [
                    sid for sid in remaining if sid not in set(special_students)
                ]
                special_limit = (
                    len(special_students)
                    if bin_["courses"]
                    else (int(hall["columns"]) + 1) // 2
                )
                special_limit = min(
                    special_limit,
                    (int(hall["columns"]) + 1) // 2,
                    bin_["remaining"],
                )
            else:
                special_students = []
                regular_students = [
                    sid for sid in remaining
                    if str(
                        data["student_by_id"].get(sid, {}).get(
                            "special_needs", "NO"
                        )
                    ).strip().upper() != "YES"
                ]
                special_limit = 0

            existing_students = len(remaining)
            maximum = min(bin_["remaining"], existing_students)
            course_seat_limit = min(
                int(hall["capacity"]),
                int(hall["rows"]) * ((int(hall["columns"]) + 1) // 2),
            )
            maximum = min(maximum, course_seat_limit)
            selected = None
            for special_count in range(special_limit, -1, -1):
                chosen_special = special_students[:special_count]
                regular_limit = min(
                    len(regular_students), maximum - len(chosen_special)
                )
                for regular_count in range(regular_limit, -1, -1):
                    chosen_students = chosen_special + regular_students[:regular_count]
                    if not chosen_students:
                        continue
                    courses = list(bin_["courses"])
                    students_by_course = {
                        code: list(bin_["students_by_course"].get(code, []))
                        for code in courses
                    }
                    if item["code"] not in courses:
                        courses.append(item["code"])
                    students_by_course.setdefault(item["code"], []).extend(
                        chosen_students
                    )
                    provisional = make_hall_assignment(
                        data, date, session, hall, courses,
                        students_by_course, item["duration"]
                    )
                    if seating_engine.can_seat(provisional):
                        selected = chosen_students
                        break
                if selected:
                    break

            if not selected:
                continue

            selected_set = set(selected)
            remaining = [
                sid for sid in remaining if sid not in selected_set
            ]
            bin_["remaining"] -= len(selected)
            bin_["duration"] = item["duration"]
            bin_["departments"].add(item["department"])
            if item["code"] not in bin_["courses"]:
                bin_["courses"].append(item["code"])
            bin_["students_by_course"].setdefault(item["code"], []).extend(
                selected
            )

        if remaining:
            failures.append((
                item["code"],
                f"{len(remaining)} of {len(item['students'])} students have no "
                f"compatible hall with valid seats on {date} {session}",
            ))

    for bin_ in bins:
        if len(bin_["courses"]) == 1:
            code = bin_["courses"][0]
            if len(data["course_students"].get(code, [])) < 10:
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
