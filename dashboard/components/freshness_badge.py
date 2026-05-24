"""
4.3  FreshnessBadge — data/source freshness indicator.
Props: state (live|cloud|cache|stale|offline), label
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
import os

from services.contracts import SourceState

_TZ_OFFSET_H = int(os.environ.get("TZ_OFFSET_HOURS", "0"))
_LOCAL_TZ    = timezone(timedelta(hours=_TZ_OFFSET_H))

_STATE_STYLE: dict[str, tuple[str, str]] = {
    "live":    ("#3DFF8A", "LIVE"),
    "cloud":   ("#FFCC00", "CLOUD"),
    "cache":   ("#778899", "CACHE"),
    "stale":   ("#FF8844", "STALE"),
    "offline": ("#FF4444", "OFFLINE"),
}


def status_pill(text: str, color: str) -> str:
    return (
        f'<span style="background:{color}22;color:{color};border:1px solid {color}55;'
        f'border-radius:4px;padding:2px 10px;font-size:0.75rem;font-weight:700;'
        f'letter-spacing:0.08em;">{text}</span>'
    )


def freshness_badge(state: SourceState, label: str = "") -> str:
    """
    Props: state (live|cloud|cache|stale|offline), label (optional override)
    Returns HTML string — use with st.markdown(unsafe_allow_html=True).
    Acceptance criteria: color semantics per spec.
    """
    color, default_label = _STATE_STYLE.get(state, ("#778899", state.upper()))
    return status_pill(label or default_label, color)


def parse_freshness(row: dict | None, fetched_at: datetime) -> tuple[str, str, int | None]:
    """
    Returns (ts_str, age_hint, ts_age_min).
    ts_str      — human-formatted timestamp
    age_hint    — inline text like "· last sync 3 min ago"
    ts_age_min  — integer minutes since last reading, or None
    """
    ts_str     = ""
    ts_age_min: int | None = None
    age_hint   = ""

    if row and row.get("timestamp"):
        try:
            ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            ts_local   = ts.astimezone(_LOCAL_TZ)
            ts_str     = ts_local.strftime("%a %d %b  ·  %H:%M")
            ts_age_min = int((fetched_at - ts).total_seconds() / 60)
        except Exception:
            ts_str = row.get("timestamp", "")[:16]

    if row is None:
        age_hint = ""
    elif ts_age_min is not None and ts_age_min < 10:
        age_hint = f"· last sync {ts_age_min} min ago"
    elif ts_age_min is not None and ts_age_min < 30:
        age_hint = f"· synced {ts_age_min} min ago"
    else:
        age_hint = (
            f"· last sync {ts_age_min} min ago · showing cached state"
            if ts_age_min is not None else "· no recent data"
        )

    return ts_str, age_hint, ts_age_min


def source_state_from_age(row: dict | None, ts_age_min: int | None) -> SourceState:
    if row is None:
        return "offline"
    sync = (row.get("sync_status") or "").lower()
    if sync == "cache":
        return "cache"
    if ts_age_min is None:
        return "stale"
    if ts_age_min < 10:
        return "live"
    if ts_age_min < 30:
        return "cloud"
    return "stale"


def pill_from_age(row: dict | None, ts_age_min: int | None) -> str:
    state = source_state_from_age(row, ts_age_min)
    return freshness_badge(state)
