"""LLM-generated guided meditation sessions for /speech/meditation.

Generates a short, calm meditation script with gpt-4o-mini via OpenAI's
structured-output (json_schema) mode, returning the EXACT schema the device
already consumes: title / subtitle / duration_s / breath cadence / timed
prompts. No device-side changes are needed — the firmware just plays whatever
prompts come back.

Design notes:
- Results are cached per theme (process-lifetime, bust with ?fresh=1). That
  keeps prompt ids stable, so the device's per-prompt TTS cache stays valid
  and a live demo can't be surprised mid-session.
- Prompt ids are derived from the text hash, so identical cues reuse cached
  audio on the device.
- ANY failure (no key, timeout, API error, bad/empty output) falls back to the
  static catalog in meditation_service, so the device never stalls.

Mirrors the pattern in agent_service.py.
"""

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI
from openai import APIError, APITimeoutError

from app.utils.logger import get_logger
from app.services.meditation_service import get_session  # static fallback

logger = get_logger(__name__)

_MODEL      = "gpt-4o-mini"
_TIMEOUT_S  = 8.0
_MAX_TOKENS = 900   # technique-driven sessions run longer (9-11 cues)

# Theme -> fixed metadata + the TECHNIQUE that shapes the generated script.
# Each theme teaches a real mindfulness technique (Headspace-style) instead of
# generic "breathe in / breathe out". `cues` is the target number of spoken
# lines; against duration_s it sets the pacing (more cues = less silence).
# The device only requests the theme its picker selects; all are generatable.
_THEMES: Dict[str, Dict[str, Any]] = {
    "calm": {
        "title": "Calm", "subtitle": "3 min - settle in",
        "duration_s": 180, "breath_in_s": 6, "breath_out_s": 6, "cues": 9,
        "technique": "focused attention on the breath",
        "guide": "Rest attention on the natural breath at the nose or belly. "
                 "Follow a few breaths, and each time the mind wanders, gently "
                 "guide it back to the breath. Calm, grounding, unhurried.",
    },
    "sleep": {
        "title": "Sleep", "subtitle": "4 min - wind down",
        "duration_s": 240, "breath_in_s": 4, "breath_out_s": 8, "cues": 9,
        "technique": "body scan with a warm-light visualization",
        "guide": "Slowly scan the body from head to toes, and with each long "
                 "exhale picture a warm soft light, or a gentle heaviness, "
                 "sinking down through the body and releasing each part. End "
                 "drifting toward sleep, eyes staying closed.",
    },
    "focus": {
        "title": "Focus", "subtitle": "3 min - reset attention",
        "duration_s": 180, "breath_in_s": 4, "breath_out_s": 4, "cues": 11,
        "technique": "noting",
        "guide": "Teach the noting technique: rest on the breath, and when a "
                 "thought or feeling pulls attention away, gently note it - "
                 "'thinking', 'planning', 'feeling' - then return to the breath. "
                 "Builds a clear, sharp, present mind for work.",
    },
    "stress": {
        "title": "Stress Relief", "subtitle": "3 min - let go",
        "duration_s": 180, "breath_in_s": 4, "breath_out_s": 6, "cues": 10,
        "technique": "body scan to release tension",
        "guide": "Move attention slowly through the body - jaw, shoulders, "
                 "chest, hands, belly, legs - softening and releasing the "
                 "tension in each area on the out-breath. Let go of the day.",
    },
    "energize": {
        "title": "Energize", "subtitle": "2 min - wake up",
        "duration_s": 120, "breath_in_s": 5, "breath_out_s": 5, "cues": 9,
        "technique": "energizing light visualization",
        "guide": "Fuller, brighter breaths. With each inhale, picture light or "
                 "warmth rising up through the body, leaving the listener alert, "
                 "awake, and present. Gently uplifting, not rushed.",
    },
}

_DEFAULT_THEME = "calm"

_SYSTEM_PROMPT = (
    "You are a warm, experienced meditation teacher (in the spirit of Headspace) "
    "writing a guided session for an ambient room companion that speaks each "
    "line aloud through a small speaker. You are given ONE technique to teach "
    "and how to guide it - the whole session should actually teach and guide "
    "that technique, not just repeat 'breathe in, breathe out'.\n\n"
    "Voice: calm, warm, plain-spoken, encouraging. Never flowery, new-age, or "
    "clinical.\n\n"
    "Shape the session as an arc:\n"
    "1. A brief, fresh settling-in line. Do NOT use the cliche 'find a "
    "comfortable position' - vary it, or simply invite the listener to arrive "
    "and soften.\n"
    "2. The heart of the session: guide the given technique step by step, with "
    "warm transitions between cues.\n"
    "3. A gentle close that fits the theme (for sleep, drifting off with the "
    "eyes staying closed; otherwise slowly returning and opening the eyes).\n\n"
    "Rules:\n"
    "- Each prompt is ONE short spoken line, max about 14 words.\n"
    "- Produce close to the requested number of prompts.\n"
    "- The lines should read as one connected session, not a list of tips.\n"
    "- Plain spoken sentences only: no numbering, markdown, emojis, or stage "
    "directions.\n"
    "- Never mention that you are an AI or that this is a script."
)

# Cache: theme -> generated session dict (stable for the process lifetime).
_CACHE: Dict[str, Dict[str, Any]] = {}

_client: Optional[OpenAI] = None


def _get_client(api_key: str) -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=api_key, timeout=_TIMEOUT_S)
    return _client


def _response_schema() -> Dict[str, Any]:
    """json_schema OpenAI enforces on the response (strict mode)."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "meditation_script",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "prompts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text":   {"type": "string"},
                                "time_s": {"type": "integer"},
                            },
                            "required": ["text", "time_s"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["prompts"],
                "additionalProperties": False,
            },
        },
    }


def _prompt_id(theme: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return "med_{}_{}".format(theme, digest)


def _sanitize_prompts(theme: str, raw_prompts: List[Dict[str, Any]], duration_s: int, max_prompts: int) -> List[Dict[str, Any]]:
    """Keep the model's wording/order but RE-SPACE the timings ourselves.

    The model reliably writes a good arc (settle in -> breathe -> body -> close)
    but is terrible at pacing — it front-loads every cue into the first minute.
    So we ignore its time_s entirely and distribute the cues evenly across the
    session, ending a little before the close so there's a final stretch of
    silence. Empty/duplicate lines are dropped; ids are stable (text hash)."""
    texts: List[str] = []
    seen = set()
    for p in raw_prompts:
        text = str(p.get("text", "")).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        texts.append(text)

    if not texts:
        return []

    # The model can overshoot the requested count. Cap to the theme's target,
    # keeping the first and last lines (the arc) and sampling the middle evenly.
    cap = max(2, max_prompts)
    if len(texts) > cap:
        idxs  = sorted({round(i * (len(texts) - 1) / (cap - 1)) for i in range(cap)})
        texts = [texts[j] for j in idxs]

    n    = len(texts)
    tail = max(10, duration_s // 12)        # leave silence before the session ends
    span = max(1, duration_s - tail)
    out: List[Dict[str, Any]] = []
    for i, text in enumerate(texts):
        t = 0 if n == 1 else round(i * span / (n - 1))
        out.append({"id": _prompt_id(theme, text), "text": text, "time_s": int(t)})
    return out


def _generate(theme: str, config) -> Optional[Dict[str, Any]]:
    meta = _THEMES.get(theme)
    if meta is None:
        return None

    api_key = config.get("OPENAI_API_KEY") if hasattr(config, "get") else None
    if not api_key:
        logger.error("meditation_agent: OPENAI_API_KEY missing from config")
        return None

    duration_s = meta["duration_s"]
    cues       = meta.get("cues", 8)
    user_content = (
        "Theme: {title}. Duration: {dur} seconds. Breathing cadence: about "
        "{bin}s in and {bout}s out.\n"
        "Technique to teach: {tech}.\n"
        "How to guide it: {guide}\n"
        "Write about {cues} short spoken prompts that guide this technique as "
        "one flowing session. Give the lines in order; we handle the timing, so "
        "time_s can just be 0."
    ).format(
        title=meta["title"], dur=duration_s, bin=meta["breath_in_s"],
        bout=meta["breath_out_s"], tech=meta["technique"], guide=meta["guide"],
        cues=cues,
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
            temperature=0.8,
            max_tokens=_MAX_TOKENS,
            response_format=_response_schema(),
        )
    except APITimeoutError:
        logger.warning("meditation_agent: OpenAI timeout after {:.1f}s".format(time.time() - t0))
        return None
    except APIError as exc:
        logger.warning("meditation_agent: OpenAI API error: {}".format(exc))
        return None
    except Exception as exc:
        logger.error("meditation_agent: unexpected error: {}".format(exc))
        return None

    raw = (resp.choices[0].message.content or "").strip()
    try:
        parsed  = json.loads(raw)
        prompts = _sanitize_prompts(theme, parsed.get("prompts", []), duration_s, cues)
    except Exception as exc:
        logger.warning("meditation_agent: parse failed: {} raw={!r}".format(exc, raw[:120]))
        return None

    if len(prompts) < 2:
        logger.warning("meditation_agent: too few usable prompts ({})".format(len(prompts)))
        return None

    session = {
        "session_id":   theme,
        "title":        meta["title"],
        "subtitle":     meta["subtitle"],
        "duration_s":   duration_s,
        "breath_in_s":  meta["breath_in_s"],
        "breath_out_s": meta["breath_out_s"],
        "prompts":      prompts,
        "source":       "agent",
    }
    logger.info("meditation_agent: generated theme={} prompts={} in {}ms".format(
        theme, len(prompts), int((time.time() - t0) * 1000)))
    return session


def get_meditation(session_id: Optional[str], config, fresh: bool = False) -> Optional[Dict[str, Any]]:
    """Public entry point used by the /speech/meditation route.

    Returns a generated-and-cached session for known themes, the static catalog
    session as a fallback (generation failure or static-only id), or None if the
    theme is unknown everywhere (route then 404s)."""
    theme = session_id or _DEFAULT_THEME

    # Unknown both as a generatable theme and in the static catalog -> 404.
    if theme not in _THEMES and get_session(theme) is None:
        return None

    if theme in _THEMES:
        if not fresh and theme in _CACHE:
            return _CACHE[theme]
        generated = _generate(theme, config)
        if generated is not None:
            _CACHE[theme] = generated
            return generated
        logger.info("meditation_agent: falling back to static catalog for theme={}".format(theme))

    return get_session(theme)
