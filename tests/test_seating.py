from engine.models import HallAssignment
from engine.seating_engine import SeatingEngine

def test_seating_numbers_are_row_major(small_data):
    assignment = HallAssignment(
        date="2026-12-01", session="FN", hall_id="H01",
        courses=["CSE101"], students=["S001","S002"], duration=3
    )
    plan = SeatingEngine(small_data).create_seating_plan([assignment])
    assert [p["seat_number"] for p in plan] == [1, 3]
    assert [(p["row"],p["column"]) for p in plan] == [(1,1),(1,3)]
    assert all(p["status"] == "ASSIGNED" for p in plan)

def test_special_needs_student_is_flagged(small_data):
    assignment = HallAssignment(
        date="2026-12-01", session="FN", hall_id="H01",
        courses=["CSE101"], students=["S002"], duration=3
    )
    plan = SeatingEngine(small_data).create_seating_plan([assignment])
    assert plan[0]["special_needs"] == "YES"
    assert plan[0]["priority_seating"] == "GROUND_ROW_1"

def test_students_from_different_courses_are_alternated(small_data):
    small_data["student_by_id"]["S003"] = {
        "student_id": "S003",
        "register_number": "S003",
        "special_needs": "NO",
    }
    assignment = HallAssignment(
        date="2026-12-01", session="FN", hall_id="H01",
        courses=["CSE101", "CSE102"], students=["S001", "S002", "S003"],
        duration=3,
        students_by_course={
            "CSE101": ["S001", "S002"],
            "CSE102": ["S003"],
        },
    )

    plan = SeatingEngine(small_data).create_seating_plan([assignment])
    assert [p["course_code"] for p in plan] == [
        "CSE101", "CSE102", "CSE101"
    ]
    assert all(
        left["course_code"] != right["course_code"]
        for left, right in zip(plan, plan[1:])
    )

def test_special_needs_student_cannot_be_seated_off_ground_floor(small_data):
    assignment = HallAssignment(
        date="2026-12-01", session="FN", hall_id="H02",
        courses=["CSE101"], students=["S002"], duration=3,
    )

    plan = SeatingEngine(small_data).create_seating_plan([assignment])
    assert plan[0]["status"] == "SPECIAL_NEEDS_GROUND_FLOOR_REQUIRED"
    assert not SeatingEngine(small_data).can_seat(assignment)
