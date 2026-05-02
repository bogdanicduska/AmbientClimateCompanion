"""
4.1 MetricHeroCard  |  4.2 RoomStateCard
"""

import streamlit as st
from services.state_meta import state_meta, accent_hex


# ---------------------------------------------------------------------------
# 4.1  MetricHeroCard
# ---------------------------------------------------------------------------

def metric_hero_card(
    label: str,
    value: int | None,
    *,
    band_label:    str = "",
    subtitle:      str = "",
    accent_color:  str = "blue",
    progress_value: int | None = None,
    max_value:     int = 100,
    trend_arrow:   str = "",
    trend_label:   str = "",
    trend_color:   str = "#556677",
) -> None:
    """
    Props: label, value, band_label, subtitle, accent_color,
           progress_value, max_value, trend_arrow, trend_label, trend_color
    """
    if value is None:
        html = (
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;padding:20px;">'
            f'<div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:8px;">{label}</div>'
            '<div style="font-size:2.4rem;font-weight:700;color:#334455;">—</div>'
            '</div>'
        )
        st.markdown(html, unsafe_allow_html=True)
        return

    color = accent_hex(accent_color)
    pct   = min(100, int((progress_value if progress_value is not None else value) / max_value * 100))

    trend_html = (
        f'<span style="font-size:0.8rem;color:{trend_color};margin-left:10px;font-weight:600;">'
        f'{trend_arrow} {trend_label}</span>'
        if trend_arrow else ""
    )
    subtitle_display = subtitle[:60] + "…" if len(subtitle) > 60 else subtitle
    subtitle_html = (
        f'<div style="font-size:0.72rem;color:#3A5A6A;margin-top:6px;line-height:1.4;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{subtitle_display}</div>'
        if subtitle_display else ""
    )
    band_html = (
        f'<div style="font-size:0.75rem;color:#556677;">{band_label}</div>'
        if band_label else ""
    )

    html = (
        '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;padding:20px;">'
        f'<div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px;">{label}</div>'
        f'<div style="display:flex;align-items:baseline;">'
        f'<div style="font-size:2.4rem;font-weight:700;color:{color};line-height:1.1;">{value}</div>'
        f'{trend_html}'
        '</div>'
        '<div style="background:#111C2A;border-radius:3px;height:4px;margin:8px 0 6px;">'
        f'<div style="width:{pct}%;max-width:100%;background:{color};height:4px;border-radius:3px;"></div>'
        '</div>'
        f'{band_html}'
        f'{subtitle_html}'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def score_accent(value: int, low_good: bool) -> str:
    if low_good:
        return "green" if value < 30 else "amber" if value < 60 else "red"
    return "green" if value >= 75 else "amber" if value >= 50 else "red"


def score_band(value: int, low_good: bool) -> str:
    if low_good:
        return "Fresh air" if value < 30 else "Rising strain" if value < 60 else "Heavy"
    return "High" if value >= 75 else "Moderate" if value >= 50 else "Low"


# backward-compat aliases
_accent_for_score = score_accent
_band_for_score   = score_band


def score_card(
    label: str,
    value: int | None,
    low_good: bool = False,
    explanation: str = "",
    trend_arrow: str = "",
    trend_label: str = "",
    trend_color: str = "#556677",
) -> None:
    """Convenience wrapper that maps score semantics → MetricHeroCard."""
    band   = _band_for_score(value, low_good) if value is not None else ""
    accent = _accent_for_score(value, low_good) if value is not None else "gray"
    metric_hero_card(
        label=label,
        value=value,
        band_label=band,
        subtitle=explanation,
        accent_color=accent,
        trend_arrow=trend_arrow,
        trend_label=trend_label,
        trend_color=trend_color,
    )


# ---------------------------------------------------------------------------
# 4.2  RoomStateCard
# ---------------------------------------------------------------------------

def room_state_card(state: str | None) -> None:
    """
    Props: state, subtitle (from state_meta), color_theme (from state_meta)
    """
    if not state or state == "---":
        html = (
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;padding:20px;">'
            '<div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px;">Room State</div>'
            '<div style="font-size:1.5rem;font-weight:700;color:#334455;">—</div>'
            '</div>'
        )
        st.markdown(html, unsafe_allow_html=True)
        return

    m = state_meta(state)
    html = (
        f'<div style="background:{m["bg"]};border:1px solid {m["border"]};border-radius:12px;padding:20px;">'
        '<div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:8px;">Room State</div>'
        f'<div style="font-size:1.6rem;font-weight:700;color:{m["text"]};letter-spacing:0.06em;">{state}</div>'
        f'<div style="font-size:0.75rem;color:#445566;margin-top:6px;">{m["subtitle"]}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
