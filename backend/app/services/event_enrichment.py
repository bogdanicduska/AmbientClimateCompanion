"""
Event enrichment — adds severity, title, and message to raw device_events rows.
Maps event_type to semantic fields required by the 6.3 contract.
"""

from __future__ import annotations
import ast

# (title, severity, message_template)
# message_template keys must match metadata fields extracted from 'details'
_EVENT_META: dict[str, tuple[str, str, str]] = {
    "wifi_connected":        ("WiFi connected",          "info",     "Connected to {ssid}."),
    "wifi_disconnected":     ("WiFi lost",               "warning",  "WiFi connection lost."),
    "wifi_failed":           ("WiFi failed",             "critical", "WiFi connection failed: {error}."),
    "room_online":           ("Device online",           "info",     "Device came online and is ready."),
    "room_state_restored":   ("State recovered",         "info",     "Room state recovered from cloud backup."),
    "room_synced":           ("Room synced",             "info",     "Room state synced to cloud successfully."),
    "room_sync_failed":      ("Sync failed",             "critical", "Cloud sync failed: {error}."),
    "cache_loaded":          ("Cache loaded",            "info",     "Device loaded state from local cache."),
    "boot_recovered":        ("Boot recovered",          "info",     "Device recovered after an unexpected restart."),
    "humidity_alert":        ("Low humidity",            "warning",  "Humidity at {value}% — below comfort range."),
    "air_quality_alert":     ("Poor air quality",        "warning",  "Air quality {label} — TVOC elevated."),
    "motion_triggered":      ("Motion detected",         "info",     "Motion detected in the room."),
    "announcement_spoken":   ("Announcement spoken",     "info",     "Device announced room state update."),
    "speech_query_received": ("Voice query received",    "info",     "Device received a voice query."),
    "speech_summary_spoken": ("Room summary spoken",     "info",     "Device spoke the current room summary."),
}


def enrich_event(raw: dict) -> dict:
    """
    Add severity, title, message to a raw device_events row.
    Preserves all existing fields.
    """
    et    = raw.get("event_type", "")
    title, severity, tmpl = _EVENT_META.get(
        et,
        (et.replace("_", " ").title(), "info", ""),
    )

    metadata = _parse_details(raw.get("details"))
    message  = _render_message(tmpl, metadata)

    return {
        **raw,
        "severity": severity,
        "title":    title,
        "message":  message,
        "metadata": metadata,
    }


def enrich_events(rows: list[dict]) -> list[dict]:
    return [enrich_event(r) for r in rows]


def _parse_details(details) -> dict:
    if not details:
        return {}
    try:
        parsed = ast.literal_eval(str(details))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {"raw": str(details)} if details else {}


def _render_message(template: str, metadata: dict) -> str:
    if not template:
        return ""
    try:
        keys = {k: metadata.get(k, "?") for k in ("ssid", "error", "value", "label", "status")}
        return template.format(**keys)
    except Exception:
        return template
