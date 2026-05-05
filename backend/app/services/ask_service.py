import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Tuple

from app.utils.logger import get_logger
from app.services.room_metrics_service import enrich_row, compute_recovery_score

logger = get_logger(__name__)

# Each entry: (intent_id, list_of_regex_patterns)
_INTENT_PATTERNS = [
    ("temp_yesterday",       [r"temp.*yesterday", r"yesterday.*temp"]),
    ("humidity_threshold",   [r"humidity.*(exceed|over|above|hit|pass|high)", r"(exceed|over|above).*(humidity|percent)"]),
    ("current_recovery",     [r"how.*(recovery|rest|calm)", r"(current|now|tonight).*(recovery|rest|calm)", r"recovery.*(now|current|tonight|score|right.?now)"]),
    ("recovery_lastnight",   [r"recovery.*(last.?night|overnight|last.?evening)", r"(last.?night|overnight|last.?evening).*(recovery|sleep|rest|calm)", r"(was|were).*(room|night).*(recovery|rest)"]),
    ("peak_comfort",         [r"most.?comfort", r"best.?condition", r"when.*comfort", r"when.*best"]),
    ("air_strain_peak",      [r"air.?strain.*(peak|high|worst|max|rise|rising)", r"(peak|high|worst|max).*air.?strain", r"when.*strained", r"when.*heavy"]),
    ("current_readiness",    [r"readiness", r"room.*ready", r"ready.*(now|today|currently)", r"focus.*room", r"productive"]),
    ("current_air",          [r"air.*(quality|right.?now|currently|like|now)", r"how.*air", r"tvoc", r"co2", r"voc"]),
    ("rain_tomorrow",        [r"rain.*(tomorrow|morning)", r"(tomorrow|morning).*(rain|wet)", r"will.*rain", r"going.*rain"]),
    ("umbrella",             [r"umbrella", r"bring.*(jacket|coat|rain)", r"need.*(jacket|coat)"]),
]


def detect_intent(question: str) -> str:
    q = question.lower()
    for intent, patterns in _INTENT_PATTERNS:
        for pat in patterns:
            if re.search(pat, q):
                return intent
    return "unknown"


def answer_question(device_id: str, question: str, config) -> Dict[str, Any]:
    intent = detect_intent(question)
    logger.info(f"ASK intent={intent!r} question={question!r}")

    if intent == "unknown":
        return _answer_via_agent(device_id, question, config)

    try:
        answer, snapshot = _build_answer(device_id, intent, question, config)
    except Exception as exc:
        logger.error(f"ASK build_answer failed for intent={intent}: {exc}")
        answer   = "I could not retrieve that data right now. Please try again."
        snapshot = {}

    return {
        "intent":        intent,
        "answer_source": "regex",
        "answer":        answer,
        "data_snapshot": snapshot,
    }


def _answer_via_agent(device_id: str, question: str, config) -> Dict[str, Any]:
    """Open-ended questions that didn't match a regex intent go to the
    OpenAI agent. On any failure (no key, timeout, API error) we fall back
    to the original generic deflection so the device always gets an
    answer."""
    try:
        from app.services.agent_service import agent_answer
        answer, snapshot = agent_answer(device_id, question, config)
    except Exception as exc:
        logger.error(f"ASK agent unavailable: {exc}")
        answer, snapshot = None, {}

    if not answer:
        return {
            "intent":        "unknown",
            "answer_source": "fallback",
            "answer":        "I am not sure how to answer that. Try asking about temperature, humidity, air quality, or recovery.",
            "data_snapshot": {},
        }

    return {
        "intent":        "agent",
        "answer_source": "agent",
        "answer":        answer,
        "data_snapshot": snapshot,
    }


# ---------------------------------------------------------------------------
# Answer builders
# ---------------------------------------------------------------------------

def _build_answer(device_id: str, intent: str, question: str, config) -> Tuple[str, Dict]:
    from app.services.bigquery_service import get_latest_reading, get_history
    from app.services.forecast_service import fetch_forecast

    if intent == "temp_yesterday":
        rows = get_history(device_id, config, hours=48)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        yesterday = [r for r in rows if _parse_ts(r["timestamp"]) < cutoff]
        if not yesterday:
            return "I do not have temperature data from yesterday.", {}
        temps = [r["indoor_temp"] for r in yesterday if r.get("indoor_temp") is not None]
        if not temps:
            return "Yesterday's temperature data is incomplete.", {}
        peak = max(temps)
        low  = min(temps)
        peak_row = next(r for r in yesterday if r["indoor_temp"] == peak)
        return (
            f"Yesterday the temperature peaked at {peak:.1f}°C at {_fmt_time(peak_row['timestamp'])} "
            f"and dropped to {low:.1f}°C.",
            {"peak_temp": peak, "low_temp": low, "records": len(yesterday)},
        )

    if intent == "humidity_threshold":
        rows = get_history(device_id, config, hours=24)
        threshold = _extract_threshold(question)
        if not rows:
            return "I do not have humidity data for the past 24 hours.", {}
        values = [r["indoor_humidity"] for r in rows if r.get("indoor_humidity") is not None]
        if not values:
            return "Humidity data is unavailable right now.", {}
        max_val  = max(values)
        exceeded = max_val > threshold
        verb     = "did" if exceeded else "did not"
        return (
            f"Humidity {verb} exceed {threshold:.0f} percent. The highest reading was {max_val:.1f} percent.",
            {"threshold": threshold, "max_humidity": max_val, "exceeded": exceeded},
        )

    if intent == "recovery_lastnight":
        rows = get_history(device_id, config, hours=24)
        # UTC hours 20–23 and 0–5 cover most "last night" windows for UTC+2 device
        night = [r for r in rows if _parse_ts(r["timestamp"]).hour >= 20 or _parse_ts(r["timestamp"]).hour < 6]
        if not night:
            return "I do not have overnight data to assess recovery conditions.", {}
        scores = [
            compute_recovery_score(
                r.get("indoor_temp") or 20.0,
                r.get("indoor_humidity") or 50.0,
                r.get("air_quality") or 0.0,
                r.get("indoor_eco2") or 400.0,
            )
            for r in night
        ]
        avg = sum(scores) / len(scores)
        return (
            f"Last night scored {avg:.0f} out of 100 for recovery conditions. {_recovery_qualifier(avg)}",
            {"recovery_avg": round(avg, 1), "records": len(night)},
        )

    if intent == "peak_comfort":
        rows = get_history(device_id, config, hours=24)
        if not rows:
            return "I do not have data for the past 24 hours.", {}
        enriched = [enrich_row(r) for r in rows]
        best = max(enriched, key=lambda r: r["room_readiness"])
        return (
            f"The room was most comfortable around {_fmt_time(best['timestamp'])} "
            f"with a readiness score of {best['room_readiness']}.",
            {"peak_readiness": best["room_readiness"], "at": best["timestamp"]},
        )

    if intent == "air_strain_peak":
        rows = get_history(device_id, config, hours=24)
        if not rows:
            return "I do not have air data for the past 24 hours.", {}
        enriched = [enrich_row(r) for r in rows]
        worst = max(enriched, key=lambda r: r["air_strain"])
        label = worst.get("room_state", "strained")
        return (
            f"Air strain peaked at {worst['air_strain']} around {_fmt_time(worst['timestamp'])}. "
            f"The room felt {label.lower()} then.",
            {"peak_strain": worst["air_strain"], "at": worst["timestamp"], "room_state": label},
        )

    if intent == "current_readiness":
        row = get_latest_reading(device_id, config)
        if not row:
            return "No current data is available.", {}
        e = enrich_row(row)
        qualifier = "good" if e["room_readiness"] >= 70 else "moderate" if e["room_readiness"] >= 45 else "low"
        return (
            f"Room readiness is {e['room_readiness']} out of 100. Conditions are {qualifier} for focus right now.",
            {"readiness": e["room_readiness"], "room_state": e["room_state"]},
        )

    if intent == "current_recovery":
        row = get_latest_reading(device_id, config)
        if not row:
            return "No current data is available.", {}
        e = enrich_row(row)
        return (
            f"Current recovery score is {e['recovery_score']} out of 100. {_recovery_qualifier(e['recovery_score'])}",
            {"recovery_score": e["recovery_score"], "room_state": e["room_state"]},
        )

    if intent == "current_air":
        row = get_latest_reading(device_id, config)
        if not row:
            return "No current data is available.", {}
        label = row.get("air_quality_label") or "unknown"
        aq    = row.get("air_quality")
        aq_str = f"{aq:.0f} ppb" if aq is not None else "not measured"
        e = enrich_row(row)
        return (
            f"Air quality is {label.lower()} right now. TVOC is {aq_str} and air strain is {e['air_strain']}.",
            {"air_quality_label": label, "air_quality_ppb": aq, "air_strain": e["air_strain"]},
        )

    if intent in ("rain_tomorrow", "umbrella"):
        forecast = fetch_forecast(config)
        tomorrow = forecast.get("tomorrow", {})
        morning_rain = tomorrow.get("morning_rain", False)
        storm        = forecast.get("storm_warning", False)
        umbrella     = forecast.get("umbrella_needed", False) or morning_rain
        if storm:
            return "There is a storm warning for tomorrow. Plan accordingly.", {"storm_warning": True}
        if morning_rain:
            return "Rain is expected tomorrow morning. You may want to bring an umbrella.", {"morning_rain": True}
        if umbrella:
            return "Some rain is likely tomorrow. An umbrella would be a good idea.", {"umbrella_needed": True}
        return "No rain expected tomorrow. Conditions look clear.", {"morning_rain": False}

    # unknown
    return (
        "I am not sure how to answer that. Try asking about temperature, humidity, air quality, or recovery.",
        {},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts_str: str) -> datetime:
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def _fmt_time(ts_str: str) -> str:
    try:
        dt = _parse_ts(ts_str)
        h  = dt.hour % 12 or 12
        period = "AM" if dt.hour < 12 else "PM"
        return f"{h}:{dt.minute:02d} {period} UTC"
    except Exception:
        return ts_str


def _extract_threshold(question: str, default: float = 50.0) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:percent|%)", question.lower())
    return float(match.group(1)) if match else default


def _recovery_qualifier(score: float) -> str:
    if score >= 75:
        return "Conditions were well suited for rest and recovery."
    if score >= 55:
        return "Conditions were adequate for rest."
    return "Conditions were not ideal for recovery."
