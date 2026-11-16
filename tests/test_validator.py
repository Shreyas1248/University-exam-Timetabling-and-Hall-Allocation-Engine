from engine.validator import DataValidator

def test_validator_accepts_valid_small_dataset(small_data):
    result = DataValidator().validate(small_data)
    assert result["valid"]
    assert result["errors"] == []

def test_validator_rejects_invalid_duration(small_data):
    small_data["courses"][0]["exam_duration_hours"] = "5"
    result = DataValidator().validate(small_data)
    assert not result["valid"]
    assert any("duration must be 2 or 3" in e for e in result["errors"])

def test_validator_rejects_duplicate_exam_window_slot(small_data):
    small_data["exam_window"].append(dict(small_data["exam_window"][0]))
    result = DataValidator().validate(small_data)
    assert not result["valid"]
    assert any("Duplicate exam-window session" in e for e in result["errors"])

def test_validator_rejects_hall_capacity_larger_than_seat_grid(small_data):
    small_data["halls"][0]["capacity"] = "11"
    result = DataValidator().validate(small_data)
    assert not result["valid"]
    assert any("capacity exceeds rows x columns" in e for e in result["errors"])
