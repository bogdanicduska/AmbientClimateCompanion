"""
Shared state metadata used by services and components.
Single source of truth for state colors, subtitles, and severity maps.
"""

from __future__ import annotations
from .contracts import AccentColor

_STATE_META: dict[str, dict] = {
    "Fresh":          {"bg": "#071F10", "border": "#0F4020", "text": "#3DFF8A",  "accent": "green",  "subtitle": "Light, usable, and supportive"},
    "Calm":           {"bg": "#071220", "border": "#0E2848", "text": "#66CCFF",  "accent": "blue",   "subtitle": "Balanced, stable, and quiet"},
    "Dry":            {"bg": "#1C1200", "border": "#3A2800", "text": "#FFD060",  "accent": "amber",  "subtitle": "Humidity too low — comfort reduced"},
    "Heavy":          {"bg": "#1C0500", "border": "#4A1000", "text": "#FF6644",  "accent": "red",    "subtitle": "Air feels stale or burdened"},
    "Social":         {"bg": "#181500", "border": "#383000", "text": "#DDDD00",  "accent": "amber",  "subtitle": "Room is active and in use"},
    "Sleep-Friendly": {"bg": "#060F1C", "border": "#0C1E38", "text": "#88BBFF",  "accent": "blue",   "subtitle": "Suitable for rest and calm"},
    "Restless":       {"bg": "#1A0E00", "border": "#3A2000", "text": "#FF9944",  "accent": "amber",  "subtitle": "Conditions are unbalanced"},
}

_FALLBACK = {"bg": "#0A1220", "border": "#1A2A3A", "text": "#AAAAAA", "accent": "gray", "subtitle": ""}


def state_meta(state: str) -> dict:
    return _STATE_META.get(state, _FALLBACK)


def state_subtitle(state: str) -> str:
    return _STATE_META.get(state, _FALLBACK)["subtitle"]


def state_accent(state: str) -> AccentColor:
    return _STATE_META.get(state, _FALLBACK)["accent"]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Accent color → hex
# ---------------------------------------------------------------------------
ACCENT_HEX: dict[str, str] = {
    "green": "#3DFF8A",
    "amber": "#FFCC00",
    "red":   "#FF4422",
    "blue":  "#66CCFF",
    "gray":  "#778899",
}


def accent_hex(color: str) -> str:
    return ACCENT_HEX.get(color, "#AAAAAA")


# ---------------------------------------------------------------------------
# Event severity → color
# ---------------------------------------------------------------------------
SEVERITY_COLOR: dict[str, str] = {
    "critical": "#FF4422",
    "warning":  "#FF8844",
    "info":     "#66CCFF",
}


# ---------------------------------------------------------------------------
# Event type → (title, severity, border_color)
# ---------------------------------------------------------------------------
_EVENT_META: dict[str, tuple[str, str, str]] = {
    "wifi_connected":        ("WiFi connected",        "info",     "#0A3D1F"),
    "wifi_disconnected":     ("WiFi lost",             "warning",  "#3A2000"),
    "wifi_failed":           ("WiFi failed",           "critical", "#4A1000"),
    "room_online":           ("Device online",         "info",     "#0A3D1F"),
    "room_state_restored":   ("Recovered from cloud",  "info",     "#0E2848"),
    "room_synced":           ("Room synced",           "info",     "#0A3D1F"),
    "room_sync_failed":      ("Sync failed",           "critical", "#4A1000"),
    "cache_loaded":          ("Loaded from cache",     "info",     "#1A2A3A"),
    "boot_recovered":        ("Boot recovered",        "info",     "#1A2A3A"),
    "humidity_alert":        ("Low humidity",          "warning",  "#3A2800"),
    "air_quality_alert":     ("Poor air quality",      "warning",  "#3A2000"),
    "motion_triggered":      ("Motion detected",       "info",     "#383000"),
    "announcement_spoken":   ("Announcement spoken",   "info",     "#1A2A3A"),
    "speech_query_received": ("Voice query received",  "info",     "#0E2848"),
    "speech_summary_spoken": ("Room summary spoken",   "info",     "#0E2848"),
    "poor_air":              ("Poor air detected",     "warning",  "#3A2000"),
    "high_strain":           ("High air strain",       "warning",  "#3A2000"),
    "low_humidity":          ("Low humidity",          "warning",  "#3A2800"),
    "room_heavy":            ("Heavy room state",      "critical", "#4A1000"),
}


def event_meta(event_type: str) -> tuple[str, str, str]:
    """Return (title, severity, border_color) for an event type."""
    return _EVENT_META.get(
        event_type,
        (event_type.replace("_", " ").title(), "info", "#1A2A3A"),
    )
