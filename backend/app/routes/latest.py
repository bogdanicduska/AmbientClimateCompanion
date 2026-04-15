from flask import Blueprint, jsonify, request, current_app

from app.services.bigquery_service import get_latest_reading, get_history

latest_bp = Blueprint("latest", __name__)


@latest_bp.get("/latest")
def latest():
    """Return the most recent record for a given device."""
    device_id = request.args.get("device_id")

    if not device_id:
        return jsonify({"success": False, "message": "device_id is required"}), 400

    try:
        row = get_latest_reading(device_id, current_app.config)

        if row is None:
            return jsonify({"success": False, "message": "No data found for this device"}), 404

        return jsonify({"success": True, "data": row}), 200

    except Exception:
        current_app.logger.exception("Latest reading query failed")
        return jsonify({"success": False, "message": "Internal server error"}), 500


@latest_bp.get("/history")
def history():
    """Return all records for a device from the last N days (default 7, max 30)."""
    device_id = request.args.get("device_id")

    if not device_id:
        return jsonify({"success": False, "message": "device_id is required"}), 400

    try:
        days = int(request.args.get("days", 7))
        if not (1 <= days <= 30):
            raise ValueError
    except ValueError:
        return jsonify({"success": False, "message": "days must be an integer between 1 and 30"}), 400

    try:
        records = get_history(device_id, current_app.config, days=days)
        return jsonify({"success": True, "count": len(records), "data": records}), 200

    except Exception:
        current_app.logger.exception("History query failed")
        return jsonify({"success": False, "message": "Internal server error"}), 500
