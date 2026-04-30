import time
from datetime import datetime, timezone

import streamlit as st

from queries import fetch_latest, fetch_history, fetch_events, DEFAULT_DEVICE_ID, KNOWN_DEVICES
from components import (
    score_card,
    room_state_card,
    sensor_row,
    snapshot_card_open,
    snapshot_card_close,
    status_pill,
    story_card,
    weather_insight_card,
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
from insights import score_explanations, score_trend, daily_story, outdoor_suitability

# ---------------------------------------------------------------------------
# Page config
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
# Section label helper
# ---------------------------------------------------------------------------
def section_label(text: str) -> None:
    st.markdown(
        f'<div style="font-size:0.68rem;color:#2A4A6A;letter-spacing:0.18em;'
        f'text-transform:uppercase;margin:20px 0 12px 0;">{text}</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Sidebar
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
    )
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
    st.caption("Data: `/latest` + `/history` · Room metrics computed locally")

# ---------------------------------------------------------------------------
# Data fetch — history fetched early so trends can use it in the hero section
# ---------------------------------------------------------------------------
row        = fetch_latest(device_id=device_id)
fetched_at = datetime.now(timezone.utc)

with st.spinner("Loading history…"):
    history_rows = fetch_history(device_id=device_id, hours=history_hours)
    df = history_to_df(history_rows)

# ---------------------------------------------------------------------------
# Parse timestamp + build status pill
# ---------------------------------------------------------------------------
ts_str     = ""
ts_age_min = None
if row and row.get("timestamp"):
    try:
        ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        ts_str     = ts.strftime("%a %d %b  ·  %H:%M")
        ts_age_min = int((fetched_at - ts).total_seconds() / 60)
    except Exception:
        ts_str = row["timestamp"][:16]

if row is None:
    pill_html = status_pill("OFFLINE", "#FF4444")
    age_hint  = ""
elif ts_age_min is not None and ts_age_min < 10:
    pill_html = status_pill("LIVE", "#3DFF8A")
    age_hint  = f"· last sync {ts_age_min} min ago"
elif ts_age_min is not None and ts_age_min < 30:
    pill_html = status_pill("RECENT", "#FFCC00")
    age_hint  = f"· synced {ts_age_min} min ago"
else:
    pill_html = status_pill("STALE", "#FF8844")
    age_hint  = (
        f"· last sync {ts_age_min} min ago · showing cached state"
        if ts_age_min is not None else "· no recent data"
    )

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.markdown(
    f"""<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
          <div style="display:flex;align-items:center;gap:14px;">
            <span style="font-size:1.6rem;font-weight:800;color:#D8EEFF;letter-spacing:0.04em;">Room Rhythm</span>
            <span style="font-size:0.78rem;color:#3A5A7A;">{device_id}</span>
            <span style="font-size:0.78rem;color:#334455;">{ts_str}&nbsp;&nbsp;{age_hint}</span>
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
             <div style="font-size:1.2rem;font-weight:600;margin-bottom:6px;">Could not reach backend</div>
             <div style="font-size:0.85rem;color:#886666;">
               Check BACKEND_URL or network connection.
             </div>
           </div>""",
        unsafe_allow_html=True,
    )
    if auto_refresh:
        time.sleep(60)
        st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# Compute insights (explanations + trends)
# ---------------------------------------------------------------------------
why    = score_explanations(row)
r_arr, r_lbl, r_clr = score_trend(row.get("room_readiness"), df, "room_readiness")
v_arr, v_lbl, v_clr = score_trend(row.get("recovery_score"), df, "recovery_score")
s_arr, s_lbl, s_clr = score_trend(row.get("air_strain"),     df, "air_strain")

# ---------------------------------------------------------------------------
# Hero — Room Performance Scores
# ---------------------------------------------------------------------------
section_label("Room Performance")

c1, c2, c3, c4 = st.columns(4)
with c1:
    score_card("Room Readiness", row.get("room_readiness"),
               explanation=why["readiness_why"],
               trend_arrow=r_arr, trend_label=r_lbl, trend_color=r_clr)
with c2:
    score_card("Recovery Score", row.get("recovery_score"),
               explanation=why["recovery_why"],
               trend_arrow=v_arr, trend_label=v_lbl, trend_color=v_clr)
with c3:
    score_card("Air Strain", row.get("air_strain"), low_good=True,
               explanation=why["strain_why"],
               trend_arrow=s_arr, trend_label=s_lbl, trend_color=s_clr)
with c4:
    room_state_card(row.get("room_state"))

# ---------------------------------------------------------------------------
# Current Room Snapshot  |  Outdoor Context
# ---------------------------------------------------------------------------
st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
section_label("Current Room Snapshot")

left, right = st.columns([5, 3])

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
        "#3DFF8A" if tvoc is not None and tvoc < 100  else
        "#FFCC00" if tvoc is not None and tvoc < 150  else
        "#FF8844" if tvoc is not None and tvoc < 200  else
        "#FF4422"
    )

    snapshot_card_open("Indoor Environment")
    sensor_row("Temperature",      f"{temp:.1f}" if temp is not None else None,         "°C",  temp_color)
    sensor_row("Humidity",         f"{humidity:.0f}" if humidity is not None else None, "%",   hum_color)
    sensor_row("Air Quality (TVOC)", f"{tvoc:.0f} ppb  ·  {aq_label}" if tvoc is not None else None, "", tvoc_color)
    sensor_row("eCO₂",             f"{eco2:.0f}" if eco2 is not None else None,         "ppm", "#FFCC99")
    sensor_row("Pressure",         f"{pressure:.0f}" if pressure is not None else None, "hPa", "#667788")
    sensor_row("Motion",           "Detected" if motion else "None", "",
               "#DDDD00" if motion else "#2A3A4A")
    snapshot_card_close()

with right:
    suitability = outdoor_suitability(row)
    weather_insight_card(row, suitability)

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    snapshot_card_open("Sync Info")
    sensor_row("Last reading",  ts_str or "—",                          "",    "#446688")
    sensor_row("Data age",      f"{ts_age_min} min" if ts_age_min is not None else "—", "", "#556677")
    sensor_row("WiFi RSSI",     row.get("wifi_rssi"),                   "dBm", "#445566")
    sensor_row("Fetched at",    fetched_at.strftime("%H:%M:%S"),         "UTC", "#334455")
    snapshot_card_close()

# ---------------------------------------------------------------------------
# Daily Room Story  (requires history)
# ---------------------------------------------------------------------------
if df is not None and not df.empty:
    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
    hours_label = f"{history_hours} h" if history_hours < 168 else "7 days"
    sentences = daily_story(df)
    story_card(sentences, window_label=f"last {hours_label}")

# ---------------------------------------------------------------------------
# Room Events
# ---------------------------------------------------------------------------
st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
section_label("Room Events")

with st.spinner("Loading events…"):
    recent_events = fetch_events(device_id=device_id, limit=20)

event_panel(recent_events)

# ---------------------------------------------------------------------------
# History charts
# ---------------------------------------------------------------------------
st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
hours_label = f"{history_hours} h" if history_hours < 168 else "7 days"
section_label(f"Room History — last {hours_label}")

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
    st.caption(
        f"{n_points} readings  ·  "
        f"{df['timestamp'].min().strftime('%d %b %H:%M')} → "
        f"{df['timestamp'].max().strftime('%d %b %H:%M')}"
    )

    st.plotly_chart(room_scores_chart(df), use_container_width=True)

    section_label("Environmental Inputs")
    env1, env2 = st.columns(2)
    with env1:
        st.plotly_chart(temperature_chart(df), use_container_width=True)
    with env2:
        st.plotly_chart(humidity_chart(df), use_container_width=True)

    has_tvoc = "air_quality"  in df.columns and df["air_quality"].notna().any()
    has_eco2 = "indoor_eco2" in df.columns and df["indoor_eco2"].notna().any()
    if has_tvoc or has_eco2:
        aq1, aq2 = st.columns(2)
        with aq1:
            if has_tvoc:
                st.plotly_chart(tvoc_chart(df), use_container_width=True)
        with aq2:
            if has_eco2:
                st.plotly_chart(eco2_chart(df), use_container_width=True)

    if "motion" in df.columns and df["motion"].notna().any():
        section_label("Room Activity")
        st.plotly_chart(motion_chart(df), use_container_width=True)

# ---------------------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------------------
if auto_refresh:
    time.sleep(60)
    st.rerun()
