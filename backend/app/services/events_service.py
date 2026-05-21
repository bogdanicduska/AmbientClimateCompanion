from typing import Dict, Any

from app.utils.time_utils import utc_now_iso
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Canonical list lives in app.utils.validators.VALID_EVENT_TYPES.
# Add new event types there; validation is enforced by validate_event_payload.


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
