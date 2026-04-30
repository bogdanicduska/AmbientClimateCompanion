import streamlit as st

# ---------------------------------------------------------------------------
# Color tokens — mirrors device palette
# ---------------------------------------------------------------------------
_STATE_COLORS = {
    "Fresh":          {"bg": "#071F10", "border": "#0F4020", "text": "#3DFF8A",  "desc": "Light, usable, and supportive"},
    "Calm":           {"bg": "#071220", "border": "#0E2848", "text": "#66CCFF",  "desc": "Balanced, stable, and quiet"},
    "Dry":            {"bg": "#1C1200", "border": "#3A2800", "text": "#FFD060",  "desc": "Humidity too low — comfort reduced"},
    "Heavy":          {"bg": "#1C0500", "border": "#4A1000", "text": "#FF6644",  "desc": "Air feels stale or burdened"},
    "Social":         {"bg": "#181500", "border": "#383000", "text": "#DDDD00",  "desc": "Room is active and in use"},
    "Sleep-Friendly": {"bg": "#060F1C", "border": "#0C1E38", "text": "#88BBFF",  "desc": "Suitable for rest and calm"},
    "Restless":       {"bg": "#1A0E00", "border": "#3A2000", "text": "#FF9944",  "desc": "Conditions are unbalanced"},
}


def _score_color(value: int, low_good: bool) -> str:
    if low_good:
        if value < 30:   return "#3DFF8A"
        if value < 60:   return "#FFAA00"
        return "#FF4422"
    if value >= 75:      return "#3DFF8A"
    if value >= 50:      return "#FFAA00"
    return "#FF4422"


def _score_label(value: int, low_good: bool) -> str:
    if low_good:
        if value < 30:   return "Fresh air"
        if value < 60:   return "Rising strain"
        return "Heavy"
    if value >= 75:      return "High"
    if value >= 50:      return "Moderate"
    return "Low"


# ---------------------------------------------------------------------------
# Hero metric card — full card with label, big number, bar, interpretation
# ---------------------------------------------------------------------------
def score_card(label: str, value: int | None, low_good: bool = False) -> None:
    if value is None:
        st.markdown(
            f"""<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;
                            padding:20px;height:120px;display:flex;flex-direction:column;
                            justify-content:center;">
                  <div style="font-size:0.7rem;color:#3A5A7A;letter-spacing:0.12em;
                              text-transform:uppercase;margin-bottom:8px;">{label}</div>
                  <div style="font-size:2.4rem;font-weight:700;color:#334455;">—</div>
                </div>""",
            unsafe_allow_html=True,
        )
        return

    color = _score_color(value, low_good)
    sublabel = _score_label(value, low_good)
    bar_pct = value

    st.markdown(
        f"""<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;
                        padding:20px;height:120px;box-sizing:border-box;">
              <div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.12em;
                          text-transform:uppercase;margin-bottom:6px;">{label}</div>
              <div style="font-size:2.4rem;font-weight:700;color:{color};line-height:1.1;">{value}</div>
              <div style="background:#111C2A;border-radius:3px;height:4px;margin:8px 0 6px;">
                <div style="width:{bar_pct}%;max-width:100%;background:{color};
                            height:4px;border-radius:3px;transition:width 0.3s;"></div>
              </div>
              <div style="font-size:0.75rem;color:#556677;">{sublabel}</div>
            </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Room State card
# ---------------------------------------------------------------------------
def room_state_card(state: str | None) -> None:
    if not state or state == "---":
        st.markdown(
            """<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;
                           padding:20px;height:120px;">
                 <div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.12em;
                             text-transform:uppercase;margin-bottom:10px;">Room State</div>
                 <div style="font-size:1.5rem;font-weight:700;color:#334455;">—</div>
               </div>""",
            unsafe_allow_html=True,
        )
        return

    c = _STATE_COLORS.get(state, {"bg": "#0A1220", "border": "#1A2A3A",
                                   "text": "#AAAAAA", "desc": ""})
    st.markdown(
        f"""<div style="background:{c['bg']};border:1px solid {c['border']};
                        border-radius:12px;padding:20px;height:120px;box-sizing:border-box;">
              <div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.12em;
                          text-transform:uppercase;margin-bottom:8px;">Room State</div>
              <div style="font-size:1.6rem;font-weight:700;color:{c['text']};
                          letter-spacing:0.06em;">{state}</div>
              <div style="font-size:0.75rem;color:#445566;margin-top:6px;">{c['desc']}</div>
            </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Sensor snapshot card — a full card container wrapping multiple rows
# ---------------------------------------------------------------------------
def snapshot_card_open(title: str) -> None:
    """Emit the opening div of a snapshot card. Must pair with snapshot_card_close()."""
    st.markdown(
        f"""<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;padding:20px;">
              <div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.15em;
                          text-transform:uppercase;margin-bottom:14px;
                          padding-bottom:6px;border-bottom:1px solid #142030;">
                {title}
              </div>""",
        unsafe_allow_html=True,
    )


def snapshot_card_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def sensor_row(label: str, value, unit: str = "", color: str = "#CCCCCC") -> None:
    display = f"{value}&nbsp;{unit}".strip() if value is not None else "—"
    st.markdown(
        f"""<div style="display:flex;justify-content:space-between;align-items:baseline;
                        padding:6px 0;border-bottom:1px solid #0F1A28;">
              <span style="color:#445566;font-size:0.8rem;">{label}</span>
              <span style="color:{color};font-weight:600;font-size:0.9rem;">{display}</span>
            </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Status pill — inline colored badge (LIVE / CACHE / OFFLINE etc.)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Event panel
# ---------------------------------------------------------------------------
_EVENT_META = {
    # (human label, severity color, border color)
    "wifi_connected":      ("WiFi connected",          "#3DFF8A", "#0A3D1F"),
    "wifi_disconnected":   ("WiFi lost",               "#FF8844", "#3A2000"),
    "wifi_failed":         ("WiFi failed",             "#FF4422", "#4A1000"),
    "room_online":         ("Device online",           "#3DFF8A", "#0A3D1F"),
    "room_state_restored": ("Recovered from cloud",    "#66CCFF", "#0E2848"),
    "room_synced":         ("Room synced",             "#3DFF8A", "#0A3D1F"),
    "room_sync_failed":    ("Sync failed",             "#FF4422", "#4A1000"),
    "cache_loaded":        ("Loaded from cache",       "#778899", "#1A2A3A"),
    "boot_recovered":      ("Boot recovered",          "#778899", "#1A2A3A"),
    "humidity_alert":      ("Low humidity",            "#FFD060", "#3A2800"),
    "air_quality_alert":   ("Poor air quality",        "#FF8844", "#3A2000"),
    "motion_triggered":    ("Motion detected",         "#DDDD00", "#383000"),
    "announcement_spoken": ("Announcement spoken",     "#778899", "#1A2A3A"),
    "speech_query_received": ("Voice query received",  "#66CCFF", "#0E2848"),
    "speech_summary_spoken": ("Room summary spoken",   "#66CCFF", "#0E2848"),
}

_SEVERITY_RANK = {
    "#FF4422": 0,   # error
    "#FF8844": 1,   # warning
    "#FFD060": 2,   # caution
    "#DDDD00": 3,   # activity
    "#3DFF8A": 4,   # ok
    "#66CCFF": 5,   # info
    "#778899": 6,   # neutral
}


def _rel_time(ts_str: str) -> str:
    """Return a human-relative time string like '3 min ago' or '2 h ago'."""
    from datetime import datetime, timezone
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        diff = int((datetime.now(timezone.utc) - ts).total_seconds())
        if diff < 60:        return "just now"
        if diff < 3600:      return f"{diff // 60} min ago"
        if diff < 86400:     return f"{diff // 3600} h ago"
        return f"{diff // 86400} d ago"
    except Exception:
        return ts_str[:16] if ts_str else "—"


def _fmt_details(details: str | None) -> str:
    if not details:
        return ""
    # details is stored as Python repr of a dict — try to make it readable
    try:
        import ast
        d = ast.literal_eval(details)
        if isinstance(d, dict):
            parts = []
            for k, v in d.items():
                if k in ("value", "label", "status", "ssid", "error"):
                    parts.append(str(v))
            return "  ·  " + "  ·  ".join(parts) if parts else ""
    except Exception:
        pass
    if len(details) < 60:
        return f"  ·  {details}"
    return ""


def event_panel(events: list[dict]) -> None:
    if not events:
        st.markdown(
            """<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;
                           padding:20px;color:#334455;text-align:center;font-size:0.85rem;">
                 No events recorded yet.
               </div>""",
            unsafe_allow_html=True,
        )
        return

    rows_html = ""
    for ev in events:
        et = ev.get("event_type", "")
        label, text_color, border_color = _EVENT_META.get(
            et, (et.replace("_", " ").title(), "#778899", "#1A2A3A")
        )
        rel = _rel_time(ev.get("timestamp") or "")
        detail_str = _fmt_details(ev.get("details"))
        rows_html += f"""
        <div style="display:flex;align-items:baseline;gap:12px;padding:7px 0;
                    border-bottom:1px solid #0F1A28;border-left:2px solid {border_color};
                    padding-left:10px;">
          <span style="color:#334455;font-size:0.75rem;white-space:nowrap;min-width:76px;">
            {rel}
          </span>
          <span style="color:{text_color};font-size:0.82rem;font-weight:600;">{label}</span>
          <span style="color:#445566;font-size:0.78rem;">{detail_str}</span>
        </div>"""

    st.markdown(
        f"""<div style="background:#0A1220;border:1px solid #1A2A3A;border-radius:12px;
                        padding:20px;">
              <div style="font-size:0.68rem;color:#3A5A7A;letter-spacing:0.15em;
                          text-transform:uppercase;margin-bottom:12px;
                          padding-bottom:6px;border-bottom:1px solid #142030;">
                Room Events
              </div>
              {rows_html}
            </div>""",
        unsafe_allow_html=True,
    )


def status_pill(text: str, color: str) -> str:
    return (
        f'<span style="background:{color}22;color:{color};border:1px solid {color}55;'
        f'border-radius:4px;padding:2px 10px;font-size:0.75rem;font-weight:700;'
        f'letter-spacing:0.08em;">{text}</span>'
    )
