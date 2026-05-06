"""Guided meditation session catalog.

Each session is a short, WHOOP-style script — calm, factual cues without
new-age flourishes. The device fetches the session metadata, then caches
each prompt's TTS audio locally on first run via /speech/tts. During the
session it renders a slow-pulse orb and plays prompts at the scheduled
times.

Adding a new session = adding a new entry to _SESSIONS. No device-side
changes needed beyond exposing the session id in the menu.
"""

from typing import Any, Dict, List, Optional


_SESSIONS: Dict[str, Dict[str, Any]] = {
    "calm": {
        "session_id":   "calm",
        "title":        "Calm",
        "subtitle":     "3 min — settle in",
        "duration_s":   180,
        "breath_in_s":  6,
        "breath_out_s": 6,
        "prompts": [
            {"id": "calm_01", "text": "Settle in. Sit tall but easy.",                   "time_s": 0},
            {"id": "calm_02", "text": "Notice your breath without changing it.",         "time_s": 25},
            {"id": "calm_03", "text": "Soften your shoulders.",                          "time_s": 60},
            {"id": "calm_04", "text": "Let your jaw release.",                           "time_s": 95},
            {"id": "calm_05", "text": "If your mind wanders, that is fine. Come back.",  "time_s": 130},
            {"id": "calm_06", "text": "When you are ready, open your eyes.",             "time_s": 165},
        ],
    },
}

_DEFAULT_SESSION_ID = "calm"


def list_sessions() -> List[Dict[str, Any]]:
    """Lightweight summary used by a future picker UI."""
    return [
        {
            "session_id": s["session_id"],
            "title":      s["title"],
            "subtitle":   s.get("subtitle", ""),
            "duration_s": s["duration_s"],
        }
        for s in _SESSIONS.values()
    ]


def get_session(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return the full session config (incl. prompts) or None if unknown."""
    if not session_id:
        session_id = _DEFAULT_SESSION_ID
    return _SESSIONS.get(session_id)
