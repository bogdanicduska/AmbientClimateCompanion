from datetime import datetime
from typing import Any, Tuple, Optional

REQUIRED_FIELDS = ("device_id", "indoor_temp", "indoor_humidity")

VALID_EVENT_TYPES = {
    # connectivity
    "wifi_connected",
    "wifi_disconnected",
    "wifi_failed",
    # lifecycle
    "room_online",
    "room_state_restored",
    "cache_loaded",
    "boot_recovered",
    # telemetry
    "room_synced",
    "room_sync_failed",
    # alerts
    "humidity_alert",
    "air_quality_alert",
    "motion_triggered",
    # speech
    "announcement_spoken",
    "speech_query_received",
    "speech_summary_spoken",
}


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


def validate_event_payload(payload: Any) -> Tuple[bool, Optional[str]]:
    if payload is None:
        return False, "Request body must be valid JSON"

    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object"

    if not payload.get("device_id") or not str(payload["device_id"]).strip():
        return False, "Missing required field: 'device_id'"

    event_type = payload.get("event_type")
    if not event_type:
        return False, "Missing required field: 'event_type'"

    if event_type not in VALID_EVENT_TYPES:
        return False, f"Unknown event_type '{event_type}'. Valid types: {sorted(VALID_EVENT_TYPES)}"

    if "timestamp" in payload and payload["timestamp"] is not None:
        try:
            datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
        except ValueError:
            return False, "timestamp must be a valid ISO-8601 string"

    return True, None


def validate_ask_payload(payload: Any) -> Tuple[bool, Optional[str]]:
    if payload is None:
        return False, "Request body must be valid JSON"
    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object"
    if not payload.get("device_id") or not str(payload["device_id"]).strip():
        return False, "Missing required field: 'device_id'"
    if not payload.get("question") or not str(payload["question"]).strip():
        return False, "Missing required field: 'question'"
    if len(str(payload["question"])) > 300:
        return False, "question must be 300 characters or fewer"
    return True, None


def validate_tts_payload(payload: Any) -> Tuple[bool, Optional[str]]:
    if payload is None:
        return False, "Request body must be valid JSON"
    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object"
    if not payload.get("device_id") or not str(payload["device_id"]).strip():
        return False, "Missing required field: 'device_id'"
    if not payload.get("text") and not payload.get("template"):
        return False, "Provide either 'text' or 'template'"
    if payload.get("text") and len(str(payload["text"])) > 500:
        return False, "text must be 500 characters or fewer"
    return True, None


def validate_stt_payload(payload: Any) -> Tuple[bool, Optional[str]]:
    if payload is None:
        return False, "Request body must be valid JSON"
    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object"
    if not payload.get("device_id") or not str(payload["device_id"]).strip():
        return False, "Missing required field: 'device_id'"
    if not payload.get("audio_b64"):
        return False, "Missing required field: 'audio_b64'"
    allowed_formats = {"wav", "webm", "raw", "mp3"}
    fmt = str(payload.get("format", "wav")).lower()
    if fmt not in allowed_formats:
        return False, f"format must be one of: {sorted(allowed_formats)}"
    try:
        import base64
        decoded = base64.b64decode(payload["audio_b64"])
        if len(decoded) < 1000:
            return False, "audio_b64 is too short — audio may be empty or corrupt"
    except Exception:
        return False, "audio_b64 must be valid base64"
    return True, None


def validate_query_payload(payload: Any) -> Tuple[bool, Optional[str]]:
    if payload is None:
        return False, "Request body must be valid JSON"
    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object"
    if not payload.get("device_id") or not str(payload["device_id"]).strip():
        return False, "Missing required field: 'device_id'"
    return validate_stt_payload(payload)
