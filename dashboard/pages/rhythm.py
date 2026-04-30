"""
Rhythm — temporal patterns and room rhythm.
Answers: How did the room change? When was it best? When was it worst?
"""

import streamlit as st

from services.api_client import fetch_history
from services.transformers import to_history_series, series_to_df
from services.analysis import get_pattern_summary

from components.section_header import section_label
from components.chart_blocks import (
    room_scores_chart, temperature_chart, humidity_chart,
    tvoc_chart, eco2_chart, motion_chart,
)

_WINDOW_LABELS = {6: "6 h", 12: "12 h", 24: "24 h", 72: "3 days", 168: "7 days"}


def render() -> None:
    device_id     = st.session_state.get("device_id", "m5stack-duska-home")
    history_hours = st.session_state.get("history_hours", 24)
    hours_label   = _WINDOW_LABELS.get(history_hours, f"{history_hours} h")

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:4px;">'
        f'<span style="font-size:1.4rem;font-weight:800;color:#D8EEFF;">Rhythm</span>'
        f'<span style="font-size:0.8rem;color:#2A4A6A;">last {hours_label}  ·  {device_id}</span>'
        f'</div>'
        f'<div style="height:1px;background:#111E2E;margin-bottom:20px;"></div>',
        unsafe_allow_html=True,
    )
    st.caption("Use the History window slider in the sidebar to change the time range.")

    # ── Data ──────────────────────────────────────────────────────────────────
    with st.spinner("Loading history…"):
        raw_rows = fetch_history(device_id=device_id, hours=history_hours)
        series   = to_history_series(raw_rows, device_id, history_hours)
        df       = series_to_df(series)

    if df is None or df.empty:
        _empty_state()
        return

    n_points = len(series["points"])
    st.caption(
        f"{n_points} readings  ·  "
        f"{df['timestamp'].min().strftime('%d %b %H:%M')} → "
        f"{df['timestamp'].max().strftime('%d %b %H:%M')}"
    )

    # ── Pattern summary cards ─────────────────────────────────────────────────
    section_label("Pattern Summary")
    cards = get_pattern_summary(df)
    if cards:
        cols = st.columns(len(cards))
        for col, card in zip(cols, cards):
            with col:
                _pattern_card(card)

    # ── Room performance over time ────────────────────────────────────────────
    st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
    section_label(f"Room Performance — last {hours_label}")
    st.plotly_chart(room_scores_chart(df), use_container_width=True)

    # ── Environmental inputs ──────────────────────────────────────────────────
    section_label("Environmental Inputs")
    env1, env2 = st.columns(2)
    with env1:
        if "indoor_temp" in df.columns and df["indoor_temp"].notna().any():
            st.plotly_chart(temperature_chart(df), use_container_width=True)
        else:
            _no_data_mini("Temperature")
    with env2:
        if "indoor_humidity" in df.columns and df["indoor_humidity"].notna().any():
            st.plotly_chart(humidity_chart(df), use_container_width=True)
        else:
            _no_data_mini("Humidity")

    # ── Air quality ───────────────────────────────────────────────────────────
    has_tvoc = "air_quality"  in df.columns and df["air_quality"].notna().any()
    has_eco2 = "indoor_eco2" in df.columns and df["indoor_eco2"].notna().any()
    if has_tvoc or has_eco2:
        section_label("Air Quality")
        aq1, aq2 = st.columns(2)
        with aq1:
            if has_tvoc:
                st.plotly_chart(tvoc_chart(df), use_container_width=True)
            else:
                _no_data_mini("TVOC")
        with aq2:
            if has_eco2:
                st.plotly_chart(eco2_chart(df), use_container_width=True)
            else:
                _no_data_mini("eCO₂")

    # ── Activity ─────────────────────────────────────────────────────────────
    if "motion" in df.columns and df["motion"].notna().any():
        section_label("Room Activity")
        st.plotly_chart(motion_chart(df), use_container_width=True)


# ── Sub-components ────────────────────────────────────────────────────────────

def _pattern_card(card: dict) -> None:
    color = card.get("color", "#778899")
    st.markdown(
        f'<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
        f'padding:16px;border-top:2px solid {color};">'
        f'<div style="font-size:0.65rem;color:#3A5A7A;letter-spacing:0.14em;'
        f'text-transform:uppercase;margin-bottom:6px;">{card.get("label","")}</div>'
        f'<div style="font-size:1.8rem;font-weight:700;color:{color};line-height:1.1;">'
        f'{card.get("value","—")}</div>'
        f'<div style="font-size:0.75rem;color:#445566;margin-top:4px;">{card.get("time","")}</div>'
        f'<div style="font-size:0.7rem;color:#2A3A4A;margin-top:2px;">{card.get("hint","")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _empty_state() -> None:
    st.markdown(
        '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
        'padding:32px;text-align:center;">'
        '<div style="font-size:1rem;font-weight:600;color:#446688;margin-bottom:8px;">'
        'History is still building.</div>'
        '<div style="font-size:0.85rem;color:#334455;line-height:1.7;max-width:480px;margin:0 auto;">'
        'Leave the device running and Room Rhythm will begin showing how readiness, recovery, '
        'and air strain evolve over time. Try widening the history window once data accumulates.'
        '</div></div>',
        unsafe_allow_html=True,
    )


def _no_data_mini(label: str) -> None:
    st.markdown(
        f'<div style="background:#0A1220;border:1px solid #0F1A28;border-radius:10px;'
        f'padding:16px;text-align:center;color:#2A3A4A;font-size:0.8rem;">'
        f'{label} readings will appear here once the device sends data for this window.</div>',
        unsafe_allow_html=True,
    )
