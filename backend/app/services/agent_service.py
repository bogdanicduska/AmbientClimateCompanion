"""Single source of truth for /speech/ask. Pulls a JSON snapshot of
current + recent room conditions plus the local forecast, sends it to
gpt-4o-mini with the intents catalog, and returns a structured
{intent, answer} pair via OpenAI's json_schema response format.

Errors and timeouts fall back to a generic deflection so the device
never hangs waiting on the LLM."""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from openai import APIError, APITimeoutError

from app.utils.logger import get_logger
from app.services.agent_intents import intent_ids, prompt_block
from app.services.bigquery_service import (
    get_history,
    get_history_window,
    get_latest_reading,
)
from app.services.forecast_service import fetch_forecast
from app.services.room_metrics_service import enrich_row

logger = get_logger(__name__)

_MODEL      = "gpt-4o-mini"
_TIMEOUT_S  = 6.0
_MAX_TOKENS = 220   # JSON wrapper adds ~30 tokens vs the old free-text answer

# WHOOP-inspired voice: data-driven coach who happens to read room sensors
# instead of biometrics. Every answer should lead with a number when one
# is relevant and stop at the implication — no filler, no hedging.
_SYSTEM_PROMPT = (
    "You are an ambient climate companion: half weather station, half "
    "recovery coach in the spirit of WHOOP. You read indoor sensors "
    "(temperature in C, humidity in %, air quality in ppb, eCO2 in ppm) "
    "plus the local outdoor forecast and recent outdoor history, and you "
    "help the user understand how their environment affects focus, "
    "recovery, and comfort.\n\n"
    "Tone: calm, factual, data-driven — like a good athletic coach. Lead "
    "with the relevant number, then a short implication if useful.\n\n"
    "Style rules:\n"
    "- Maximum two short sentences. Ideally one.\n"
    "- Plain units (C, %, ppb, ppm). No technical jargon unless asked.\n"
    "- Reference actual numbers from the snapshot when relevant.\n"
    "- No filler greetings, sign-offs, or apologies.\n"
    "- If the snapshot lacks the data needed, say so plainly in one line "
    "and tag the intent as 'unknown'.\n\n"
    "You receive a JSON snapshot of current + recent room conditions, "
    "recent outdoor history, and the local forecast on every call. Only "
    "use values from the snapshot — never invent metrics.\n\n"
    + prompt_block() + "\n\n"
    "Return JSON with two fields: 'intent' (one id from the list above) "
    "and 'answer' (the spoken reply, following the style rules)."
)

# Built once: the JSON schema OpenAI will enforce on the response.
_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "intent_answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": intent_ids()},
                "answer": {"type": "string"},
            },
            "required": ["intent", "answer"],
            "additionalProperties": False,
        },
    },
}

_client: Optional[OpenAI] = None


def _get_client(api_key: str) -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=api_key, timeout=_TIMEOUT_S)
    return _client


def _modal(values: List[Any]) -> Optional[Any]:
    """Most-frequent value, or None for an empty list. Cheap stand-in for
    statistics.mode (which raises on empties on older Pythons)."""
    if not values:
        return None
    counts: Dict[Any, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _outdoor_yesterday(device_id: str, config) -> Optional[Dict[str, Any]]:
    """Aggregate outdoor columns from BigQuery for the previous UTC calendar
    day. Returns None if no rows exist in that window — the LLM will then
    answer weather_yesterday with a 'no data' deflection."""
    end   = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    rows  = get_history_window(device_id, config, start.isoformat(), end.isoformat())
    if not rows:
        return None

    temps    = [r["outdoor_temp"]     for r in rows if r.get("outdoor_temp")     is not None]
    hums     = [r["outdoor_humidity"] for r in rows if r.get("outdoor_humidity") is not None]
    weathers = [r["outdoor_weather"]  for r in rows if r.get("outdoor_weather")]

    return {
        "date_utc":         start.date().isoformat(),
        "records":          len(rows),
        "outdoor_temp_min": round(min(temps), 1) if temps else None,
        "outdoor_temp_max": round(max(temps), 1) if temps else None,
        "outdoor_hum_min":  round(min(hums), 1)  if hums  else None,
        "outdoor_hum_max":  round(max(hums), 1)  if hums  else None,
        "weather_mode":     _modal(weathers),
    }


def _build_snapshot(device_id: str, config) -> Dict[str, Any]:
    """Compose the JSON context block sent to the model. Each section is
    wrapped in its own try so a single failing data source (e.g. forecast
    API down) does not blank out the whole snapshot."""
    snapshot: Dict[str, Any] = {}

    try:
        latest = get_latest_reading(device_id, config)
        if latest:
            e = enrich_row(latest)
            snapshot["current"] = {
                "timestamp":           e.get("timestamp"),
                "indoor_temp_c":       e.get("indoor_temp"),
                "indoor_humidity_pct": e.get("indoor_humidity"),
                "air_quality_ppb":     e.get("air_quality"),
                "air_quality_label":   e.get("air_quality_label"),
                "eco2_ppm":            e.get("indoor_eco2"),
                "room_state":          e.get("room_state"),
                "room_readiness":      e.get("readiness_score"),
                "recovery_score":      e.get("recovery_score"),
                "air_strain":          e.get("air_strain_score"),
                "outdoor_temp_c":      e.get("outdoor_temp"),
                "outdoor_humidity_pct":e.get("outdoor_humidity"),
                "outdoor_weather":     e.get("outdoor_weather"),
            }
    except Exception as exc:
        logger.warning(f"agent: snapshot.current failed: {exc}")

    try:
        rows = get_history(device_id, config, hours=24)
        if rows:
            temps = [r["indoor_temp"]     for r in rows if r.get("indoor_temp")     is not None]
            hums  = [r["indoor_humidity"] for r in rows if r.get("indoor_humidity") is not None]
            aqs   = [r["air_quality"]     for r in rows if r.get("air_quality")     is not None]
            eco2s = [r["indoor_eco2"]     for r in rows if r.get("indoor_eco2")     is not None]
            snapshot["last_24h"] = {
                "records":             len(rows),
                "temp_min_c":          round(min(temps), 1) if temps else None,
                "temp_max_c":          round(max(temps), 1) if temps else None,
                "humidity_max_pct":    round(max(hums), 1)  if hums  else None,
                "humidity_min_pct":    round(min(hums), 1)  if hums  else None,
                "air_quality_max_ppb": round(max(aqs), 0)   if aqs   else None,
                "eco2_max_ppm":        round(max(eco2s), 0) if eco2s else None,
            }
    except Exception as exc:
        logger.warning(f"agent: snapshot.last_24h failed: {exc}")

    try:
        yest = _outdoor_yesterday(device_id, config)
        if yest:
            snapshot["outdoor_yesterday"] = yest
    except Exception as exc:
        logger.warning(f"agent: snapshot.outdoor_yesterday failed: {exc}")

    try:
        forecast = fetch_forecast(config)
        if forecast:
            snapshot["forecast"] = {
                "today":           forecast.get("today"),
                "tomorrow":        forecast.get("tomorrow"),
                "storm_warning":   forecast.get("storm_warning"),
                "umbrella_needed": forecast.get("umbrella_needed"),
            }
    except Exception as exc:
        logger.warning(f"agent: snapshot.forecast failed: {exc}")

    return snapshot


_FALLBACK_ANSWER = (
    "I am not sure how to answer that. Try asking about temperature, "
    "humidity, air quality, or recovery."
)


def answer_question(device_id: str, question: str, config) -> Dict[str, Any]:
    """Public entry point used by /speech/ask. Calls the LLM with current
    sensor context and the intents catalog, and returns a structured
    response. On any failure (no API key, timeout, API error, empty
    completion, schema parse error), falls back to a generic deflection
    tagged 'unknown' so the device never stalls."""
    intent, answer, snapshot = _agent_answer(device_id, question, config)

    if not answer:
        return {
            "intent":        "unknown",
            "answer_source": "fallback",
            "answer":        _FALLBACK_ANSWER,
            "data_snapshot": snapshot,
        }

    return {
        "intent":        intent or "unknown",
        "answer_source": "agent",
        "answer":        answer,
        "data_snapshot": snapshot,
    }


def _agent_answer(
    device_id: str, question: str, config
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """Return (intent, answer_text, snapshot). intent and answer_text are
    None if the LLM call failed for any reason — caller falls back to the
    generic deflection so the device doesn't stall."""
    snapshot = _build_snapshot(device_id, config)

    api_key = config.get("OPENAI_API_KEY") if hasattr(config, "get") else None
    if not api_key:
        logger.error("agent: OPENAI_API_KEY missing from config")
        return None, None, snapshot

    user_content = (
        "Room snapshot (JSON):\n"
        + json.dumps(snapshot, default=str)
        + f"\n\nQuestion: {question}"
    )

    t0 = time.time()
    try:
        client = _get_client(api_key)
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.4,
            max_tokens=_MAX_TOKENS,
            response_format=_RESPONSE_SCHEMA,
        )
    except APITimeoutError:
        logger.warning(f"agent: OpenAI timeout after {time.time() - t0:.1f}s")
        return None, None, snapshot
    except APIError as exc:
        logger.warning(f"agent: OpenAI API error: {exc}")
        return None, None, snapshot
    except Exception as exc:
        logger.error(f"agent: unexpected error: {exc}")
        return None, None, snapshot

    elapsed_ms = int((time.time() - t0) * 1000)
    raw = (resp.choices[0].message.content or "").strip()

    try:
        parsed = json.loads(raw)
        intent = parsed["intent"]
        answer = (parsed["answer"] or "").strip()
    except Exception as exc:
        logger.warning(f"agent: structured-output parse failed: {exc} raw={raw[:120]!r}")
        return None, None, snapshot

    usage = getattr(resp, "usage", None)
    if usage is not None:
        cached_details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens  = getattr(cached_details, "cached_tokens", 0) if cached_details else 0
        logger.info(
            f"agent: ok intent={intent} in {elapsed_ms}ms tokens "
            f"prompt={usage.prompt_tokens} completion={usage.completion_tokens} "
            f"cached={cached_tokens}"
        )
    else:
        logger.info(f"agent: ok intent={intent} in {elapsed_ms}ms (no usage)")

    if not answer:
        return intent, None, snapshot
    return intent, answer, snapshot
