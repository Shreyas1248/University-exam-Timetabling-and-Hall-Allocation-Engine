from engine.models import Assignment
from engine.hall_allocator import HallAllocator, pack_courses
from engine.scheduler import ExamScheduler


def _add_course_students(data, course_code, count, prefix):
    ids = []
    for index in range(count):
        student_id = f"{prefix}{index:03d}"
        ids.append(student_id)
        student = {
            "student_id": student_id,
            "register_number": student_id,
            "special_needs": "NO",
        }
        data["student_by_id"][student_id] = student
        data["students"].append(student)
    data["course_students"][course_code] = ids
    data["course_by_code"][course_code]["enrolment_count"] = str(count)
    return ids


def _large_hall(data):
    hall = {
        "hall_id": "H01",
        "capacity": "180",
        "rows": "21",
        "columns": "9",
        "building": "B1",
        "floor": "GROUND",
    }
    data["halls"] = [hall]
    data["hall_by_id"] = {"H01": hall}

def test_allocator_uses_largest_hall_first(small_data):
    _large_hall(small_data)
    students = _add_course_students(small_data, "CSE101", 10, "A")
    assignment = Assignment(
        course_code="CSE101", date="2026-12-01", session="FN",
        duration=3, students=students
    )
    result = HallAllocator(small_data).allocate([assignment])
    assert len(result) == 1
    assert result[0].hall_id == "H01"
    assert result[0].students == students

def test_nine_student_course_must_merge_but_ten_may_stand_alone(small_data):
    _large_hall(small_data)
    nine_students = _add_course_students(small_data, "CSE101", 9, "A")
    small_course = Assignment(
        "CSE101", "2026-12-01", "FN", 3, nine_students
    )
    assert not pack_courses(
        small_data, [small_course], small_data["halls"]
    )

    small_data["course_by_code"]["CSE102"]["department"] = "ECE"
    small_data["course_by_code"]["CSE102"]["exam_duration_hours"] = "3"
    ten_students = _add_course_students(small_data, "CSE102", 10, "B")
    companion = Assignment(
        "CSE102", "2026-12-01", "FN", 3, ten_students
    )
    assert pack_courses(
        small_data, [small_course, companion], small_data["halls"]
    )

    exactly_ten = Assignment(
        "CSE101", "2026-12-02", "FN", 3,
        _add_course_students(small_data, "CSE101", 10, "C"),
    )
    assert pack_courses(
        small_data, [exactly_ten], small_data["halls"]
    )

def test_non_integer_ninety_percent_capacity_threshold_rounds_down(small_data):
    hall = {
        "hall_id": "H01",
        "capacity": "11",
        "rows": "3",
        "columns": "4",
        "building": "B1",
        "floor": "GROUND",
    }
    small_data["halls"] = [hall]
    small_data["hall_by_id"] = {"H01": hall}
    students = _add_course_students(small_data, "CSE101", 10, "D")
    candidate = Assignment(
        "CSE101", "2026-12-01", "FN", 3, students
    )

    assert not ExamScheduler(small_data)._capacity_ok(
        candidate,
        {"date": "2026-12-01", "session": "FN"},
        [],
    )
