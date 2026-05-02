from typing import Dict, Any

from app.utils.time_utils import utc_now_iso
from app.utils.logger import get_logger

logger = get_logger(__name__)

VALID_EVENT_TYPES = {
    "wifi_connected", "wifi_disconnected", "wifi_failed",
    "room_online", "room_state_restored", "cache_loaded", "boot_recovered",
    "room_synced", "room_sync_failed",
    "humidity_alert", "air_quality_alert", "motion_triggered",
    "announcement_spoken", "speech_query_received", "speech_summary_spoken",
}


def store_device_event(payload: Dict[str, Any], config) -> Dict[str, Any]:
    from app.services.bigquery_service import insert_event_row

    row = {
        "device_id":  payload["device_id"],
        "event_type": payload["event_type"],
        "timestamp":  payload.get("timestamp") or utc_now_iso(),
        "details":    str(payload["details"]) if payload.get("details") is not None else None,
        "logged_at":  utc_now_iso(),
    }

    insert_event_row(row, config)
    return row
