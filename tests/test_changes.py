from engine.models import Assignment
from engine.change_manager import ChangeManager

def test_postpone_moves_course_to_later_available_session(small_data):
    assignment = Assignment(
        course_code="CSE101", date="2026-12-01", session="FN",
        duration=3, students=["S001","S002"]
    )
    manager = ChangeManager(small_data, [assignment])
    result = manager.postpone("CSE101")
    assert result["status"] == "POSTPONED"
    assert (assignment.date, assignment.session) > ("2026-12-01","FN")

def test_unknown_course_is_rejected(small_data):
    manager = ChangeManager(small_data, [])
    result = manager.postpone("NO_SUCH_COURSE")
    assert result["status"] == "REJECTED_UNKNOWN_COURSE"
