# WHOOP for Room — core metric definitions
#
# Room Readiness:  how supportive the room is for active use, focus,
#                  and comfortable presence. (0-100)
# Recovery Score:  how supportive the room is for calm, rest, and
#                  recovery-like conditions. (0-100)
# Air Strain:      how heavy, stale, or environmentally stressed the
#                  room feels. (0-100)
# Room State:      human-readable label summarising the room's current
#                  condition (Fresh / Calm / Dry / Heavy / Social /
#                  Sleep-Friendly / Restless).
#
# These metrics are environmental interpretation metrics — they do not
# claim to measure human biology directly.

from typing import Dict, Any

from app.services.weather_service import fetch_outdoor_weather
from app.utils.logger import get_logger
from app.utils.time_utils import utc_now_str, utc_now_iso

logger = get_logger(__name__)


def _air_quality_label(raw: float) -> str:
    """Derive a human-readable label from the raw air quality sensor value."""
    if raw < 100:
        return "Good"
    elif raw < 150:
        return "Moderate"
    elif raw < 200:
        return "Poor"
    return "Hazardous"


def process_telemetry_payload(payload: Dict[str, Any], config) -> Dict[str, Any]:
    """
    Normalize payload, enrich with outdoor weather and ingested_at,
    then insert into BigQuery. Returns the full stored record.
    """
    from app.services.bigquery_service import insert_telemetry_row

    outdoor = fetch_outdoor_weather(config)
    air_quality = float(payload["air_quality"]) if payload.get("air_quality") is not None else None

    row = {
        "device_id":         payload["device_id"],
        "timestamp":         payload.get("timestamp") or utc_now_str(),
        "indoor_temp":       float(payload["indoor_temp"]),
        "indoor_humidity":   float(payload["indoor_humidity"]),
        "air_quality":       air_quality,
        "air_quality_label": _air_quality_label(air_quality) if air_quality is not None else None,
        "motion":            bool(payload["motion"]) if payload.get("motion") is not None else None,
        "wifi_rssi":         payload.get("wifi_rssi"),
        "indoor_pressure":   payload.get("indoor_pressure"),
        "indoor_eco2":       payload.get("indoor_eco2"),
        "ingested_at":       utc_now_iso(),
        "sync_status":       "ok",
        **outdoor,
    }

    insert_telemetry_row(row, config)
    logger.info(f"Ingested — device={row['device_id']}, temp={row['indoor_temp']}°C, humidity={row['indoor_humidity']}%")
    return row
