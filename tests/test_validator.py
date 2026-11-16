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
