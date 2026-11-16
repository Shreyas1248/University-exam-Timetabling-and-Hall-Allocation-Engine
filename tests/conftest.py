import pytest

@pytest.fixture
def small_data():
    courses = [
        {"course_code":"CSE101","department":"CSE","semester":"1","credits":"4",
         "exam_duration_hours":"3","exam_type":"REGULAR","enrolment_count":"2"},
        {"course_code":"CSE102","department":"CSE","semester":"1","credits":"3",
         "exam_duration_hours":"2","exam_type":"REGULAR","enrolment_count":"1"},
    ]
    students = [
        {"student_id":"S001","register_number":"S001","name":"Student 1",
         "department":"CSE","programme":"CSE","semester":"1",
         "special_needs":"NO","backlog_consent":"NO"},
        {"student_id":"S002","register_number":"S002","name":"Student 2",
         "department":"CSE","programme":"CSE","semester":"1",
         "special_needs":"YES","backlog_consent":"NO"},
    ]
    halls = [
        {"hall_id":"H01","capacity":"10","rows":"2","columns":"5",
         "building":"B1","floor":"GROUND"},
        {"hall_id":"H02","capacity":"8","rows":"2","columns":"4",
         "building":"B1","floor":"FIRST"},
    ]
    invigilators = [
        {"invigilator_id":"I001","name":"Invigilator 1","department":"ECE",
         "max_sessions_per_week":"5","unavailable_dates":"","is_chief_eligible":"YES"},
        {"invigilator_id":"I002","name":"Invigilator 2","department":"ME",
         "max_sessions_per_week":"5","unavailable_dates":"","is_chief_eligible":"YES"},
    ]
    return {
        "courses": courses,
        "students": students,
        "enrolments": [
            {"course_code":"CSE101","student_id":"S001","enrolment_type":"REGULAR"},
            {"course_code":"CSE101","student_id":"S002","enrolment_type":"REGULAR"},
            {"course_code":"CSE102","student_id":"S001","enrolment_type":"REGULAR"},
        ],
        "halls": halls,
        "invigilators": invigilators,
        "exam_window": [
            {"date":"2026-12-01","session":"FN","start_time":"09:30","end_time":"12:30","available":"YES"},
            {"date":"2026-12-01","session":"AN","start_time":"14:00","end_time":"17:00","available":"YES"},
            {"date":"2026-12-02","session":"FN","start_time":"09:30","end_time":"12:30","available":"YES"},
            {"date":"2026-12-02","session":"AN","start_time":"14:00","end_time":"17:00","available":"YES"},
        ],
        "holidays": [],
        "course_by_code": {c["course_code"]:c for c in courses},
        "student_by_id": {s["student_id"]:s for s in students},
        "course_students": {"CSE101":["S001","S002"],"CSE102":["S001"]},
        "student_courses": {"S001":["CSE101","CSE102"],"S002":["CSE101"]},
        "hall_by_id": {"H01":halls[0],"H02":halls[1]},
        "invigilator_by_id": {"I001":invigilators[0],"I002":invigilators[1]},
    }
