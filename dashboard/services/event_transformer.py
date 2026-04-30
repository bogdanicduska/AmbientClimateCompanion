"""
Transform raw API events into normalized RoomEvent contracts.
"""

from __future__ import annotations
import ast
import hashlib

from .contracts import RoomEvent
from .state_meta import event_meta


def to_room_event(raw: dict) -> RoomEvent:
    """Map a raw API event dict to a RoomEvent contract."""
    et    = raw.get("event_type", "")
    ts    = raw.get("timestamp", "")
    title, severity, _ = event_meta(et)

    # Build a stable event_id from type + timestamp
    event_id = hashlib.md5(f"{et}:{ts}".encode()).hexdigest()[:12]

    # Parse details into metadata dict
    metadata: dict = {}
    raw_details = raw.get("details")
    if raw_details:
        try:
            parsed = ast.literal_eval(str(raw_details))
            if isinstance(parsed, dict):
                metadata = parsed
        except Exception:
            metadata = {"details": str(raw_details)}

    # Build a human message from metadata
    message = _build_message(et, metadata)

    event: RoomEvent = {
        "event_id":   event_id,
        "timestamp":  ts,
        "event_type": et,
        "severity":   severity,  # type: ignore[typeddict-item]
        "title":      title,
        "message":    message,
        "metadata":   metadata,
    }
    return event


def to_room_events(raw_list: list[dict]) -> list[RoomEvent]:
    return [to_room_event(r) for r in raw_list]


def _build_message(event_type: str, metadata: dict) -> str:
    templates = {
        "wifi_connected":      "Connected to {ssid}.",
        "wifi_disconnected":   "WiFi connection lost.",
        "wifi_failed":         "WiFi connection failed: {error}.",
        "room_online":         "Device came online.",
        "room_synced":         "Room state synced to cloud.",
        "room_sync_failed":    "Sync failed: {error}.",
        "humidity_alert":      "Humidity at {value}% — below comfort range.",
        "air_quality_alert":   "Air quality {label} — TVOC elevated.",
        "motion_triggered":    "Motion detected in room.",
        "poor_air":            "Air strain exceeded 60 due to elevated TVOC.",
        "room_heavy":          "Heavy room state — air quality degraded.",
    }
    tmpl = templates.get(event_type, "")
    if not tmpl:
        return ""
    try:
        return tmpl.format(**{k: metadata.get(k, "?") for k in ("ssid", "error", "value", "label")})
    except Exception:
        return tmpl
