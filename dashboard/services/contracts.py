"""
Normalized frontend data contracts.

All TypedDicts are total=False where fields may be absent (sparse API data).
Pages and components should always use these types — never raw API dicts.
"""

from __future__ import annotations
from typing import Literal, TypedDict


# ---------------------------------------------------------------------------
# Scalar type aliases
# ---------------------------------------------------------------------------
SourceState  = Literal["live", "cloud", "cache", "stale", "offline"]
RoomStateStr = Literal["Fresh", "Calm", "Dry", "Heavy", "Social", "Sleep-Friendly", "Restless"]
Severity     = Literal["info", "warning", "critical"]
Priority     = Literal["high", "medium", "low"]
AccentColor  = Literal["green", "amber", "red", "blue", "gray"]


# ---------------------------------------------------------------------------
# 3.1  LatestRoomState
# ---------------------------------------------------------------------------

class IndoorData(TypedDict, total=False):
    temperature_c:  float
    humidity_pct:   float
    tvoc_ppb:       float
    tvoc_label:     str          # Good | Moderate | Poor | Hazardous
    eco2_ppm:       float
    pressure_hpa:   float
    motion:         bool
    wifi_rssi:      int


class OutdoorData(TypedDict, total=False):
    temperature_c:       float
    humidity_pct:        float
    weather_main:        str
    weather_description: str
    icon_code:           str
    summary:             str


class SyncInfo(TypedDict, total=False):
    last_reading_at:    str   # ISO-8601
    fetched_at:         str   # ISO-8601
    weather_freshness:  Literal["fresh", "stale", "failed"]
    telemetry_state:    Literal["ok", "failed", "idle"]
    cloud_sync_state:   Literal["ok", "failed", "none"]


class Explanations(TypedDict, total=False):
    readiness:          list[str]
    recovery:           list[str]
    air_strain:         list[str]
    room_state_subtitle: str


class LatestRoomState(TypedDict, total=False):
    device_id:        str
    timestamp:        str          # ISO-8601
    source_state:     SourceState
    data_age_minutes: int | None

    readiness_score:  int
    recovery_score:   int
    air_strain_score: int
    room_state:       RoomStateStr

    indoor:           IndoorData
    outdoor:          OutdoorData
    sync:             SyncInfo
    explanations:     Explanations


# ---------------------------------------------------------------------------
# 3.2  HistorySeries
# ---------------------------------------------------------------------------

class HistoryPoint(TypedDict, total=False):
    timestamp:            str   # ISO-8601
    readiness_score:      int
    recovery_score:       int
    air_strain_score:     int
    room_state:           RoomStateStr

    temperature_c:        float
    humidity_pct:         float
    tvoc_ppb:             float
    eco2_ppm:             float
    pressure_hpa:         float
    motion:               bool

    outdoor_temperature_c: float
    outdoor_weather:       str


class HistorySeries(TypedDict):
    device_id:    str
    window_hours: int
    points:       list[HistoryPoint]


# ---------------------------------------------------------------------------
# 3.3  RoomEvent
# ---------------------------------------------------------------------------

class RoomEvent(TypedDict, total=False):
    event_id:   str
    timestamp:  str          # ISO-8601
    event_type: str
    severity:   Severity
    title:      str
    message:    str
    metadata:   dict


# ---------------------------------------------------------------------------
# 3.4  RitualRecommendation
# ---------------------------------------------------------------------------

class RitualRecommendation(TypedDict, total=False):
    ritual_id:        str
    title:            str
    subtitle:         str
    state:            RoomStateStr | str
    reason_lines:     list[str]
    next_step:        str
    expected_benefit: str
    icon:             str
    priority:         Priority


# ---------------------------------------------------------------------------
# 3.5  DailyRoomStory
# ---------------------------------------------------------------------------

class DailyRoomStory(TypedDict):
    date:         str    # YYYY-MM-DD
    headline:     str
    bullets:      list[str]
    summary_type: Literal["daily_story"]
