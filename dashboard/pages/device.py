"""
Device — trust and operational visibility.
Answers: Is the device healthy? Is the data fresh? What source am I seeing?
"""

import streamlit as st
from datetime import datetime, timezone

from services.api_client import fetch_latest, fetch_events
from services.transformers import to_latest_room_state
from services.event_transformer import to_room_events
from services.contracts import SourceState

from components.section_header import section_label
from components.snapshot_table import snapshot_card_open, snapshot_card_close, sensor_row
from components.event_timeline import event_timeline
from components.freshness_badge import parse_freshness, freshness_badge, source_state_from_age

_SOURCE_LABEL = {
    "live":    ("LIVE",    "#3DFF8A", "Data is current — last sync within 10 minutes."),
    "cloud":   ("CLOUD",   "#FFCC00", "Recent cloud sync — data is 10–30 minutes old."),
    "cache":   ("CACHE",   "#778899", "Device is showing cached data — no recent sync."),
    "stale":   ("STALE",   "#FF8844", "Data is older than 30 minutes — may not reflect current conditions."),
    "offline": ("OFFLINE", "#FF4422", "Device is unreachable — no data available."),
}


def render() -> None:
    device_id  = st.session_state.get("device_id", "m5stack-duska-home")
    fetched_at = datetime.now(timezone.utc)

    raw = fetch_latest(device_id=device_id)
    lrs = to_latest_room_state(raw, fetched_at) if raw else None

    ts_str, age_hint, ts_age_min = parse_freshness(raw, fetched_at)
    source_state = source_state_from_age(raw, ts_age_min)
    pill_html    = freshness_badge(source_state)

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">'
        f'<div style="display:flex;align-items:baseline;gap:12px;">'
        f'<span style="font-size:1.4rem;font-weight:800;color:#D8EEFF;">Device</span>'
        f'<span style="font-size:0.78rem;color:#334455;">{device_id}</span>'
        f'</div><div>{pill_html}</div></div>'
        f'<div style="height:1px;background:#111E2E;margin-bottom:20px;"></div>',
        unsafe_allow_html=True,
    )

    # ── Freshness / source state banner ───────────────────────────────────────
    lbl, color, description = _SOURCE_LABEL.get(source_state, ("UNKNOWN", "#778899", ""))
    st.markdown(
        f'<div style="background:{color}11;border:1px solid {color}33;border-radius:10px;'
        f'padding:12px 16px;margin-bottom:20px;display:flex;align-items:center;gap:14px;">'
        f'<span style="background:{color}22;color:{color};border:1px solid {color}55;'
        f'border-radius:4px;padding:2px 10px;font-size:0.75rem;font-weight:700;'
        f'letter-spacing:0.08em;">{lbl}</span>'
        f'<span style="font-size:0.85rem;color:#AABCCC;">{description}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Device identity | Sync health ─────────────────────────────────────────
    section_label("Device Health")
    left, right = st.columns(2)

    sync   = (lrs or {}).get("sync", {})
    indoor = (lrs or {}).get("indoor", {})

    with left:
        snapshot_card_open("Device Identity")
        sensor_row("Device ID",    device_id,                                              "",    "#3A5A7A")
        sensor_row("Source",       source_state.upper(),                                    "",    color)
        sensor_row("Last reading", ts_str or "—",                                           "",    "#446688")
        sensor_row("Data age",     f"{ts_age_min} min" if ts_age_min is not None else "—", "",    "#556677")
        if lrs:
            sensor_row("Room State", lrs.get("room_state") or "—",                        "",    "#AABBCC")
        snapshot_card_close()

    with right:
        snapshot_card_open("Sync Status")
        sensor_row("Cloud sync",      sync.get("cloud_sync_state") or "—",  "", _sync_c(sync.get("cloud_sync_state")))
        sensor_row("Telemetry",       sync.get("telemetry_state")  or "—",  "", _sync_c(sync.get("telemetry_state")))
        sensor_row("Weather data",    sync.get("weather_freshness") or "—", "", _fresh_c(sync.get("weather_freshness")))
        sensor_row("Last reading at", sync.get("last_reading_at", "")[:16] or "—", "", "#334455")
        sensor_row("Fetched at",      fetched_at.strftime("%H:%M:%S"),      "UTC", "#334455")
        snapshot_card_close()

    # ── Connectivity / network quality ────────────────────────────────────────
    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    section_label("Network Quality")
    _wifi_card(indoor)

    # ── Technical snapshot ────────────────────────────────────────────────────
    if lrs:
        st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
        section_label("Latest Reading")
        snap1, snap2 = st.columns(2)
        with snap1:
            snapshot_card_open("Sensors")
            temp = indoor.get("temperature_c")
            hum  = indoor.get("humidity_pct")
            tvoc = indoor.get("tvoc_ppb")
            eco2 = indoor.get("eco2_ppm")
            sensor_row("Temperature", f"{temp:.1f}" if temp is not None else None, "°C",  "#00FFCC")
            sensor_row("Humidity",    f"{hum:.0f}"  if hum  is not None else None, "%",   "#66CCFF")
            sensor_row("TVOC",        f"{tvoc:.0f}" if tvoc is not None else None, "ppb", "#FFCC00")
            sensor_row("eCO₂",        f"{eco2:.0f}" if eco2 is not None else None, "ppm", "#FFCC99")
            snapshot_card_close()
        with snap2:
            snapshot_card_open("Room Scores")
            sensor_row("Readiness",  str(lrs.get("readiness_score") or "—"),   "/100", "#3DFF8A")
            sensor_row("Recovery",   str(lrs.get("recovery_score")  or "—"),   "/100", "#66CCFF")
            sensor_row("Air Strain", str(lrs.get("air_strain_score") or "—"),  "/100", "#FF8844")
            snapshot_card_close()

    # ── Device events (technical only) ────────────────────────────────────────
    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    section_label("Device Event Log")

    with st.spinner("Loading events…"):
        raw_events = fetch_events(device_id=device_id, limit=30)
        events     = to_room_events(raw_events)

    # Filter to device/system events only (not environmental alerts).
    # Full event type list lives in backend/app/utils/validators.py VALID_EVENT_TYPES.
    device_event_types = {
        "wifi_connected", "wifi_disconnected", "wifi_failed",
        "room_online", "room_state_restored", "room_synced", "room_sync_failed",
        "cache_loaded", "boot_recovered",
    }
    device_events = [e for e in events if e.get("event_type", "") in device_event_types]
    other_events  = [e for e in events if e.get("event_type", "") not in device_event_types]

    if device_events:
        event_timeline(device_events, max_items=20)
    elif events:
        st.markdown(
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
            'padding:16px;color:#334455;font-size:0.85rem;">'
            'No device-specific events in log — showing all events below.</div>',
            unsafe_allow_html=True,
        )
        event_timeline(events, max_items=10)
    else:
        st.markdown(
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
            'padding:16px;color:#334455;font-size:0.85rem;">'
            'No device events yet. As the device runs, this log will show WiFi connections, '
            'cloud sync confirmations, boot recoveries, and sensor calibration events.</div>',
            unsafe_allow_html=True,
        )

    if other_events and device_events:
        with st.expander(f"Room events ({len(other_events)})", expanded=False):
            event_timeline(other_events, max_items=15)


# ── Sub-components ────────────────────────────────────────────────────────────

def _wifi_card(indoor: dict) -> None:
    rssi = indoor.get("wifi_rssi")
    if rssi is None:
        st.markdown(
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
            'padding:16px;color:#334455;font-size:0.85rem;">WiFi data not available.</div>',
            unsafe_allow_html=True,
        )
        return

    if rssi >= -50:   quality, color, bars = "Excellent", "#3DFF8A", 4
    elif rssi >= -70: quality, color, bars = "Good",      "#FFCC00", 3
    elif rssi >= -85: quality, color, bars = "Fair",      "#FF8844", 2
    else:             quality, color, bars = "Weak",      "#FF4422", 1

    bars_html = "".join(
        f'<div style="width:10px;height:{10 + i*6}px;background:{"' + color + '" if i < bars else "#1A2A3A"};'
        f'border-radius:2px;margin-right:3px;align-self:flex-end;"></div>'
        for i in range(4)
    )

    st.markdown(
        f'<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;padding:18px;">'
        f'<div style="display:flex;align-items:flex-end;gap:16px;">'
        f'<div style="display:flex;align-items:flex-end;">{bars_html}</div>'
        f'<div>'
        f'<div style="font-size:1.1rem;font-weight:700;color:{color};">{quality}</div>'
        f'<div style="font-size:0.78rem;color:#445566;margin-top:2px;">{rssi} dBm</div>'
        f'</div>'
        f'<div style="margin-left:auto;font-size:0.75rem;color:#334455;">'
        f'≥ -50 excellent  ·  ≥ -70 good  ·  ≥ -85 fair  ·  below weak'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )


def _sync_c(s):
    return {"ok": "#3DFF8A", "failed": "#FF4422", "none": "#556677", "idle": "#556677"}.get(s or "", "#556677")

def _fresh_c(s):
    return {"fresh": "#3DFF8A", "stale": "#FF8844", "failed": "#FF4422"}.get(s or "", "#556677")
