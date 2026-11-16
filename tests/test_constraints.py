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

def test_core_exams_need_one_full_calendar_day_between_them(small_data):
    checker = ConstraintChecker(small_data)
    existing = small_data["course_by_code"]["CSE101"]
    candidate = small_data["course_by_code"]["CSE102"]
    candidate["credits"] = "4"
    assignment = type("Scheduled", (), {
        "course_code": "CSE101",
        "date": "2026-12-01",
        "session": "FN",
        "students": ["S002"],
    })()

    ok, _, reason = checker.can_assign(
        candidate, "2026-12-02", "AN", [assignment]
    )
    assert not ok
    assert reason == "core-course gap rule"

    ok, _, _ = checker.can_assign(
        candidate, "2026-12-03", "AN", [assignment]
    )
    assert ok

def test_gap_fallback_is_recorded_as_soft_br02(small_data):
    checker = ConstraintChecker(small_data)
    candidate = small_data["course_by_code"]["CSE102"]
    candidate["credits"] = "4"
    assignment = type("Scheduled", (), {
        "course_code": "CSE101",
        "date": "2026-12-01",
        "session": "FN",
        "students": ["S001", "S002"],
    })()

    ok, soft, _ = checker.can_assign(
        candidate, "2026-12-02", "AN", [assignment],
        allow_gap_violation=True,
    )
    assert ok
    assert soft == [
        "BR-02: core exams have fewer than one full day between them"
    ]

def test_backlog_consent_never_allows_a_third_exam_in_one_day(small_data):
    small_data["course_by_code"]["CSE101"]["exam_type"] = "BACKLOG"
    small_data["student_by_id"]["S001"]["backlog_consent"] = "YES"
    small_data["course_by_code"]["CSE103"] = {
        "course_code": "CSE103",
        "department": "CSE",
        "semester": "1",
        "credits": "2",
        "exam_duration_hours": "2",
        "exam_type": "BACKLOG",
    }
    small_data["course_students"]["CSE103"] = ["S001"]
    assignments = [
        type("Scheduled", (), {
            "course_code": "CSE101",
            "date": "2026-12-01",
            "session": "FN",
            "students": ["S001"],
        })(),
        type("Scheduled", (), {
            "course_code": "CSE102",
            "date": "2026-12-01",
            "session": "AN",
            "students": ["S001"],
        })(),
    ]

    ok, _, reason = ConstraintChecker(small_data).can_assign(
        small_data["course_by_code"]["CSE103"],
        "2026-12-01",
        "FN",
        assignments,
    )
    assert not ok
    assert "exceeds two exams per day" in reason
