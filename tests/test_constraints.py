from engine.constraint_checker import ConstraintChecker

def test_same_student_cannot_have_same_session_clash(small_data):
    checker = ConstraintChecker(small_data)
    first = small_data["course_by_code"]["CSE101"]
    checker.register(first, "2026-12-01", "FN")
    ok, _, reason = checker.can_assign(
        small_data["course_by_code"]["CSE102"], "2026-12-01", "FN", []
    )
    assert not ok
    assert "session clash" in reason

def test_same_student_cannot_have_second_exam_same_day(small_data):
    checker = ConstraintChecker(small_data)
    first = small_data["course_by_code"]["CSE101"]
    checker.register(first, "2026-12-01", "FN")
    ok, _, reason = checker.can_assign(
        small_data["course_by_code"]["CSE102"], "2026-12-01", "AN", []
    )
    assert not ok
    assert "one exam per day" in reason
