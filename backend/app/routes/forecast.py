from flask import Blueprint, jsonify, current_app

from app.services.forecast_service import fetch_forecast

forecast_bp = Blueprint("forecast", __name__)


@forecast_bp.get("/forecast")
def forecast():
    """Return a 3-day weather forecast with rain and storm flags."""
    try:
        data = fetch_forecast(current_app.config)
        return jsonify({"success": True, "data": data}), 200
    except Exception:
        current_app.logger.exception("Forecast fetch failed")
        return jsonify({"success": False, "message": "Failed to fetch forecast"}), 500
