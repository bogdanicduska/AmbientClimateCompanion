from flask import Blueprint, jsonify, current_app

from app.services.weather_service import fetch_outdoor_weather

weather_bp = Blueprint("weather", __name__)


@weather_bp.get("/weather")
def weather():
    """Return the current outdoor weather from OpenWeatherMap."""
    try:
        data = fetch_outdoor_weather(current_app.config)
        return jsonify({"success": True, "data": data}), 200
    except Exception:
        current_app.logger.exception("Weather fetch failed")
        return jsonify({"success": False, "message": "Failed to fetch weather"}), 500
