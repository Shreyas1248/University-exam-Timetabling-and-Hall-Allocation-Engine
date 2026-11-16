from engine.scheduler import ExamScheduler


def test_backlog_repair_rebalances_courses_to_avoid_greedy_dead_end(small_data):
    courses = [
        ("CSE101", "CSE", ["AB"] + [f"A{i}" for i in range(9)]),
        ("ECE101", "ECE", ["CD"] + [f"D{i}" for i in range(9)]),
        ("ISE101", "ISE", ["AB", "BC"] + [f"B{i}" for i in range(8)]),
        ("ME101", "ME", ["BC", "CD"] + [f"C{i}" for i in range(8)]),
    ]
    course_rows = []
    course_students = {}
    student_by_id = {}
    student_courses = {}

    for code, department, students in courses:
        course_rows.append({
            "course_code": code,
            "department": department,
            "semester": "1",
            "credits": "2",
            "exam_duration_hours": "2",
            "exam_type": "BACKLOG",
            "enrolment_count": str(len(students)),
        })
        course_students[code] = students
        for student_id in students:
            student_by_id.setdefault(student_id, {
                "student_id": student_id,
                "register_number": student_id,
                "programme": department,
                "department": department,
                "semester": "1",
                "special_needs": "NO",
                "backlog_consent": "NO",
            })
            student_courses.setdefault(student_id, []).append(code)

    small_data["courses"] = course_rows
    small_data["course_by_code"] = {
        course["course_code"]: course for course in course_rows
    }
    small_data["course_students"] = course_students
    small_data["students"] = list(student_by_id.values())
    small_data["student_by_id"] = student_by_id
    small_data["student_courses"] = student_courses
    halls = [
        {
            "hall_id": "H01",
            "capacity": "100",
            "rows": "10",
            "columns": "10",
            "building": "B1",
            "floor": "GROUND",
        },
        {
            "hall_id": "H02",
            "capacity": "100",
            "rows": "10",
            "columns": "10",
            "building": "B1",
            "floor": "GROUND",
        },
    ]
    small_data["halls"] = halls
    small_data["hall_by_id"] = {hall["hall_id"]: hall for hall in halls}

    assignments = ExamScheduler(small_data).generate()

    scheduled = {assignment.course_code: assignment for assignment in assignments}
    assert set(scheduled) == set(small_data["course_by_code"])
    assert (scheduled["CSE101"].date, scheduled["CSE101"].session) == (
        "2026-12-01", "AN"
    )
    assert (scheduled["ME101"].date, scheduled["ME101"].session) == (
        "2026-12-01", "AN"
    )
    assert (scheduled["ECE101"].date, scheduled["ECE101"].session) == (
        "2026-12-02", "AN"
    )
    assert (scheduled["ISE101"].date, scheduled["ISE101"].session) == (
        "2026-12-02", "AN"
    )
