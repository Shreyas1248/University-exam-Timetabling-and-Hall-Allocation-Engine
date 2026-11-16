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

def test_chief_uses_a_compatible_hall_and_is_reserved_before_hall_staffing(small_data):
    small_data["invigilators"][0]["department"] = "CSE"
    small_data["invigilators"][1]["department"] = "ECE"
    small_data["invigilators"][1]["is_chief_eligible"] = "NO"
    third_invigilator = {
        "invigilator_id": "I003",
        "name": "Invigilator 3",
        "department": "ME",
        "max_sessions_per_week": "5",
        "unavailable_dates": "",
        "is_chief_eligible": "NO",
    }
    small_data["invigilators"].append(third_invigilator)
    small_data["course_by_code"]["CSE102"]["department"] = "ECE"
    halls = [
        {
            "hall_id": "H01", "capacity": "10", "rows": "2",
            "columns": "5", "building": "B1", "floor": "GROUND",
        },
        {
            "hall_id": "H02", "capacity": "8", "rows": "2",
            "columns": "4", "building": "B1", "floor": "GROUND",
        },
    ]
    small_data["halls"] = halls
    small_data["hall_by_id"] = {hall["hall_id"]: hall for hall in halls}
    assignments = [
        HallAssignment(
            "2026-12-01", "FN", "H01", ["CSE101"], ["S001"], 3
        ),
        HallAssignment(
            "2026-12-01", "FN", "H02", ["CSE102"], ["S002"], 2
        ),
    ]

    roster = InvigilatorAllocator(small_data).allocate(assignments)

    assert any(
        row["role"] == "CHIEF"
        and row["hall_id"] == "H02"
        and row["invigilator_id"] == "I001"
        and row["status"] == "ASSIGNED"
        for row in roster
    )
    assert not any(
        row["role"] == "INVIGILATOR" and row["invigilator_id"] == "I001"
        for row in roster
    )
