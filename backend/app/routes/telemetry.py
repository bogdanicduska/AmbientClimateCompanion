from flask import Blueprint, jsonify, request, current_app

from app.services.telemetry_service import process_telemetry_payload
from app.services.auth_service import is_valid_device_token
from app.utils.validators import validate_telemetry_payload
from app.utils.logger import get_logger

telemetry_bp = Blueprint("telemetry", __name__)
logger = get_logger(__name__)


@telemetry_bp.post("/telemetry")
def ingest_telemetry():
    """
    Receive sensor data from the M5Stack device and store it in BigQuery.
    The service layer enriches the record with outdoor weather from OpenWeatherMap.
    """
    if not is_valid_device_token(current_app.config):
        logger.warning("Auth failed — invalid device token")
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    device_id = (payload or {}).get("device_id", "unknown")
    logger.info(f"Telemetry received for {device_id}")

    is_valid, error = validate_telemetry_payload(payload)
    if not is_valid:
        logger.warning(f"Payload validation failed for {device_id}: {error}")
        return jsonify({"success": False, "message": error}), 400

    try:
        result = process_telemetry_payload(payload, current_app.config)
        return jsonify({
            "success": True,
            "message": "Telemetry ingested successfully",
            "data": result,
        }), 201
    except Exception:
        current_app.logger.exception(f"Telemetry ingestion failed for {device_id}")
        return jsonify({
            "success": False,
            "message": "Internal server error",
        }), 500
