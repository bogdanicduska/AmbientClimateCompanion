from datetime import datetime, timezone
from typing import Dict, Any

import requests

from app.utils.logger import get_logger

logger = get_logger(__name__)


def process_telemetry_payload(payload: Dict[str, Any], config) -> Dict[str, Any]:
    """
    Normalize payload, enrich with outdoor weather and ingested_at,
    then insert into BigQuery. Returns the full stored record.
    """
    from app.services.bigquery_service import insert_indoor_reading

    outdoor = fetch_outdoor_weather(config)

    row = {
        "device_id":       payload["device_id"],
        "timestamp":       payload.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "indoor_temp":     float(payload["indoor_temp"]),
        "indoor_humidity": float(payload["indoor_humidity"]),
        "air_quality":     float(payload["air_quality"]) if payload.get("air_quality") is not None else None,
        "motion":          bool(payload["motion"]) if payload.get("motion") is not None else None,
        "wifi_rssi":       payload.get("wifi_rssi"),
        "indoor_pressure": payload.get("indoor_pressure"),
        "indoor_eco2":     payload.get("indoor_eco2"),
        "ingested_at":     datetime.now(timezone.utc).isoformat(),
        **outdoor,
    }

    insert_indoor_reading(row, config)
    logger.info(f"Ingested — device={row['device_id']}, temp={row['indoor_temp']}°C, humidity={row['indoor_humidity']}%")
    return row


def fetch_outdoor_weather(config) -> Dict[str, Any]:
    """
    Fetch current outdoor weather from OpenWeatherMap.
    Returns outdoor fields; all None on failure so the record is still stored.
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
