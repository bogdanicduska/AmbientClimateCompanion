"""
4.6  EventTimeline — chronological event list.
Props: events: [RoomEvent], max_items (default 20)
"""

import streamlit as st
from datetime import datetime, timezone

from services.contracts import RoomEvent
from services.state_meta import SEVERITY_COLOR, event_meta


def _rel_time(ts_str: str) -> str:
    try:
        ts   = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        diff = int((datetime.now(timezone.utc) - ts).total_seconds())
        if diff < 60:    return "just now"
        if diff < 3600:  return f"{diff // 60} min ago"
        if diff < 86400: return f"{diff // 3600} h ago"
        return f"{diff // 86400} d ago"
    except Exception:
        return ts_str[:16] if ts_str else "—"


def event_timeline(events: list[RoomEvent], max_items: int = 20) -> None:
    """
    Acceptance criteria:
    - newest first (caller must sort; this renders in order)
    - severity visible by color
    - each event shows: time, title, short explanation
    - empty state has meaningful copy
    """
    if not events:
        st.markdown(
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
            'padding:24px;color:#3A5A7A;text-align:center;">'
            '<div style="font-size:0.88rem;font-weight:600;margin-bottom:6px;color:#446688;">'
            'No recent room events yet.</div>'
            '<div style="font-size:0.82rem;color:#334455;line-height:1.6;">'
            'As the device collects more moments, this timeline will show air alerts, '
            'recovery peaks, motion bursts, and sync events.'
            '</div></div>',
            unsafe_allow_html=True,
        )
        return

    display = list(events)[:max_items]
    rows_html = ""

    for ev in display:
        severity    = ev.get("severity", "info")
        text_color  = SEVERITY_COLOR.get(severity, "#778899")
        _, _, border_color = event_meta(ev.get("event_type", ""))

        rel     = _rel_time(ev.get("timestamp") or "")
        title   = ev.get("title") or ev.get("event_type", "").replace("_", " ").title()
        message = ev.get("message", "")

        msg_html = (
            f'<span style="color:#445566;font-size:0.78rem;margin-left:4px;">{message}</span>'
            if message else ""
        )

        rows_html += (
            f'<div style="display:flex;align-items:baseline;gap:12px;padding:7px 0;'
            f'border-bottom:1px solid #0F1A28;border-left:2px solid {border_color};padding-left:10px;">'
            f'<span style="color:#334455;font-size:0.75rem;white-space:nowrap;min-width:76px;">{rel}</span>'
            f'<span style="color:{text_color};font-size:0.82rem;font-weight:600;">{title}</span>'
            f'{msg_html}'
            f'</div>'
        )

    st.markdown(
        f'<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;padding:20px;">'
        f'<div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.15em;text-transform:uppercase;'
        f'margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #142030;">Room Events</div>'
        f'{rows_html}</div>',
        unsafe_allow_html=True,
    )
