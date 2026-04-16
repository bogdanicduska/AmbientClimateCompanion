from typing import Dict, Any

import requests

from app.utils.logger import get_logger

logger = get_logger(__name__)


def fetch_outdoor_weather(config) -> Dict[str, Any]:
    """
    Fetch current outdoor weather from OpenWeatherMap.
    Returns normalized outdoor fields plus weather_status.
    On failure returns None values so the telemetry record is still stored.
    """
    try:
        response = requests.get(
            config["OPENWEATHER_URL"],
            params={
                "q":     config["OPENWEATHER_CITY"],
                "appid": config["OPENWEATHER_API_KEY"],
                "units": "metric",
            },
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        logger.info(f"Weather fetch successful — {config['OPENWEATHER_CITY']}: {data['weather'][0]['description']}, {data['main']['temp']}°C")

        return {
            "outdoor_temp":     round(data["main"]["temp"], 1),
            "outdoor_humidity": round(data["main"]["humidity"], 1),
            "outdoor_weather":  data["weather"][0]["description"],
            "outdoor_icon":     data["weather"][0]["icon"],
            "weather_status":   "live",
        }
    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        return {
            "outdoor_temp":     None,
            "outdoor_humidity": None,
            "outdoor_weather":  None,
            "outdoor_icon":     None,
            "weather_status":   "unavailable",
        }
