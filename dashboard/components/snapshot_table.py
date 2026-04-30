"""
4.4  SnapshotTable — compact table for indoor or outdoor data.
Props: title, rows: [{label, value, hint?}]
"""

import streamlit as st


def snapshot_card_open(title: str) -> None:
    st.markdown(
        f'<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;padding:20px;">'
        f'<div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.15em;text-transform:uppercase;'
        f'margin-bottom:14px;padding-bottom:6px;border-bottom:1px solid #142030;">{title}</div>',
        unsafe_allow_html=True,
    )


def snapshot_card_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def sensor_row(label: str, value, unit: str = "", color: str = "#CCCCCC", hint: str = "") -> None:
    """
    Single data row. hint is optional supplementary text shown dimly after the value.
    Acceptance criteria: values aligned, hint optional, no default-Streamlit table borders.
    """
    if value is None:
        display = "—"
    else:
        display = f"{value}&nbsp;{unit}".strip() if unit else str(value)

    hint_html = (
        f'<span style="color:#334455;font-size:0.72rem;margin-left:6px;">{hint}</span>'
        if hint else ""
    )

    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
        f'padding:6px 0;border-bottom:1px solid #0F1A28;">'
        f'<span style="color:#445566;font-size:0.8rem;">{label}</span>'
        f'<span style="display:flex;align-items:baseline;">'
        f'<span style="color:{color};font-weight:600;font-size:0.9rem;">{display}</span>'
        f'{hint_html}'
        f'</span></div>',
        unsafe_allow_html=True,
    )


def snapshot_table(title: str, rows: list[dict]) -> None:
    """
    Props: title, rows: [{label, value, hint?}]
    Acceptance criteria: no default-Streamlit table, hint optional, values aligned.
    """
    snapshot_card_open(title)
    for row in rows:
        sensor_row(
            label=row.get("label", ""),
            value=row.get("value"),
            hint=row.get("hint", ""),
        )
    snapshot_card_close()
