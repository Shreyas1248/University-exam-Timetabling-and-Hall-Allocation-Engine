from engine.ordering_heuristic import order_courses

def test_courses_sorted_by_enrolment_then_credits_then_code():
    courses = [
        {"course_code":"ZZZ","enrolment_count":"10","credits":"3"},
        {"course_code":"BBB","enrolment_count":"10","credits":"4"},
        {"course_code":"AAA","enrolment_count":"10","credits":"4"},
        {"course_code":"CCC","enrolment_count":"20","credits":"2"},
    ]
    assert [c["course_code"] for c in order_courses(courses)] == [
        "CCC","AAA","BBB","ZZZ"
    ]
