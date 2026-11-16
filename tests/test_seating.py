from engine.models import HallAssignment
from engine.seating_engine import SeatingEngine

def test_seating_numbers_are_row_major(small_data):
    assignment = HallAssignment(
        date="2026-12-01", session="FN", hall_id="H01",
        courses=["CSE101"], students=["S001","S002"], duration=3
    )
    plan = SeatingEngine(small_data).create_seating_plan([assignment])
    assert [p["seat_number"] for p in plan] == [1, 2]
    assert [(p["row"],p["column"]) for p in plan] == [(1,1),(1,2)]

def test_special_needs_student_is_flagged(small_data):
    assignment = HallAssignment(
        date="2026-12-01", session="FN", hall_id="H01",
        courses=["CSE101"], students=["S002"], duration=3
    )
    plan = SeatingEngine(small_data).create_seating_plan([assignment])
    assert plan[0]["special_needs"] == "YES"
    assert plan[0]["priority_seating"] == "GROUND_ROW_1"
