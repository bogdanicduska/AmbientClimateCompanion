from flask import Blueprint, jsonify, request, current_app

from app.services.events_service import store_device_event
from app.services.auth_service import is_valid_device_token
from app.utils.validators import validate_event_payload
from app.utils.logger import get_logger

events_bp = Blueprint("events", __name__)
logger = get_logger(__name__)


@events_bp.post("/events")
def ingest_event():
    if not is_valid_device_token(current_app.config):
        logger.warning("Auth failed — invalid device token on event ingest")
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True)

    is_valid, error = validate_event_payload(payload)
    if not is_valid:
        logger.warning(f"Event payload validation failed: {error}")
        return jsonify({"success": False, "message": error}), 400

    try:
        result = store_device_event(payload, current_app.config)
        logger.info(f"Event stored — device={result['device_id']}, type={result['event_type']}")
        return jsonify({"success": True, "data": result}), 201
    except Exception:
        current_app.logger.exception("Event ingest failed")
        return jsonify({"success": False, "message": "Internal server error"}), 500
