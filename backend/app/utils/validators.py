from typing import Any, Tuple, Optional

REQUIRED_FIELDS = ("device_id", "indoor_temp", "indoor_humidity")


def validate_telemetry_payload(payload: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate the raw JSON payload from the M5Stack device.

    Returns (True, None) when valid.
    Returns (False, error_message) when invalid.
    """
    if payload is None:
        return False, "Request body must be valid JSON"

    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object"

    for field in REQUIRED_FIELDS:
        if field not in payload:
            return False, f"Missing required field: '{field}'"

    if not isinstance(payload["device_id"], str) or not payload["device_id"].strip():
        return False, "device_id must be a non-empty string"

    try:
        float(payload["indoor_temp"])
        float(payload["indoor_humidity"])
    except (ValueError, TypeError):
        return False, "indoor_temp and indoor_humidity must be numeric"

    if not (0.0 <= float(payload["indoor_humidity"]) <= 100.0):
        return False, "indoor_humidity must be between 0 and 100"

    return True, None
