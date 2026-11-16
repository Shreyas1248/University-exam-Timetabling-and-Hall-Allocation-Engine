from engine.models import Assignment
from engine.hall_allocator import HallAllocator

def test_allocator_uses_largest_hall_first(small_data):
    assignment = Assignment(
        course_code="CSE101", date="2026-12-01", session="FN",
        duration=3, students=["S001","S002"]
    )
    result = HallAllocator(small_data).allocate([assignment])
    assert len(result) == 1
    assert result[0].hall_id == "H01"
    assert result[0].students == ["S001","S002"]
