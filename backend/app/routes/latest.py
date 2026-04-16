from flask import Blueprint, jsonify, request, current_app

from app.services.bigquery_service import get_latest_reading
from app.utils.logger import get_logger

latest_bp = Blueprint("latest", __name__)
logger = get_logger(__name__)


@latest_bp.get("/latest")
def latest():
    """Return the most recent record for a given device."""
    device_id = request.args.get("device_id")

    if not device_id:
        return jsonify({"success": False, "message": "device_id is required"}), 400

    logger.info(f"Latest reading requested for {device_id}")

    try:
        row = get_latest_reading(device_id, current_app.config)

        if row is None:
            logger.warning(f"No data found for device {device_id}")
            return jsonify({"success": False, "message": "No data found for this device"}), 404

        return jsonify({"success": True, "data": row}), 200

    except Exception:
        current_app.logger.exception(f"Latest reading query failed for {device_id}")
        return jsonify({"success": False, "message": "Internal server error"}), 500
