from engine.models import Assignment, HallAssignment
from engine.change_manager import ChangeManager

def test_postpone_moves_course_to_later_available_session(small_data):
    students = [f"T{index:03d}" for index in range(10)]
    for sid in students:
        student = {
            "student_id": sid,
            "register_number": sid,
            "special_needs": "NO",
            "backlog_consent": "NO",
        }
        small_data["students"].append(student)
        small_data["student_by_id"][sid] = student
    small_data["course_students"]["CSE101"] = students
    small_data["halls"] = [{
        "hall_id": "H01", "capacity": "180", "rows": "21", "columns": "9",
        "building": "B1", "floor": "GROUND",
    }]
    small_data["hall_by_id"] = {"H01": small_data["halls"][0]}
    assignment = Assignment(
        course_code="CSE101", date="2026-12-01", session="FN",
        duration=3, students=students
    )
    manager = ChangeManager(small_data, [assignment])
    result = manager.postpone("CSE101")
    assert result["status"] == "POSTPONED"
    assert assignment.date > "2026-12-01" or (
        assignment.date == "2026-12-01" and assignment.session == "AN"
    )

def test_unknown_course_is_rejected(small_data):
    manager = ChangeManager(small_data, [])
    result = manager.postpone("NO_SUCH_COURSE")
    assert result["status"] == "REJECTED_UNKNOWN_COURSE"

def test_late_regular_exam_conflict_is_rejected_without_mutation(small_data):
    existing = Assignment(
        "CSE102", "2026-12-01", "FN", 2, ["LATE099"]
    )
    candidate = Assignment(
        "CSE101", "2026-12-01", "AN", 3, ["S002"]
    )
    manager = ChangeManager(small_data, [existing, candidate])

    result = manager.add_late_registrant({
        "student_id": "LATE099",
        "register_number": "LATE099",
        "backlog_consent": "NO",
        "special_needs": "NO",
    }, "CSE101")

    assert result["status"] == "REJECTED_CLASH"
    assert result["course_codes"] == ["CSE101", "CSE102"]
    assert "LATE099" not in small_data["student_by_id"]

def test_late_backlog_registration_uses_hall_with_most_free_seats(small_data):
    halls = [
        {
            "hall_id": "H01", "capacity": "180", "rows": "21", "columns": "9",
            "building": "B1", "floor": "GROUND",
        },
        {
            "hall_id": "H02", "capacity": "160", "rows": "20", "columns": "8",
            "building": "B1", "floor": "GROUND",
        },
    ]
    small_data["halls"] = halls
    small_data["hall_by_id"] = {hall["hall_id"]: hall for hall in halls}
    small_data["course_by_code"]["CSE102"].update({
        "department": "CSE",
        "exam_duration_hours": "3",
    })

    def add_students(prefix, count, course_code):
        ids = []
        for index in range(count):
            sid = f"{prefix}{index:03d}"
            ids.append(sid)
            student = {
                "student_id": sid,
                "register_number": sid,
                "special_needs": "NO",
                "backlog_consent": "NO",
            }
            small_data["students"].append(student)
            small_data["student_by_id"][sid] = student
        small_data["course_students"][course_code] = ids
        return ids

    cse_students = add_students("C", 5, "CSE102")
    ece_students = add_students("E", 10, "ECE201")
    ece_course = {
        "course_code": "ECE201",
        "department": "ECE",
        "semester": "2",
        "credits": "2",
        "exam_duration_hours": "3",
        "exam_type": "BACKLOG",
        "enrolment_count": "10",
    }
    small_data["courses"].append(ece_course)
    small_data["course_by_code"]["ECE201"] = ece_course
    small_data["course_students"]["ECE201"] = ece_students

    late_sid = "LATE099"
    cse_exam = Assignment(
        "CSE101", "2026-12-01", "FN", 3, [late_sid]
    )
    cse_hall_exam = Assignment(
        "CSE102", "2026-12-01", "AN", 3, cse_students
    )
    ece_exam = Assignment(
        "ECE201", "2026-12-01", "AN", 3, ece_students
    )
    halls = [
        HallAssignment(
            "2026-12-01", "AN", "H01", ["CSE102"], cse_students, 3,
            students_by_course={"CSE102": cse_students},
        ),
        HallAssignment(
            "2026-12-01", "AN", "H02", ["ECE201"], ece_students, 3,
            students_by_course={"ECE201": ece_students},
        ),
    ]
    manager = ChangeManager(
        small_data, [cse_exam, cse_hall_exam, ece_exam], halls
    )

    result = manager.add_late_registrant({
        "student_id": late_sid,
        "register_number": late_sid,
        "special_needs": "NO",
        "backlog_consent": "YES",
    }, "ECE201")

    assert result["status"] == "ADDED"
    assert result["hall_id"] == "H01"
    selected_hall = next(
        hall for hall in manager.hall_assignments
        if hall.hall_id == "H01" and hall.session == "AN"
    )
    assert late_sid in selected_hall.students_by_course["ECE201"]
    assert late_sid in small_data["course_students"]["ECE201"]

def test_late_registration_no_seat_rolls_back_student(small_data):
    assignment = Assignment(
        "CSE101", "2026-12-01", "FN", 3, ["S001", "S002"]
    )
    unavailable = {
        ("H01", "2026-12-01", "FN"),
        ("H02", "2026-12-01", "FN"),
    }
    manager = ChangeManager(
        small_data, [assignment], unavailable_halls=unavailable
    )

    result = manager.add_late_registrant({
        "student_id": "LATE099",
        "register_number": "LATE099",
        "special_needs": "NO",
        "backlog_consent": "NO",
    }, "CSE101")

    assert result["status"] == "REJECTED_NO_SEAT"
    assert "LATE099" not in small_data["student_by_id"]
    assert "LATE099" not in assignment.students

def test_hall_closure_moves_smallest_course_when_capacity_is_insufficient(small_data):
    small_data["halls"][0].update({
        "capacity": "25",
        "rows": "5",
        "columns": "5",
    })
    students = []
    for index in range(10):
        sid = f"M{index:03d}"
        students.append(sid)
        student = {
            "student_id": sid,
            "register_number": sid,
            "special_needs": "NO",
            "backlog_consent": "NO",
        }
        small_data["students"].append(student)
        small_data["student_by_id"][sid] = student
    small_data["course_students"]["CSE101"] = students
    assignment = Assignment(
        "CSE101", "2026-12-01", "FN", 3, students
    )
    hall_assignment = HallAssignment(
        "2026-12-01", "FN", "H01", ["CSE101"], students, 3,
        students_by_course={"CSE101": students},
    )
    manager = ChangeManager(
        small_data, [assignment], [hall_assignment]
    )

    result = manager.mark_hall_unavailable(
        "H01", "2026-12-01", "FN"
    )

    assert result["status"] == "HALL_MARKED_UNAVAILABLE"
    assert (assignment.date, assignment.session) == ("2026-12-01", "AN")
    assert any(v["rule_id"] == "BR-10" for v in manager.violations)
