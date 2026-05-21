"""
Outdoor weather fetching with a lightweight in-process cache.

The M5Stack sends telemetry every 5 minutes. Without caching,
every ingest would hit OpenWeatherMap — up to 576 calls/day per
device, easily exhausting the free-tier quota (1 000 calls/day).

Cache TTL: 5 minutes (CACHE_TTL_SECONDS). The cache is per-process,
so a Cloud Run cold start resets it (acceptable — first call after
a cold start fetches fresh data and then the cache holds).
"""

import time
from typing import Dict, Any

import requests

from app.utils.logger import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutes

_cache: Dict[str, Any] = {}   # keyed by city name
_cache_ts: Dict[str, float] = {}


def _null_weather() -> Dict[str, Any]:
    return {
        "outdoor_temp":     None,
        "outdoor_humidity": None,
        "outdoor_weather":  None,
        "outdoor_icon":     None,
        "weather_status":   "unavailable",
    }


def fetch_outdoor_weather(config) -> Dict[str, Any]:
    """
    Return current outdoor weather for the configured city.
    Results are cached for CACHE_TTL_SECONDS to avoid hitting
    the OpenWeatherMap API on every telemetry ingest.
    Falls back to None-valued dict so the telemetry record is
    still stored even when the API is unavailable.
    """
    city = config.get("OPENWEATHER_CITY", "")
    now  = time.monotonic()

    # Return cached result if still fresh
    if city in _cache and (now - _cache_ts.get(city, 0)) < CACHE_TTL_SECONDS:
        logger.debug(f"Weather cache hit for {city}")
        return _cache[city]

    try:
        response = requests.get(
            config["OPENWEATHER_URL"],
            params={
                "q":     city,
                "appid": config["OPENWEATHER_API_KEY"],
                "units": "metric",
            },
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()

        result = {
            "outdoor_temp":     round(data["main"]["temp"], 1),
            "outdoor_humidity": round(data["main"]["humidity"], 1),
            "outdoor_weather":  data["weather"][0]["description"],
            "outdoor_icon":     data["weather"][0]["icon"],
            "weather_status":   "live",
        }
        _cache[city]    = result
        _cache_ts[city] = now
        logger.info(
            f"Weather fetched — {city}: {result['outdoor_weather']}, "
            f"{result['outdoor_temp']}°C (cached for {CACHE_TTL_SECONDS}s)"
        )
        return result

    except Exception as e:
        logger.error(f"Weather fetch failed for {city}: {e}")
        # Return stale cache if available rather than all-None
        if city in _cache:
            logger.warning(f"Returning stale cached weather for {city}")
            return {**_cache[city], "weather_status": "stale"}
        return _null_weather()
