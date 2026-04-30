import time
import streamlit as st
from services.api_client import DEFAULT_DEVICE_ID, KNOWN_DEVICES

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Room Rhythm",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.markdown(
    """<style>
    html, body,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stHeader"] { background-color: #070C14 !important; color: #C8D8E8; }
    [data-testid="stSidebar"] { background-color: #080E18 !important; border-right: 1px solid #1A2A3A; }
    .block-container { padding-top: 3.5rem !important; padding-bottom: 2rem !important; max-width: 1200px; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #070C14; }
    ::-webkit-scrollbar-thumb { background: #1A2A3A; border-radius: 3px; }
    [data-testid="stDecoration"] { display: none; }
    footer { display: none; }
    #MainMenu { display: none; }
    </style>""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
from pages import home, rhythm, coach, memory, device as device_page  # noqa: E402

pg = st.navigation({
    "Overview": [
        st.Page(home.render,        title="Home",   icon="🏠", url_path="home",   default=True),
        st.Page(coach.render,       title="Coach",  icon="💡", url_path="coach"),
    ],
    "History": [
        st.Page(rhythm.render,      title="Rhythm", icon="📈", url_path="rhythm"),
        st.Page(memory.render,      title="Memory", icon="🕐", url_path="memory"),
    ],
    "System": [
        st.Page(device_page.render, title="Device", icon="📡", url_path="device"),
    ],
})

# ---------------------------------------------------------------------------
# Shared sidebar (shown on every page)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div style="font-size:1rem;font-weight:700;color:#88CCFF;'
        'letter-spacing:0.08em;margin-bottom:4px;">ROOM RHYTHM</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Default: `{DEFAULT_DEVICE_ID}`")
    st.divider()

    device_id = st.selectbox(
        "Device",
        options=KNOWN_DEVICES,
        index=KNOWN_DEVICES.index(DEFAULT_DEVICE_ID) if DEFAULT_DEVICE_ID in KNOWN_DEVICES else 0,
        key="device_id",
    )

    st.divider()
    auto_refresh = st.toggle("Auto-refresh (60 s)", value=True)
    if st.button("↺  Refresh now", use_container_width=True):
        st.rerun()

    st.divider()
    st.select_slider(
        "History window",
        options=[6, 12, 24, 72, 168],
        value=24,
        format_func=lambda h: {6: "6 h", 12: "12 h", 24: "24 h", 72: "3 days", 168: "7 days"}.get(h, f"{h} h"),
        key="history_hours",
    )

    st.divider()
    st.caption("Data: `/latest` + `/history` + `/events`")

# ---------------------------------------------------------------------------
# Run the selected page
# ---------------------------------------------------------------------------
pg.run()

# ---------------------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------------------
if auto_refresh:
    time.sleep(60)
    st.rerun()
