from app.utils.validators import validate_telemetry_payload


VALID_PAYLOAD = {
    "device_id": "core2-livingroom",
    "timestamp": "2026-04-08T10:30:00Z",
    "indoor_temp": 22.1,
    "indoor_humidity": 45.0,
    "air_quality": 120.0,
    "motion": True,
    "wifi_rssi": -61,
}


def test_valid_payload_passes():
    is_valid, error = validate_telemetry_payload(VALID_PAYLOAD)
    assert is_valid is True
    assert error is None


def test_none_payload_fails():
    is_valid, error = validate_telemetry_payload(None)
    assert is_valid is False
    assert "valid JSON" in error


def test_missing_device_id_fails():
    payload = {**VALID_PAYLOAD}
    del payload["device_id"]
    is_valid, error = validate_telemetry_payload(payload)
    assert is_valid is False
    assert "device_id" in error


def test_missing_indoor_temp_fails():
    payload = {**VALID_PAYLOAD}
    del payload["indoor_temp"]
    is_valid, error = validate_telemetry_payload(payload)
    assert is_valid is False
    assert "indoor_temp" in error


def test_missing_indoor_humidity_fails():
    payload = {**VALID_PAYLOAD}
    del payload["indoor_humidity"]
    is_valid, error = validate_telemetry_payload(payload)
    assert is_valid is False
    assert "indoor_humidity" in error


def test_empty_device_id_fails():
    payload = {**VALID_PAYLOAD, "device_id": "   "}
    is_valid, error = validate_telemetry_payload(payload)
    assert is_valid is False
    assert "device_id" in error


def test_humidity_out_of_range_fails():
    payload = {**VALID_PAYLOAD, "indoor_humidity": 150.0}
    is_valid, error = validate_telemetry_payload(payload)
    assert is_valid is False
    assert "indoor_humidity" in error


def test_non_numeric_temp_fails():
    payload = {**VALID_PAYLOAD, "indoor_temp": "hot"}
    is_valid, error = validate_telemetry_payload(payload)
    assert is_valid is False
    assert "numeric" in error


def test_optional_fields_not_required():
    payload = {
        "device_id": "core2-livingroom",
        "indoor_temp": 22.1,
        "indoor_humidity": 45.0,
    }
    is_valid, error = validate_telemetry_payload(payload)
    assert is_valid is True
    assert error is None
