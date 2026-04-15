from datetime import datetime
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

    if "air_quality" in payload and payload["air_quality"] is not None:
        try:
            float(payload["air_quality"])
        except (ValueError, TypeError):
            return False, "air_quality must be numeric"

    if "motion" in payload and payload["motion"] is not None:
        if not isinstance(payload["motion"], bool):
            return False, "motion must be a boolean"

    if "timestamp" in payload and payload["timestamp"] is not None:
        try:
            datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
        except ValueError:
            return False, "timestamp must be a valid ISO-8601 string"

    return True, None
