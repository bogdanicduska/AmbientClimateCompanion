"""LLM fallback for /speech/ask. The regex router in ask_service handles
the deterministic question patterns; anything that returns intent='unknown'
falls through here. We pass a JSON snapshot of current + recent room
conditions plus the local forecast to gpt-4o-mini and let it produce a
short, WHOOP-style answer.

Errors and timeouts return (None, snapshot) so the caller can fall back
to the original generic deflection — the device must never hang waiting
on the LLM."""

import json
import time
from typing import Any, Dict, Optional, Tuple

from openai import OpenAI
from openai import APIError, APITimeoutError

from app.utils.logger import get_logger
from app.services.bigquery_service import get_history, get_latest_reading
from app.services.forecast_service import fetch_forecast
from app.services.room_metrics_service import enrich_row

logger = get_logger(__name__)

_MODEL      = "gpt-4o-mini"
_TIMEOUT_S  = 6.0
_MAX_TOKENS = 140

# WHOOP-inspired voice: data-driven coach who happens to read room sensors
# instead of biometrics. Every answer should lead with a number when one
# is relevant and stop at the implication — no filler, no hedging.
_SYSTEM_PROMPT = (
    "You are an ambient climate companion: half weather station, half "
    "recovery coach in the spirit of WHOOP. You read indoor sensors "
    "(temperature in C, humidity in %, air quality in ppb, eCO2 in ppm) "
    "plus the local outdoor forecast, and you help the user understand "
    "how their environment affects focus, recovery, and comfort.\n\n"
    "Tone: calm, factual, data-driven — like a good athletic coach. Lead "
    "with the relevant number, then a short implication if useful.\n\n"
    "Style rules:\n"
    "- Maximum two short sentences. Ideally one.\n"
    "- Plain units (C, %, ppb, ppm). No technical jargon unless asked.\n"
    "- Reference actual numbers from the snapshot when relevant.\n"
    "- No filler greetings, sign-offs, or apologies.\n"
    "- If the snapshot lacks the data needed, say so plainly in one line.\n\n"
    "You receive a JSON snapshot of current and recent room conditions "
    "on every call. Only use values from the snapshot — never invent "
    "metrics."
)

_client: Optional[OpenAI] = None


def _get_client(api_key: str) -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=api_key, timeout=_TIMEOUT_S)
    return _client


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


def agent_answer(device_id: str, question: str, config) -> Tuple[Optional[str], Dict[str, Any]]:
    """Return (answer_text, snapshot). answer_text is None if the LLM call
    failed for any reason — caller should fall back to the generic
    deflection so the device doesn't stall."""
    snapshot = _build_snapshot(device_id, config)

    api_key = config.get("OPENAI_API_KEY") if hasattr(config, "get") else None
    if not api_key:
        logger.error("agent: OPENAI_API_KEY missing from config")
        return None, snapshot

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
        )
    except APITimeoutError:
        logger.warning(f"agent: OpenAI timeout after {time.time() - t0:.1f}s")
        return None, snapshot
    except APIError as exc:
        logger.warning(f"agent: OpenAI API error: {exc}")
        return None, snapshot
    except Exception as exc:
        logger.error(f"agent: unexpected error: {exc}")
        return None, snapshot

    elapsed_ms = int((time.time() - t0) * 1000)
    answer = (resp.choices[0].message.content or "").strip()

    usage = getattr(resp, "usage", None)
    if usage is not None:
        cached_details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens  = getattr(cached_details, "cached_tokens", 0) if cached_details else 0
        logger.info(
            f"agent: ok in {elapsed_ms}ms tokens "
            f"prompt={usage.prompt_tokens} completion={usage.completion_tokens} "
            f"cached={cached_tokens}"
        )
    else:
        logger.info(f"agent: ok in {elapsed_ms}ms (no usage)")

    if not answer:
        return None, snapshot
    return answer, snapshot
