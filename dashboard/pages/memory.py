"""
Memory — room memory and narrative.
Answers: What happened today? What moments mattered? How did the room feel over time?
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from services.api_client import fetch_history, fetch_events
from services.transformers import to_history_series, series_to_df
from services.story_engine import to_daily_story
from services.event_transformer import to_room_events
from services.analysis import get_notable_moments, replay_snapshot
from services.rituals import get_ritual

from components.section_header import section_label
from components.story_card import story_card
from components.event_timeline import event_timeline
from components.snapshot_table import snapshot_card_open, snapshot_card_close, sensor_row

_WINDOW_LABELS = {6: "6 h", 12: "12 h", 24: "24 h", 72: "3 days", 168: "7 days"}
_STATE_HEX = {
    "Fresh": "#3DFF8A", "Calm": "#66CCFF", "Sleep-Friendly": "#88BBFF",
    "Dry": "#FFD060",   "Heavy": "#FF6644", "Restless": "#FF9944", "Social": "#DDDD00",
}


def render() -> None:
    device_id     = st.session_state.get("device_id", "m5stack-duska-home")
    history_hours = st.session_state.get("history_hours", 24)
    hours_label   = _WINDOW_LABELS.get(history_hours, f"{history_hours} h")

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:4px;">'
        f'<span style="font-size:1.4rem;font-weight:800;color:#D8EEFF;">Memory</span>'
        f'<span style="font-size:0.8rem;color:#2A4A6A;">last {hours_label}  ·  {device_id}</span>'
        f'</div>'
        f'<div style="height:1px;background:#111E2E;margin-bottom:20px;"></div>',
        unsafe_allow_html=True,
    )

    with st.spinner("Loading…"):
        raw_rows   = fetch_history(device_id=device_id, hours=history_hours)
        series     = to_history_series(raw_rows, device_id, history_hours)
        df         = series_to_df(series)
        raw_events = fetch_events(device_id=device_id, limit=30)
        events     = to_room_events(raw_events)

    if df is None or df.empty:
        _empty_state()
        if events:
            section_label("Event History")
            event_timeline(events)
        return

    # ── Daily story ───────────────────────────────────────────────────────────
    section_label(f"Room Story — last {hours_label}")
    ds = to_daily_story(df)
    if ds:
        story_card(ds["headline"], ds["bullets"], window_label=f"last {hours_label}")
    else:
        st.markdown(
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
            'padding:16px;color:#334455;font-size:0.85rem;">'
            'Not enough history for a story yet — data accumulates with each reading.</div>',
            unsafe_allow_html=True,
        )

    # ── Notable moments ───────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
    section_label("Notable Moments")
    moments = get_notable_moments(df)
    if moments:
        cols = st.columns(len(moments))
        for col, m in zip(cols, moments):
            with col:
                _moment_card(m)
    else:
        st.markdown(
            '<div style="color:#334455;font-size:0.85rem;">No notable moments identified in this window.</div>',
            unsafe_allow_html=True,
        )

    # ── Climate Memory Replay ─────────────────────────────────────────────────
    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    section_label("Climate Memory Replay")

    points = series.get("points", [])
    if len(points) >= 2:
        _replay_panel(df, points)
    else:
        st.markdown(
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
            'padding:16px;color:#334455;font-size:0.85rem;">'
            'Replay requires at least 2 history points in the selected window.</div>',
            unsafe_allow_html=True,
        )

    # ── Full event timeline ───────────────────────────────────────────────────
    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    section_label("Event History")
    event_timeline(events, max_items=30)


# ── Replay panel ──────────────────────────────────────────────────────────────

def _replay_panel(df: pd.DataFrame, points: list[dict]) -> None:
    n = len(points)

    # Build slider labels from timestamps
    labels = []
    for pt in points:
        ts = pt.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            labels.append(dt.strftime("%d %b %H:%M"))
        except Exception:
            labels.append(ts[:16] if ts else "—")

    idx = st.select_slider(
        "Scrub through history",
        options=list(range(n)),
        value=n - 1,
        format_func=lambda i: labels[i],
        label_visibility="collapsed",
    )

    snap = replay_snapshot(points, idx)
    if not snap:
        return

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    left, right = st.columns(2)
    state = snap.get("room_state", "")
    state_color = _STATE_HEX.get(state, "#AAAAAA")

    with left:
        snapshot_card_open(f"Room State at {labels[idx]}")
        sensor_row("Room State",  state or "—",                                  "",    state_color)
        sensor_row("Readiness",   _v(snap.get("readiness_score")),               "/100","#3DFF8A")
        sensor_row("Recovery",    _v(snap.get("recovery_score")),                "/100","#66CCFF")
        sensor_row("Air Strain",  _v(snap.get("air_strain_score")),              "/100","#FF8844")
        snapshot_card_close()

    with right:
        snapshot_card_open("Environment at That Moment")
        temp = snap.get("temperature_c")
        hum  = snap.get("humidity_pct")
        tvoc = snap.get("tvoc_ppb")
        eco2 = snap.get("eco2_ppm")
        o_temp = snap.get("outdoor_temperature_c")
        o_wx   = snap.get("outdoor_weather", "—").title() if snap.get("outdoor_weather") else "—"
        sensor_row("Temperature", f"{temp:.1f}" if temp is not None else None, "°C",  "#00FFCC")
        sensor_row("Humidity",    f"{hum:.0f}"  if hum  is not None else None, "%",   "#66CCFF")
        sensor_row("TVOC",        f"{tvoc:.0f}" if tvoc is not None else None, "ppb", "#FFCC00")
        sensor_row("eCO₂",        f"{eco2:.0f}" if eco2 is not None else None, "ppm", "#FFCC99")
        sensor_row("Outdoor",     o_wx,                                        "",    "#445566",
                   hint=f"{o_temp:.0f}°C" if o_temp is not None else "")
        snapshot_card_close()

    # Coaching message for that moment
    _replay_coaching(snap)


def _replay_coaching(snap: dict) -> None:
    """Show what the ritual would have been at the replayed moment."""
    lrs_like = {
        "air_strain_score": snap.get("air_strain_score"),
        "recovery_score":   snap.get("recovery_score"),
        "readiness_score":  snap.get("readiness_score"),
        "room_state":       snap.get("room_state", ""),
        "indoor": {
            "humidity_pct": snap.get("humidity_pct"),
            "temperature_c": snap.get("temperature_c"),
            "tvoc_ppb": snap.get("tvoc_ppb"),
        },
        "outdoor": {
            "temperature_c": snap.get("outdoor_temperature_c"),
            "weather_main": snap.get("outdoor_weather", ""),
        },
    }
    ritual = get_ritual(lrs_like)
    color  = {"high": "#FF8844", "medium": "#FFCC00", "low": "#66CCFF"}.get(ritual.get("priority", "low"), "#66CCFF")
    st.markdown(
        f'<div style="margin-top:10px;padding:10px 14px;background:#060E18;'
        f'border-left:3px solid {color};border-radius:0 8px 8px 0;">'
        f'<span style="font-size:0.7rem;color:#2A4A6A;letter-spacing:0.12em;'
        f'text-transform:uppercase;">Coaching at that moment</span><br>'
        f'<span style="font-size:0.85rem;color:{color};font-weight:600;">{ritual.get("title","")}</span>'
        f'<span style="font-size:0.78rem;color:#445566;margin-left:8px;">→ {ritual.get("next_step","")}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Sub-components ────────────────────────────────────────────────────────────

def _moment_card(m: dict) -> None:
    color = m.get("color", "#778899")
    icon  = m.get("icon", "◆")
    st.markdown(
        f'<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
        f'padding:16px;border-top:2px solid {color};">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
        f'<span style="color:{color};font-size:1rem;">{icon}</span>'
        f'<span style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.12em;'
        f'text-transform:uppercase;">{m.get("title","")}</span>'
        f'</div>'
        f'<div style="font-size:1rem;font-weight:700;color:{color};margin-bottom:2px;">'
        f'{m.get("value","—")}</div>'
        f'<div style="font-size:0.72rem;color:#445566;margin-top:2px;">{m.get("time","")}</div>'
        f'<div style="font-size:0.7rem;color:#2A3A4A;margin-top:4px;">{m.get("subtitle","")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _empty_state() -> None:
    st.markdown(
        '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
        'padding:32px;text-align:center;margin-bottom:20px;">'
        '<div style="font-size:1rem;font-weight:600;color:#446688;margin-bottom:8px;">'
        'No room memory yet.</div>'
        '<div style="font-size:0.85rem;color:#334455;line-height:1.7;max-width:480px;margin:0 auto;">'
        'Memory builds as the device collects readings over time. Once data is present, '
        'this page will show daily stories, notable moments, and a replay of how your room '
        'evolved throughout the day.'
        '</div></div>',
        unsafe_allow_html=True,
    )


def _v(val) -> str:
    return str(val) if val is not None else "—"
