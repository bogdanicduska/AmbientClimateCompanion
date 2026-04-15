from flask import Blueprint, jsonify, request, current_app

from app.services.telemetry_service import process_telemetry_payload
from app.services.auth_service import is_valid_device_token
from app.utils.validators import validate_telemetry_payload

telemetry_bp = Blueprint("telemetry", __name__)


@telemetry_bp.post("/telemetry")
def ingest_telemetry():
    """
    Receive sensor data from the M5Stack device and store it in BigQuery.
    The service layer enriches the record with outdoor weather from OpenWeatherMap.
    """
    if not is_valid_device_token(current_app.config):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True)

    is_valid, error = validate_telemetry_payload(payload)
    if not is_valid:
        return jsonify({"success": False, "message": error}), 400

    try:
        result = process_telemetry_payload(payload, current_app.config)
        return jsonify({
            "success": True,
            "message": "Telemetry ingested successfully",
            "data": result,
        }), 201
    except Exception:
        current_app.logger.exception("Telemetry ingestion failed")
        return jsonify({
            "success": False,
            "message": "Internal server error",
        }), 500
