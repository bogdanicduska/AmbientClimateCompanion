from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


# Each trigger: id, condition(snapshot, hour_utc) -> bool, spoken text, cooldown hours.
# Triggers are evaluated in order. First match wins.
# Order matters: more urgent / rarer triggers first so they aren't drowned out.
PROACTIVE_TRIGGERS: List[Dict[str, Any]] = [
    {
        "id":             "air_strain_rising",
        "check":          lambda s, hour: s.get("air_strain", 0) >= 65,
        "text":           "Air strain is rising. Consider opening a window.",
        "cooldown_hours": 2,
    },
    {
        "id":             "dry_air",
        "check":          lambda s, hour: (s.get("indoor_humidity") or 100) < 38,
        "text":           "The room air is dry right now. Humidity is below 40 percent.",
        "cooldown_hours": 3,
    },
    {
        "id":             "recovery_good_evening",
        # 8 PM–11 PM UTC ≈ 10 PM–1 AM local for a UTC+2 device
        "check":          lambda s, hour: s.get("recovery_score", 0) >= 75 and 20 <= hour <= 23,
        "text":           "Recovery conditions are good this evening. Temperature and air are both in range.",
        "cooldown_hours": 4,
    },
    {
        "id":             "rain_tomorrow_morning",
        "check":          lambda s, hour: s.get("forecast_morning_rain") is True,
        "text":           "Rain is expected tomorrow morning. You may want to bring an umbrella.",
        "cooldown_hours": 12,
    },
]


def _was_recently_spoken(device_id: str, trigger_id: str, cooldown_hours: int, config) -> bool:
    """Look up recent speech_summary_spoken events and check for a matching trigger_id in details."""
    from app.services.bigquery_service import get_recent_speech_events
    try:
        events = get_recent_speech_events(
            device_id, "speech_summary_spoken", config, hours=cooldown_hours,
        )
    except Exception as exc:
        logger.warning(f"Cooldown lookup failed for {trigger_id}: {exc} — assuming not recently spoken")
        return False

    for ev in events:
        details = ev.get("details") or ""
        if trigger_id in details:
            return True
    return False


def _attach_forecast(snapshot: Dict[str, Any], config) -> Dict[str, Any]:
    """Decorate the snapshot with forecast flags the rain trigger needs."""
    try:
        from app.services.forecast_service import fetch_forecast
        forecast = fetch_forecast(config)
        tomorrow = forecast.get("tomorrow", {})
        snapshot["forecast_morning_rain"] = bool(tomorrow.get("morning_rain"))
        snapshot["forecast_storm"]        = bool(forecast.get("storm_warning"))
    except Exception as exc:
        logger.warning(f"Forecast attach failed: {exc} — rain trigger will be skipped")
        snapshot["forecast_morning_rain"] = False
        snapshot["forecast_storm"]        = False
    return snapshot


def _snapshot_fields(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "room_readiness":  snapshot.get("room_readiness"),
        "recovery_score":  snapshot.get("recovery_score"),
        "air_strain":      snapshot.get("air_strain"),
        "indoor_humidity": snapshot.get("indoor_humidity"),
        "room_state":      snapshot.get("room_state"),
    }


def evaluate_proactive(device_id: str, config, force_trigger: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Return one trigger to speak (first match in order), or None if nothing fires.
    If force_trigger is provided, that trigger is returned unconditionally — condition
    checks and cooldowns are bypassed. Useful for demos and end-to-end testing.
    """
    from app.services.bigquery_service import get_latest_reading
    from app.services.room_metrics_service import enrich_row

    row = get_latest_reading(device_id, config)
    snapshot: Dict[str, Any] = enrich_row(row) if row else {}
    snapshot = _attach_forecast(snapshot, config)

    # ----- Forced trigger (demo / testing) -----
    if force_trigger:
        forced = next((t for t in PROACTIVE_TRIGGERS if t["id"] == force_trigger), None)
        if not forced:
            valid = [t["id"] for t in PROACTIVE_TRIGGERS]
            raise ValueError(f"Unknown trigger '{force_trigger}'. Valid: {valid}")
        logger.info(f"Proactive forced trigger: {force_trigger}")
        return {
            "trigger_id":     forced["id"],
            "text":           forced["text"],
            "cooldown_hours": forced["cooldown_hours"],
            "forced":         True,
            "snapshot":       _snapshot_fields(snapshot),
        }

    if not row:
        logger.info(f"Proactive skip — no latest reading for {device_id}")
        return None

    hour_utc = datetime.now(timezone.utc).hour

    for trigger in PROACTIVE_TRIGGERS:
        try:
            if not trigger["check"](snapshot, hour_utc):
                continue
        except Exception as exc:
            logger.warning(f"Trigger {trigger['id']} check raised: {exc}")
            continue

        if _was_recently_spoken(device_id, trigger["id"], trigger["cooldown_hours"], config):
            logger.info(f"Trigger {trigger['id']} in cooldown — skipping")
            continue

        logger.info(f"Proactive trigger fired: {trigger['id']}")
        return {
            "trigger_id":     trigger["id"],
            "text":           trigger["text"],
            "cooldown_hours": trigger["cooldown_hours"],
            "forced":         False,
            "snapshot":       _snapshot_fields(snapshot),
        }

    return None
