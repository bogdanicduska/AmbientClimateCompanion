"""
4.5  RitualCard — primary coach recommendation.
Props: title, subtitle, reason_lines, next_step, expected_benefit, priority, icon
"""

import streamlit as st

_PRIORITY_COLOR = {
    "high":   "#FF8844",
    "medium": "#FFCC00",
    "low":    "#66CCFF",
}

_ICON_GLYPH = {
    "wind":  "◈",
    "drop":  "◉",
    "moon":  "◐",
    "arrow": "▶",
    "leaf":  "◆",
    "pause": "◎",
}


def ritual_card(
    title:            str,
    subtitle:         str = "",
    reason_lines:     list[str] | None = None,
    next_step:        str = "",
    expected_benefit: str = "",
    priority:         str = "medium",
    icon:             str = "",
) -> None:
    """
    Acceptance criteria:
    - hero recommendation visible above the fold on Coach page
    - max 2 reason lines shown
    - next_step is concise and actionable
    - icon optional but rendered when present
    """
    reason_lines = (reason_lines or [])[:2]
    color        = _PRIORITY_COLOR.get(priority, "#66CCFF")
    glyph        = _ICON_GLYPH.get(icon, "")

    icon_html = (
        f'<span style="font-size:1.4rem;color:{color};margin-right:10px;">{glyph}</span>'
        if glyph else ""
    )

    reasons_html = "".join(
        f'<div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid #0F1A28;">'
        f'<span style="color:{color};font-size:0.85rem;margin-top:1px;">▸</span>'
        f'<span style="color:#AABBCC;font-size:0.85rem;">{r}</span>'
        f'</div>'
        for r in reason_lines
    )

    next_html = (
        f'<div style="margin-top:14px;padding:10px 12px;background:#0A1825;border-radius:8px;'
        f'border-left:3px solid {color};">'
        f'<div style="font-size:0.65rem;color:#2A4A6A;letter-spacing:0.14em;'
        f'text-transform:uppercase;margin-bottom:4px;">Next step</div>'
        f'<div style="font-size:0.88rem;color:#C8D8E8;">{next_step}</div>'
        f'</div>'
        if next_step else ""
    )

    benefit_html = (
        f'<div style="margin-top:8px;font-size:0.75rem;color:#445566;">{expected_benefit}</div>'
        if expected_benefit else ""
    )

    st.markdown(
        f'<div style="background:#080F1A;border:1px solid {color}44;border-radius:14px;padding:24px;">'
        f'<div style="display:flex;align-items:center;margin-bottom:4px;">'
        f'{icon_html}'
        f'<div style="font-size:1.5rem;font-weight:800;color:{color};letter-spacing:0.04em;">{title}</div>'
        f'</div>'
        f'<div style="font-size:0.85rem;color:#667788;margin-bottom:16px;">{subtitle}</div>'
        f'{reasons_html}'
        f'{next_html}'
        f'{benefit_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
