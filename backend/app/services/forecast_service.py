from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from app.utils.logger import get_logger

logger = get_logger(__name__)

FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


def _summarise_day(slots: List[Dict]) -> Dict[str, Any]:
    morning = [s for s in slots
               if 6 <= datetime.fromtimestamp(s["dt"], tz=timezone.utc).hour < 12]

    rain_prob   = max((s.get("pop", 0) for s in slots), default=0)
    morning_rain = any(s.get("pop", 0) > 0.4 for s in morning)
    storm        = any(200 <= s["weather"][0]["id"] < 300 for s in slots)

    return {
        "date":             slots[0]["dt_txt"][:10],
        "temp_min":         round(min(s["main"]["temp_min"] for s in slots), 1),
        "temp_max":         round(max(s["main"]["temp_max"] for s in slots), 1),
        "description":      slots[0]["weather"][0]["description"],
        "icon":             slots[0]["weather"][0]["icon"],
        "rain_probability": round(rain_prob, 2),
        "morning_rain":     morning_rain,
        "storm_warning":    storm,
    }


def fetch_forecast(config) -> Dict[str, Any]:
    response = requests.get(
        FORECAST_URL,
        params={
            "q":     config["OPENWEATHER_CITY"],
            "appid": config["OPENWEATHER_API_KEY"],
            "units": "metric",
            "cnt":   24,
        },
        timeout=5,
    )
    response.raise_for_status()
    items = response.json()["list"]

    days: Dict[str, list] = defaultdict(list)
    for item in items:
        day_key = item["dt_txt"][:10]
        days[day_key].append(item)

    summaries = [_summarise_day(days[k]) for k in sorted(days)[:3]]

    labels = ["today", "tomorrow", "day_after"]
    data: Dict[str, Any] = {labels[i]: summaries[i] for i in range(len(summaries))}
    data["umbrella_needed"] = data.get("today", {}).get("morning_rain", False)
    data["storm_warning"]   = any(s.get("storm_warning") for s in summaries)

    logger.info(
        f"Forecast fetched — umbrella={data['umbrella_needed']}, "
        f"storm={data['storm_warning']}"
    )
    return data
