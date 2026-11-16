from engine.models import HallAssignment
from engine.invigilator_allocator import InvigilatorAllocator
from engine.hall_allocator import HallAllocator
from engine.models import Assignment

def test_assigns_required_invigilator_and_chief(small_data):
    hall_assignment = HallAssignment(
        date="2026-12-01", session="FN", hall_id="H01",
        courses=["CSE101"], students=["S001","S002"], duration=3
    )
    allocator = InvigilatorAllocator(small_data)
    roster = allocator.allocate([hall_assignment])
    assert any(r["role"] == "INVIGILATOR" for r in roster)
    assert any(r["role"] == "CHIEF" for r in roster)
    assert all(r["invigilator_id"] != "" for r in roster)

def test_extended_duty_ends_at_1720_before_1730_duty(small_data):
    small_data["invigilators"][0]["unavailable_periods"] = (
        "2026-12-01|17:30|18:00"
    )
    assignment = Assignment(
        "CSE101", "2026-12-01", "AN", 3, ["S002"]
    )
    hall_assignment = HallAllocator(small_data).allocate([assignment])[0]
    assert hall_assignment.extended_end == "17:20"

    roster = InvigilatorAllocator(small_data).allocate([hall_assignment])
    assert any(
        row["invigilator_id"] == "I001"
        and row["role"] == "INVIGILATOR"
        and row["status"] == "ASSIGNED"
        for row in roster
    )

def test_unavailable_period_overlap_marks_missing_staff(small_data):
    for invigilator in small_data["invigilators"]:
        invigilator["unavailable_periods"] = (
            "2026-12-01|14:00|17:21"
        )
    hall_assignment = HallAssignment(
        date="2026-12-01", session="AN", hall_id="H01",
        courses=["CSE101"], students=["S002"], duration=3,
        extended_end="17:20",
    )

    allocator = InvigilatorAllocator(small_data)
    roster = allocator.allocate([hall_assignment])
    assert any(row["status"] == "UNSTAFFED" for row in roster)
    assert any(v["rule_id"] == "BR-08" for v in allocator.violations)

def test_unstaffed_halls_are_explicit_in_roster(small_data):
    for invigilator in small_data["invigilators"]:
        invigilator["unavailable_dates"] = "2026-12-01"
    hall_assignment = HallAssignment(
        date="2026-12-01", session="FN", hall_id="H01",
        courses=["CSE101"], students=["S001"], duration=3,
    )

    roster = InvigilatorAllocator(small_data).allocate([hall_assignment])
    assert any(
        row["hall_id"] == "H01"
        and row["role"] == "INVIGILATOR"
        and row["status"] == "UNSTAFFED"
        and row["invigilator_id"] == ""
        for row in roster
    )

def test_own_department_is_ineligible_for_every_course_in_merged_hall(small_data):
    small_data["invigilators"][0]["department"] = "CSE"
    hall_assignment = HallAssignment(
        date="2026-12-01", session="FN", hall_id="H01",
        courses=["CSE101", "CSE102"], students=["S001", "S002"], duration=3,
    )

    roster = InvigilatorAllocator(small_data).allocate([hall_assignment])
    assert all(row["invigilator_id"] != "I001" for row in roster)
