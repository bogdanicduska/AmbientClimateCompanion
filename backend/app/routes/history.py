from flask import Blueprint, jsonify, request, current_app

from app.services.bigquery_service import get_history

history_bp = Blueprint("history", __name__)


@history_bp.get("/history")
def history():
    """Return records for a device from the last N hours (default 24, max 168)."""
    device_id = request.args.get("device_id")

    if not device_id:
        return jsonify({"success": False, "message": "device_id is required"}), 400

    try:
        hours = int(request.args.get("hours", 24))
        if not (1 <= hours <= 168):
            raise ValueError
    except ValueError:
        return jsonify({"success": False, "message": "hours must be an integer between 1 and 168"}), 400

    try:
        records = get_history(device_id, current_app.config, hours=hours)
        return jsonify({"success": True, "count": len(records), "data": records}), 200

    except Exception:
        current_app.logger.exception("History query failed")
        return jsonify({"success": False, "message": "Internal server error"}), 500
