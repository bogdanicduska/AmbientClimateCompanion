import requests
from typing import Dict

from app.config import OPENWEATHER_API_KEY, OPENWEATHER_CITY, OPENWEATHER_URL
from app.utils.logger import get_logger

logger = get_logger(__name__)


def fetch_outdoor_weather() -> Dict:
    """
    Fetch current outdoor weather from OpenWeatherMap.
    Returns a dict with outdoor_temp, outdoor_humidity, outdoor_weather, outdoor_icon.
    On failure returns None values so the record is still stored.
    """
    try:
        response = requests.get(
            OPENWEATHER_URL,
            params={
                "q": OPENWEATHER_CITY,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
            },
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()

        return {
            "outdoor_temp":     round(data["main"]["temp"], 1),
            "outdoor_humidity": round(data["main"]["humidity"], 1),
            "outdoor_weather":  data["weather"][0]["description"],
            "outdoor_icon":     data["weather"][0]["icon"],
        }
    except Exception as e:
        logger.error(f"OpenWeatherMap fetch failed: {e}")
        return {
            "outdoor_temp":     None,
            "outdoor_humidity": None,
            "outdoor_weather":  None,
            "outdoor_icon":     None,
        }
