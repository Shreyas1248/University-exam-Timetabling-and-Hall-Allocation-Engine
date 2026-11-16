from engine.models import HallAssignment
from engine.invigilator_allocator import InvigilatorAllocator

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
