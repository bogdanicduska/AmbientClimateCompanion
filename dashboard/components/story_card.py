"""
4.7  StoryCard — daily room story insight card.
Props: headline, bullets (2-4 items)
"""

import streamlit as st


def story_card(
    headline: str,
    bullets:  list[str],
    window_label: str = "last 24 h",
) -> None:
    """
    Acceptance criteria:
    - looks like a product insight card, not a raw markdown block
    - headline emphasized
    - 2-4 bullets max
    """
    if not headline and not bullets:
        return

    bullets = bullets[:4]

    bullets_html = "".join(
        f'<div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid #0F1A28;">'
        f'<span style="color:#3A8A5A;font-size:0.9rem;margin-top:1px;">▸</span>'
        f'<span style="color:#99AABB;font-size:0.85rem;line-height:1.5;">{b}</span>'
        f'</div>'
        for b in bullets
    )

    headline_html = (
        f'<div style="font-size:1.0rem;color:#DDEEFF;font-weight:700;'
        f'line-height:1.5;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid #0F1A28;">'
        f'{headline}</div>'
        if headline else ""
    )

    st.markdown(
        f'<div style="background:#070F1A;border:1px solid #0F2030;border-radius:12px;padding:20px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
        f'margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #0F1A28;">'
        f'<span style="font-size:0.68rem;color:#5A8AAA;letter-spacing:0.15em;'
        f'text-transform:uppercase;">Daily Room Story</span>'
        f'<span style="font-size:0.7rem;color:#3A5A6A;">{window_label}</span>'
        f'</div>'
        f'{headline_html}'
        f'{bullets_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
