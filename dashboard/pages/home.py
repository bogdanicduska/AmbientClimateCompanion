"""
Home — daily check-in page.
Answers: What is happening now? Why does it matter? What should I do next?
"""

import streamlit as st
from datetime import datetime, timezone

from services.api_client import fetch_latest, fetch_history, fetch_forecast
from services.transformers import to_latest_room_state, enrich_rows, history_to_df
from services.explanations import score_trend
from services.story_engine import to_daily_story, outdoor_suitability
from services.rituals import get_ritual
from services.event_transformer import to_room_events
from services.api_client import fetch_events
from services.analysis import summary_sentence, readiness_why, recovery_why, strain_why

from components.section_header import section_label
from components.metric_cards import metric_hero_card, room_state_card, score_accent, score_band
from components.snapshot_table import snapshot_card_open, snapshot_card_close, sensor_row
from components.story_card import story_card
from components.event_timeline import event_timeline
from components.freshness_badge import parse_freshness, freshness_badge, source_state_from_age


def render() -> None:
    device_id     = st.session_state.get("device_id", "m5stack-duska-home")
    history_hours = st.session_state.get("history_hours", 24)
    fetched_at    = datetime.now(timezone.utc)

    raw = fetch_latest(device_id=device_id)

    with st.spinner("Loading…"):
        history_rows = fetch_history(device_id=device_id, hours=history_hours)
        df           = history_to_df(enrich_rows(history_rows))
        raw_events   = fetch_events(device_id=device_id, limit=5)

    lrs          = to_latest_room_state(raw, fetched_at) if raw else None
    events       = to_room_events(raw_events)
    ts_str, age_hint, ts_age_min = parse_freshness(raw, fetched_at)
    source_state = source_state_from_age(raw, ts_age_min)
    pill_html    = freshness_badge(source_state)

    # ── Page header ──────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">'
        f'<div style="display:flex;align-items:center;gap:14px;">'
        f'<span style="font-size:1.6rem;font-weight:800;color:#D8EEFF;letter-spacing:0.04em;">Room Rhythm</span>'
        f'<span style="font-size:0.78rem;color:#3A5A7A;">{device_id}</span>'
        f'<span style="font-size:0.78rem;color:#334455;">{ts_str}&nbsp;&nbsp;{age_hint}</span>'
        f'</div><div>{pill_html}</div></div>'
        f'<div style="height:1px;background:#111E2E;margin-bottom:12px;"></div>',
        unsafe_allow_html=True,
    )

    # ── Offline / stale state ─────────────────────────────────────────────────
    if lrs is None:
        _offline_card()
        return

    # ── Summary sentence (above the fold) ────────────────────────────────────
    sentence = summary_sentence(lrs)
    st.markdown(
        f'<div style="background:#060E18;border-left:3px solid #1A3A5A;'
        f'border-radius:0 8px 8px 0;padding:10px 16px;margin-bottom:16px;">'
        f'<span style="font-size:0.92rem;color:#AABCCC;font-style:italic;">{sentence}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    expl = lrs.get("explanations", {})

    # ── Trend arrows from history ─────────────────────────────────────────────
    r_arr, r_lbl, r_clr = score_trend(lrs.get("readiness_score"), df, "room_readiness")
    v_arr, v_lbl, v_clr = score_trend(lrs.get("recovery_score"),  df, "recovery_score")
    s_arr, s_lbl, s_clr = score_trend(lrs.get("air_strain_score"), df, "air_strain")

    # ── Hero scores (all four core concepts above the fold) ──────────────────
    section_label("Room Performance")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        v = lrs.get("readiness_score")
        metric_hero_card("Room Readiness", v,
            band_label=score_band(v, False) if v is not None else "",
            subtitle=readiness_why(lrs),
            accent_color=score_accent(v, False) if v is not None else "gray",
            trend_arrow=r_arr, trend_label=r_lbl, trend_color=r_clr)
    with c2:
        v = lrs.get("recovery_score")
        metric_hero_card("Recovery Score", v,
            band_label=score_band(v, False) if v is not None else "",
            subtitle=recovery_why(lrs),
            accent_color=score_accent(v, False) if v is not None else "gray",
            trend_arrow=v_arr, trend_label=v_lbl, trend_color=v_clr)
    with c3:
        v = lrs.get("air_strain_score")
        metric_hero_card("Air Strain", v,
            band_label=score_band(v, True) if v is not None else "",
            subtitle=strain_why(lrs),
            accent_color=score_accent(v, True) if v is not None else "gray",
            trend_arrow=s_arr, trend_label=s_lbl, trend_color=s_clr)
    with c4:
        room_state_card(lrs.get("room_state"))

    # ── Indoor snapshot | Outdoor context ────────────────────────────────────
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    section_label("Current Room Snapshot")
    indoor_col, outdoor_col = st.columns([5, 3])

    indoor  = lrs.get("indoor", {})
    outdoor = lrs.get("outdoor", {})
    sync    = lrs.get("sync", {})

    with indoor_col:
        temp     = indoor.get("temperature_c")
        humidity = indoor.get("humidity_pct")
        tvoc     = indoor.get("tvoc_ppb")
        eco2     = indoor.get("eco2_ppm")
        pressure = indoor.get("pressure_hpa")
        motion   = indoor.get("motion")
        tvoc_lbl = indoor.get("tvoc_label", "—")

        temp_color = "#3DFF8A" if temp is not None and 18 <= temp <= 26 else "#FF8844"
        hum_color  = "#66CCFF" if humidity is not None and 40 <= humidity <= 65 else "#FFAA00"
        tvoc_color = (
            "#3DFF8A" if tvoc is not None and tvoc < 100 else
            "#FFCC00" if tvoc is not None and tvoc < 150 else
            "#FF8844" if tvoc is not None and tvoc < 200 else "#FF4422"
        )

        snapshot_card_open("Indoor Environment")
        sensor_row("Temperature",        f"{temp:.1f}" if temp is not None else None,   "°C",  temp_color,
                   hint="ideal 18–26 °C")
        sensor_row("Humidity",           f"{humidity:.0f}" if humidity is not None else None, "%", hum_color,
                   hint="comfort 40–65%")
        sensor_row("Air Quality (TVOC)", f"{tvoc:.0f} ppb  ·  {tvoc_lbl}" if tvoc is not None else None, "", tvoc_color)
        sensor_row("eCO₂",               f"{eco2:.0f}" if eco2 is not None else None,   "ppm", "#FFCC99",
                   hint="elevated ≥ 1000" if eco2 is not None and eco2 >= 1000 else "")
        sensor_row("Pressure",           f"{pressure:.0f}" if pressure is not None else None, "hPa", "#667788")
        sensor_row("Motion",             "Detected" if motion else "None", "",
                   "#DDDD00" if motion else "#2A3A4A")
        snapshot_card_close()

    with outdoor_col:
        _outdoor_card(outdoor, outdoor_suitability(lrs))
        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        _sync_card(sync, ts_str, ts_age_min, fetched_at, indoor)

    # ── 3-day weather forecast ────────────────────────────────────────────────
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    section_label("Weather Forecast")
    fc = fetch_forecast()
    if fc:
        f1, f2, f3 = st.columns(3)
        with f1: _forecast_card("Today",     fc.get("today",     {}))
        with f2: _forecast_card("Tomorrow",  fc.get("tomorrow",  {}))
        with f3: _forecast_card("Day After", fc.get("day_after", {}))
        if fc.get("storm_warning"):
            st.markdown(
                '<div style="margin-top:8px;padding:8px 14px;background:#1A0808;'
                'border-left:3px solid #FF4422;border-radius:0 8px 8px 0;">'
                '<span style="font-size:0.82rem;color:#FF6644;font-weight:600;">'
                'Storm warning in the 3-day forecast — check conditions before going out.</span>'
                '</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
            'padding:14px;color:#334455;font-size:0.85rem;">Forecast unavailable.</div>',
            unsafe_allow_html=True,
        )

    # ── Daily story teaser ────────────────────────────────────────────────────
    if df is not None and not df.empty:
        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        hours_label = {6: "6 h", 12: "12 h", 24: "24 h", 72: "3 days", 168: "7 days"}.get(history_hours, f"{history_hours} h")
        ds = to_daily_story(df)
        if ds:
            section_label("Today's Story")
            story_card(ds["headline"], ds["bullets"][:2], window_label=f"last {hours_label}")

    # ── Recent events teaser ──────────────────────────────────────────────────
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    section_label("Recent Events")
    if events:
        event_timeline(events, max_items=5)
    else:
        st.markdown(
            '<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;'
            'padding:16px;color:#334455;font-size:0.85rem;">No recent events — device is quiet.</div>',
            unsafe_allow_html=True,
        )


# ── Sub-cards ────────────────────────────────────────────────────────────────

def _offline_card() -> None:
    st.markdown(
        '<div style="background:#1A0808;border:1px solid #4A1010;border-radius:12px;'
        'padding:32px;text-align:center;color:#FF8888;margin-top:16px;">'
        '<div style="font-size:1.3rem;font-weight:700;margin-bottom:8px;">Device Offline</div>'
        '<div style="font-size:0.88rem;color:#886666;line-height:1.6;">'
        'No data received from the device.<br>'
        'Check the device is powered on and connected to WiFi.<br>'
        'The backend URL may also be unreachable.'
        '</div></div>',
        unsafe_allow_html=True,
    )


def _weather_icon(desc: str) -> str:
    d = desc.lower()
    if "thunder" in d or "storm" in d: return "⛈"
    if "snow" in d or "sleet" in d:    return "❄️"
    if "drizzle" in d:                 return "🌦"
    if "rain" in d:                    return "🌧"
    if "mist" in d or "fog" in d or "haze" in d: return "🌫"
    if "overcast" in d or "cloud" in d: return "☁️"
    if "clear" in d or "sun" in d:     return "☀️"
    return "🌤"


def _outdoor_card(outdoor: dict, suitability: str) -> None:
    o_temp   = outdoor.get("temperature_c")
    o_hum    = outdoor.get("humidity_pct")
    o_desc   = (outdoor.get("weather_main") or "—").title()
    icon     = _weather_icon(o_desc)
    temp_str = f"{o_temp:.1f} °C" if o_temp is not None else "—"
    hum_str  = f"{o_hum:.0f} %" if o_hum is not None else "—"
    suit_color = (
        "#3DFF8A" if "good" in suitability.lower() or "suitable" in suitability.lower() else
        "#FF8844" if any(w in suitability.lower() for w in ("unfavourable", "cold", "heat")) else
        "#FFCC00"
    )
    st.markdown(
        f'<div style="background:#070C18;border:1px solid #0F1E2E;border-radius:12px;padding:18px;">'
        f'<div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.15em;text-transform:uppercase;'
        f'margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #0F1A28;">Outdoor Context</div>'
        f'<div style="display:flex;justify-content:space-between;padding:4px 0;">'
        f'<span style="color:#667788;font-size:0.8rem;">Conditions</span>'
        f'<span style="color:#AAAACC;font-weight:600;">{icon} {o_desc}</span></div>'
        f'<div style="display:flex;justify-content:space-between;padding:4px 0;">'
        f'<span style="color:#667788;font-size:0.8rem;">Temperature</span>'
        f'<span style="color:#88CCFF;font-weight:600;">{temp_str}</span></div>'
        f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
        f'border-bottom:1px solid #0F1A28;margin-bottom:10px;">'
        f'<span style="color:#667788;font-size:0.8rem;">Humidity</span>'
        f'<span style="color:#66AACC;font-weight:600;">{hum_str}</span></div>'
        f'<div style="padding:8px 12px;background:#0A1825;border-radius:8px;'
        f'border-left:3px solid {suit_color};">'
        f'<span style="font-size:0.8rem;color:{suit_color};">{suitability}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _sync_card(sync: dict, ts_str: str, ts_age_min, fetched_at: datetime, indoor: dict) -> None:
    snapshot_card_open("Freshness & Sync")
    sensor_row("Last reading", ts_str or "—",                                        "",    "#446688")
    sensor_row("Data age",     f"{ts_age_min} min" if ts_age_min is not None else "—", "", "#556677")
    sensor_row("Cloud sync",   sync.get("cloud_sync_state") or "—",                 "",    _sync_c(sync.get("cloud_sync_state")))
    sensor_row("Weather data", sync.get("weather_freshness") or "—",                "",    _fresh_c(sync.get("weather_freshness")))
    sensor_row("WiFi RSSI",    indoor.get("wifi_rssi"),                              "dBm", "#445566",
               hint=_rssi_hint(indoor.get("wifi_rssi")))
    snapshot_card_close()


def _forecast_card(label: str, day: dict) -> None:
    if not day:
        st.markdown(
            f'<div style="background:#070C18;border:1px solid #0F1E2E;border-radius:12px;'
            f'padding:16px;min-height:100px;display:flex;align-items:center;justify-content:center;">'
            f'<span style="color:#223344;font-size:0.8rem;">—</span></div>',
            unsafe_allow_html=True,
        )
        return
    temp_min  = day.get("temp_min")
    temp_max  = day.get("temp_max")
    desc      = (day.get("description") or "—").title()
    fc_icon   = _weather_icon(desc)
    rain_prob = day.get("rain_probability", 0)
    storm     = day.get("storm_warning", False)
    morning_r = day.get("morning_rain", False)
    temp_str  = (f"{temp_min:.0f}–{temp_max:.0f} °C"
                 if temp_min is not None and temp_max is not None else "—")
    if storm:
        flag_html = '<span style="color:#FF4422;font-size:0.72rem;font-weight:700;">Storm warning</span>'
    elif morning_r:
        flag_html = '<span style="color:#4488FF;font-size:0.72rem;">Morning rain</span>'
    elif rain_prob > 0.4:
        flag_html = f'<span style="color:#4488FF;font-size:0.72rem;">{int(rain_prob * 100)}% rain</span>'
    else:
        flag_html = '<span style="color:#1A3A2A;font-size:0.72rem;">Clear</span>'
    st.markdown(
        f'<div style="background:#070C18;border:1px solid #0F1E2E;border-radius:12px;padding:16px;">'
        f'<div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.15em;text-transform:uppercase;'
        f'margin-bottom:10px;">{label}</div>'
        f'<div style="font-size:1.4rem;margin-bottom:4px;">{fc_icon}</div>'
        f'<div style="font-size:1.2rem;font-weight:700;color:#AACCEE;margin-bottom:4px;">{temp_str}</div>'
        f'<div style="font-size:0.82rem;color:#667788;margin-bottom:8px;">{desc}</div>'
        f'<div>{flag_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _sync_c(s):
    return {"ok": "#3DFF8A", "failed": "#FF4422", "none": "#556677", "idle": "#556677"}.get(s or "", "#556677")

def _fresh_c(s):
    return {"fresh": "#3DFF8A", "stale": "#FF8844", "failed": "#FF4422"}.get(s or "", "#556677")

def _rssi_hint(rssi):
    if rssi is None: return ""
    if rssi >= -50:  return "excellent"
    if rssi >= -70:  return "good"
    if rssi >= -85:  return "fair"
    return "weak"
