import time
from datetime import datetime, timezone

import streamlit as st

from queries import fetch_latest, fetch_history, fetch_events, DEVICE_ID
from components import (
    score_card,
    room_state_card,
    sensor_row,
    snapshot_card_open,
    snapshot_card_close,
    status_pill,
    event_panel,
)
from charts import (
    history_to_df,
    room_scores_chart,
    temperature_chart,
    humidity_chart,
    tvoc_chart,
    eco2_chart,
    motion_chart,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Room Rhythm",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Global CSS — dark theme, card system, typography
# ---------------------------------------------------------------------------
st.markdown(
    """<style>
    /* ---------- background ---------- */
    html, body,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stHeader"] {
        background-color: #070C14 !important;
        color: #C8D8E8;
    }
    [data-testid="stSidebar"] {
        background-color: #080E18 !important;
        border-right: 1px solid #1A2A3A;
    }
    /* ---------- layout ---------- */
    .block-container {
        padding-top: 3.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 1200px;
    }
    /* ---------- links / buttons ---------- */
    button[kind="primary"] {
        background-color: #1A3A5A !important;
        color: #88CCFF !important;
        border: 1px solid #2A4A6A !important;
    }
    /* ---------- scrollbar ---------- */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #070C14; }
    ::-webkit-scrollbar-thumb { background: #1A2A3A; border-radius: 3px; }
    /* ---------- hide default Streamlit decorations ---------- */
    [data-testid="stDecoration"] { display: none; }
    footer { display: none; }
    #MainMenu { display: none; }
    </style>""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """<div style="font-size:1rem;font-weight:700;color:#88CCFF;
                       letter-spacing:0.08em;margin-bottom:4px;">ROOM RHYTHM</div>""",
        unsafe_allow_html=True,
    )
    st.caption(f"Device: `{DEVICE_ID}`")
    st.divider()
    auto_refresh = st.toggle("Auto-refresh (60 s)", value=True)
    if st.button("↺  Refresh now", use_container_width=True):
        st.rerun()
    st.divider()
    history_hours = st.select_slider(
        "History window",
        options=[6, 12, 24, 48, 168],
        value=24,
        format_func=lambda h: f"{h} h" if h < 168 else "7 days",
    )
    st.divider()
    st.caption("Data: `/latest` + `/history` → room metrics computed locally")

# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------
row = fetch_latest()
fetched_at = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# Parse timestamp
# ---------------------------------------------------------------------------
ts_str = ""
ts_age_min = None
if row and row.get("timestamp"):
    try:
        ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        ts_str = ts.strftime("%a %d %b  ·  %H:%M")
        ts_age_min = int((fetched_at - ts).total_seconds() / 60)
    except Exception:
        ts_str = row["timestamp"][:16]

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
dot = "🟢" if row is not None else "🔴"

pill_html = ""
if row is None:
    pill_html = status_pill("OFFLINE", "#FF4444")
elif ts_age_min is not None and ts_age_min < 10:
    pill_html = status_pill("LIVE", "#3DFF8A")
elif ts_age_min is not None and ts_age_min < 30:
    pill_html = status_pill("RECENT", "#FFCC00")
else:
    pill_html = status_pill("STALE", "#FF8844")

st.markdown(
    f"""<div style="display:flex;align-items:center;justify-content:space-between;
                    margin-bottom:4px;">
          <div style="display:flex;align-items:center;gap:14px;">
            <span style="font-size:1.6rem;font-weight:800;color:#D8EEFF;
                         letter-spacing:0.04em;">Room Rhythm</span>
            <span style="font-size:0.8rem;color:#334455;">
              {ts_str}
              {"&nbsp;&nbsp;·&nbsp;&nbsp;" + str(ts_age_min) + " min ago" if ts_age_min is not None else ""}
            </span>
          </div>
          <div>{pill_html}</div>
        </div>
        <div style="height:1px;background:#111E2E;margin-bottom:20px;"></div>""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# No data state
# ---------------------------------------------------------------------------
if row is None:
    st.markdown(
        """<div style="background:#1A0808;border:1px solid #4A1010;border-radius:12px;
                       padding:24px;text-align:center;color:#FF8888;">
             <div style="font-size:1.2rem;font-weight:600;margin-bottom:6px;">
               Could not reach backend
             </div>
             <div style="font-size:0.85rem;color:#886666;">
               Check BACKEND_URL environment variable or network connection.
             </div>
           </div>""",
        unsafe_allow_html=True,
    )
    if auto_refresh:
        time.sleep(60)
        st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# Section label helper
# ---------------------------------------------------------------------------
def section_label(text: str) -> None:
    st.markdown(
        f"""<div style="font-size:0.68rem;color:#2A4A6A;letter-spacing:0.18em;
                        text-transform:uppercase;margin:20px 0 12px 0;">{text}</div>""",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Hero — Room Performance Scores
# ---------------------------------------------------------------------------
section_label("Room Performance")

c1, c2, c3, c4 = st.columns(4)

with c1:
    score_card("Room Readiness", row.get("room_readiness"))
with c2:
    score_card("Recovery Score", row.get("recovery_score"))
with c3:
    score_card("Air Strain", row.get("air_strain"), low_good=True)
with c4:
    room_state_card(row.get("room_state"))

# ---------------------------------------------------------------------------
# Current Room Snapshot  |  Outdoor Context
# ---------------------------------------------------------------------------
st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
section_label("Current Room Snapshot")

left, right = st.columns([5, 3])

# --- Indoor ---
with left:
    temp     = row.get("indoor_temp")
    humidity = row.get("indoor_humidity")
    tvoc     = row.get("air_quality")
    eco2     = row.get("indoor_eco2")
    pressure = row.get("indoor_pressure")
    motion   = row.get("motion")
    aq_label = row.get("air_quality_label") or "—"

    temp_color = "#3DFF8A" if temp is not None and 18 <= temp <= 26 else "#FF8844"
    hum_color  = "#66CCFF" if humidity is not None and 40 <= humidity <= 65 else "#FFAA00"
    tvoc_color = (
        "#3DFF8A"  if tvoc is not None and tvoc < 100  else
        "#FFCC00"  if tvoc is not None and tvoc < 150  else
        "#FF8844"  if tvoc is not None and tvoc < 200  else
        "#FF4422"
    )

    snapshot_card_open("Indoor Environment")
    sensor_row("Temperature",
               f"{temp:.1f}" if temp is not None else None, "°C", temp_color)
    sensor_row("Humidity",
               f"{humidity:.0f}" if humidity is not None else None, "%", hum_color)
    sensor_row("Air Quality (TVOC)",
               f"{tvoc:.0f} ppb  ·  {aq_label}" if tvoc is not None else None, "", tvoc_color)
    sensor_row("eCO₂",
               f"{eco2:.0f}" if eco2 is not None else None, "ppm", "#FFCC99")
    sensor_row("Pressure",
               f"{pressure:.0f}" if pressure is not None else None, "hPa", "#667788")
    sensor_row("Motion",
               "Detected" if motion else "None", "",
               "#DDDD00" if motion else "#2A3A4A")
    snapshot_card_close()

# --- Outdoor + Sync ---
with right:
    o_temp = row.get("outdoor_temp")
    o_hum  = row.get("outdoor_humidity")
    o_desc = row.get("outdoor_weather") or "—"
    o_stat = row.get("weather_status")  or "—"

    snapshot_card_open("Outdoor Context")
    sensor_row("Temperature",
               f"{o_temp:.1f}" if o_temp is not None else None, "°C", "#88CCFF")
    sensor_row("Humidity",
               f"{o_hum:.0f}" if o_hum is not None else None, "%", "#66AACC")
    sensor_row("Conditions",  o_desc.title(), "", "#AAAACC")
    sensor_row("Summary",     o_stat.title(), "", "#556677")
    snapshot_card_close()

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    snapshot_card_open("Sync Info")
    sensor_row("Last reading",  ts_str or "—", "", "#446688")
    sensor_row("Data age",
               f"{ts_age_min} min" if ts_age_min is not None else "—", "", "#334455")
    sensor_row("WiFi RSSI",
               row.get("wifi_rssi"), "dBm", "#445566")
    sensor_row("Fetched at",
               fetched_at.strftime("%H:%M:%S"), "UTC", "#334455")
    snapshot_card_close()

# ---------------------------------------------------------------------------
# Room Events
# ---------------------------------------------------------------------------
st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
section_label("Room Events")

with st.spinner("Loading events…"):
    recent_events = fetch_events(limit=20)

event_panel(recent_events)

# ---------------------------------------------------------------------------
# History charts
# ---------------------------------------------------------------------------
st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
hours_label = f"{history_hours} h" if history_hours < 168 else "7 days"
section_label(f"Room History — last {hours_label}")

with st.spinner("Loading history…"):
    history_rows = fetch_history(hours=history_hours)
    df = history_to_df(history_rows)

if df is None or df.empty:
    st.markdown(
        """<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;
                       padding:24px;text-align:center;color:#334455;">
             No history data available for the selected window.
           </div>""",
        unsafe_allow_html=True,
    )
else:
    n_points = len(df)
    st.caption(f"{n_points} readings · "
               f"{df['timestamp'].min().strftime('%d %b %H:%M')} → "
               f"{df['timestamp'].max().strftime('%d %b %H:%M')}")

    # ── Room performance scores (full width, most important) ──────────────
    st.plotly_chart(room_scores_chart(df), use_container_width=True)

    # ── Environmental inputs (2-column grid) ─────────────────────────────
    section_label("Environmental Inputs")
    env1, env2 = st.columns(2)
    with env1:
        st.plotly_chart(temperature_chart(df), use_container_width=True)
    with env2:
        st.plotly_chart(humidity_chart(df), use_container_width=True)

    has_tvoc = df["air_quality"].notna().any()
    has_eco2 = df["indoor_eco2"].notna().any()
    if has_tvoc or has_eco2:
        aq1, aq2 = st.columns(2)
        with aq1:
            if has_tvoc:
                st.plotly_chart(tvoc_chart(df), use_container_width=True)
        with aq2:
            if has_eco2:
                st.plotly_chart(eco2_chart(df), use_container_width=True)

    # ── Motion / activity (full width) ───────────────────────────────────
    if "motion" in df.columns and df["motion"].notna().any():
        section_label("Room Activity")
        st.plotly_chart(motion_chart(df), use_container_width=True)


# ---------------------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------------------
if auto_refresh:
    time.sleep(60)
    st.rerun()
