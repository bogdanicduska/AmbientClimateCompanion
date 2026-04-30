"""
Coach — turn room state into action.
Answers: What should I do right now? Why now? What benefit will it bring?
"""

import streamlit as st
from datetime import datetime, timezone

from services.api_client import fetch_latest
from services.transformers import to_latest_room_state
from services.rituals import get_ritual, get_alternative_ritual
from services.story_engine import outdoor_suitability
from services.analysis import summary_sentence

from components.section_header import section_label
from components.ritual_card import ritual_card
from components.freshness_badge import parse_freshness, freshness_badge, source_state_from_age


def render() -> None:
    device_id  = st.session_state.get("device_id", "m5stack-duska-home")
    fetched_at = datetime.now(timezone.utc)

    raw = fetch_latest(device_id=device_id)
    lrs = to_latest_room_state(raw, fetched_at) if raw else None

    ts_str, age_hint, ts_age_min = parse_freshness(raw, fetched_at)
    pill_html = freshness_badge(source_state_from_age(raw, ts_age_min))

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">'
        f'<div style="display:flex;align-items:baseline;gap:12px;">'
        f'<span style="font-size:1.4rem;font-weight:800;color:#D8EEFF;">Coach</span>'
        f'<span style="font-size:0.78rem;color:#334455;">{ts_str}&nbsp;&nbsp;{age_hint}</span>'
        f'</div><div>{pill_html}</div></div>'
        f'<div style="height:1px;background:#111E2E;margin-bottom:20px;"></div>',
        unsafe_allow_html=True,
    )

    if lrs is None:
        st.markdown(
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
            'padding:32px;text-align:center;margin-bottom:20px;">'
            '<div style="font-size:1rem;font-weight:600;color:#446688;margin-bottom:8px;">'
            'Waiting for the first reading.</div>'
            '<div style="font-size:0.85rem;color:#334455;line-height:1.7;max-width:480px;margin:0 auto;">'
            'Once the device sends a reading, Coach will recommend a specific action — whether to ventilate, '
            'hydrate, rest, or do nothing — based on the current room state, air quality, and time of day. '
            'Each recommendation includes a reason, a next step, and the expected benefit.'
            '</div></div>',
            unsafe_allow_html=True,
        )
        return

    ritual      = get_ritual(lrs)
    alt_ritual  = get_alternative_ritual(ritual.get("ritual_id", "ritual_reset"))
    expl        = lrs.get("explanations", {})
    indoor      = lrs.get("indoor", {})
    outdoor     = lrs.get("outdoor", {})
    suitability = outdoor_suitability(lrs)

    # ── Primary ritual hero ───────────────────────────────────────────────────
    section_label("Recommended Action")
    hero_col, why_col = st.columns([3, 2])

    with hero_col:
        ritual_card(
            title=ritual.get("title", ""),
            subtitle=ritual.get("subtitle", ""),
            reason_lines=ritual.get("reason_lines", []),
            next_step=ritual.get("next_step", ""),
            expected_benefit=ritual.get("expected_benefit", ""),
            priority=ritual.get("priority", "medium"),
            icon=ritual.get("icon", ""),
        )

    with why_col:
        section_label("Why Now")

        # Contextual "why now" sentence based on state + time
        why_sentence = _why_now_sentence(lrs, ritual)
        st.markdown(
            f'<div style="background:#060E18;border-left:3px solid #1A3A5A;border-radius:0 8px 8px 0;'
            f'padding:10px 14px;margin-bottom:14px;">'
            f'<span style="font-size:0.85rem;color:#AABCCC;">{why_sentence}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        section_label("Room Factors")
        _factor_row("Room State",  lrs.get("room_state") or "—",              "#AAAACC")
        _factor_row("Readiness",   _score_str(lrs.get("readiness_score")),     _score_color(lrs.get("readiness_score"), False))
        _factor_row("Recovery",    _score_str(lrs.get("recovery_score")),      "#66CCFF")
        _factor_row("Air Strain",  _score_str(lrs.get("air_strain_score")),    _score_color(lrs.get("air_strain_score"), True))

        if indoor.get("humidity_pct") is not None:
            _factor_row("Humidity", f"{indoor['humidity_pct']:.0f}%",
                        "#66CCFF" if 40 <= indoor["humidity_pct"] <= 65 else "#FFAA00")
        if indoor.get("tvoc_ppb") is not None:
            tvoc_lbl = indoor.get("tvoc_label", "")
            _factor_row("Air Quality",
                        f"{indoor['tvoc_ppb']:.0f} ppb  ·  {tvoc_lbl}".strip("  · "),
                        "#3DFF8A" if indoor["tvoc_ppb"] < 100 else "#FFCC00")

    # ── Alternative suggestion ────────────────────────────────────────────────
    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    section_label("Alternative")

    _compact_ritual_card(
        title=alt_ritual.get("title", ""),
        subtitle=alt_ritual.get("subtitle", ""),
        next_step=alt_ritual.get("next_step", ""),
        priority=alt_ritual.get("priority", "low"),
        icon=alt_ritual.get("icon", ""),
    )

    # ── Outdoor context ───────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    section_label("Outdoor Context")

    o_temp  = outdoor.get("temperature_c")
    o_hum   = outdoor.get("humidity_pct")
    o_desc  = (outdoor.get("weather_main") or "—").title()
    temp_part = f"{o_temp:.1f} °C" if o_temp is not None else "—"
    hum_part  = f"{o_hum:.0f}%" if o_hum is not None else "—"
    suit_color = (
        "#3DFF8A" if "good" in suitability.lower() or "suitable" in suitability.lower() else
        "#FF8844" if any(w in suitability.lower() for w in ("unfavourable", "cold", "heat")) else
        "#FFCC00"
    )
    st.markdown(
        f'<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;padding:16px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
        f'<span style="color:#445566;font-size:0.82rem;">{o_desc}  ·  {temp_part}  ·  {hum_part}</span>'
        f'</div>'
        f'<div style="padding:8px 12px;background:#060E18;border-radius:8px;'
        f'border-left:3px solid {suit_color};">'
        f'<span style="font-size:0.85rem;color:{suit_color};">{suitability}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


# ── Sub-components ────────────────────────────────────────────────────────────

_PRIORITY_COLOR = {"high": "#FF8844", "medium": "#FFCC00", "low": "#66CCFF"}
_ICON_GLYPH     = {"wind": "◈", "drop": "◉", "moon": "◐", "arrow": "▶", "leaf": "◆", "pause": "◎"}


def _compact_ritual_card(title: str, subtitle: str, next_step: str, priority: str, icon: str) -> None:
    color = _PRIORITY_COLOR.get(priority, "#66CCFF")
    glyph = _ICON_GLYPH.get(icon, "")
    st.markdown(
        f'<div style="background:#0A1220;border:1px solid {color}33;border-radius:10px;'
        f'padding:14px 18px;display:flex;align-items:center;gap:14px;">'
        f'<span style="font-size:1.2rem;color:{color};">{glyph}</span>'
        f'<div>'
        f'<div style="font-size:0.88rem;font-weight:700;color:{color};">{title}</div>'
        f'<div style="font-size:0.78rem;color:#556677;margin-top:2px;">{subtitle}</div>'
        f'<div style="font-size:0.78rem;color:#445566;margin-top:4px;">{next_step}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _why_now_sentence(lrs: dict, ritual: dict) -> str:
    """Generate an explicit "why now" sentence for the recommended ritual."""
    ritual_id = ritual.get("ritual_id", "")
    indoor    = lrs.get("indoor", {})
    strain    = lrs.get("air_strain_score")
    readiness = lrs.get("readiness_score")
    recovery  = lrs.get("recovery_score")
    humidity  = indoor.get("humidity_pct")
    temp      = indoor.get("temperature_c")

    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour

    if ritual_id == "ritual_ventilate":
        return f"Air strain is at {strain} — above the 60-point threshold where air quality visibly affects comfort and focus."
    if ritual_id == "ritual_hydrate":
        hum_str = f"{humidity:.0f}%" if humidity is not None else "below 40%"
        return f"Humidity is at {hum_str} — dry air increases fatigue and reduces comfort, especially for extended stays."
    if ritual_id == "ritual_winddown":
        return f"It's {hour}:00 and recovery conditions are strong ({recovery}). Evening is the best time to transition to rest."
    if ritual_id == "ritual_focus":
        return f"Readiness is at {readiness} with clean air — this is a good window for concentrated work before conditions shift."
    if ritual_id == "ritual_outside":
        o_temp = (lrs.get("outdoor") or {}).get("temperature_c")
        temp_str = f"{o_temp:.0f}°C" if o_temp is not None else "mild"
        return f"Outdoor conditions are {temp_str} — a brief break outside improves alertness and resets focus."
    return "Conditions support a short mental reset. Brief breaks prevent attention fatigue and improve overall performance."


def _factor_row(label: str, value: str, color: str) -> None:
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #0F1A28;">'
        f'<span style="color:#445566;font-size:0.8rem;">{label}</span>'
        f'<span style="color:{color};font-weight:600;font-size:0.85rem;">{value}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _score_str(v) -> str:
    return str(v) if v is not None else "—"


def _score_color(v, low_good: bool) -> str:
    if v is None:
        return "#556677"
    if low_good:
        return "#3DFF8A" if v < 30 else "#FFAA00" if v < 60 else "#FF4422"
    return "#3DFF8A" if v >= 75 else "#FFAA00" if v >= 50 else "#FF4422"
