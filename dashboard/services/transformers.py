"""
Data transformation: room metric computation, contract builders,
and history DataFrame parsing.

IMPORTANT — SOURCE OF TRUTH
The functions compute_air_strain / compute_recovery / compute_readiness /
compute_room_state below are LOCAL FALLBACK formulas only.
They are kept in sync with backend/app/services/room_metrics_service.py.
The dashboard PREFERS backend-computed scores (readiness_score /
recovery_score / air_strain_score) when the API returns them — see enrich().
Fallback computation only fires when those fields are absent (e.g. legacy data).
"""

from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd

from .contracts import (
    LatestRoomState, IndoorData, OutdoorData, SyncInfo, Explanations,
    HistorySeries, HistoryPoint, SourceState,
)


# ---------------------------------------------------------------------------
# Room metric computation
# ---------------------------------------------------------------------------

def compute_air_strain(temp, humidity, aq, eco2) -> int:
    aq    = aq    or 0.0
    eco2  = eco2  or 400.0
    aq_f  = min(100.0, aq / 2.0)
    eco2_f = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    temp_f = min(100.0, max(0.0, (temp - 22.0) * 5.0)) if temp > 22.0 else 0.0
    return int(aq_f * 0.50 + eco2_f * 0.35 + temp_f * 0.15)


def compute_recovery(temp, humidity, aq, eco2) -> int:
    aq   = aq   or 0.0
    eco2 = eco2 or 400.0
    temp_s = max(0.0, 100.0 - abs(temp - 20.0) * 10.0)
    hum_s  = max(0.0, 100.0 - abs(humidity - 52.0) * 3.0)
    aq_pen   = min(100.0, aq / 2.0)
    eco2_pen = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    air_s = max(0.0, 100.0 - (aq_pen * 0.60 + eco2_pen * 0.40))
    return int(temp_s * 0.35 + hum_s * 0.30 + air_s * 0.35)


def compute_readiness(temp, humidity, aq, eco2) -> int:
    aq   = aq   or 0.0
    eco2 = eco2 or 400.0
    temp_s = max(0.0, 100.0 - abs(temp - 21.0) * 8.0)
    hum_s  = max(0.0, 100.0 - abs(humidity - 50.0) * 2.5)
    aq_pen   = min(100.0, aq / 2.0)
    eco2_pen = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    air_s = max(0.0, 100.0 - (aq_pen * 0.60 + eco2_pen * 0.40))
    return int(temp_s * 0.40 + hum_s * 0.25 + air_s * 0.35)


def compute_room_state(readiness, recovery, strain, humidity, motion: bool = False) -> str:
    # Mirrors backend compute_room_state — keep in sync with room_metrics_service.py
    if humidity < 40:
        return "Dry"
    if strain >= 65:
        return "Heavy"
    if motion:
        return "Social"
    if strain < 25 and 40 <= humidity <= 70:
        return "Fresh"
    if recovery >= 70:
        return "Sleep-Friendly"
    if recovery >= 55:
        return "Calm"
    if strain >= 45:
        return "Restless"
    return "Calm"


def _tvoc_label(tvoc: float) -> str:
    if tvoc < 50:   return "Good"
    if tvoc < 100:  return "Moderate"
    if tvoc < 200:  return "Poor"
    return "Hazardous"


def _derive_source_state(row: dict, ts_age_min: int | None) -> SourceState:
    """Derive source_state from age and sync_status field."""
    sync = (row.get("sync_status") or "").lower()
    if sync == "cache":
        return "cache"
    if ts_age_min is None:
        return "stale"
    if ts_age_min < 10:
        return "live"
    if ts_age_min < 30:
        return "cloud"
    return "stale"


# ---------------------------------------------------------------------------
# Enrich a raw API row (adds computed metrics)
# ---------------------------------------------------------------------------

def enrich(row: dict) -> dict:
    """
    Add computed room metrics to a raw API row.
    Prefers backend-provided scores (spec names: readiness_score / recovery_score /
    air_strain_score) when present; falls back to local computation otherwise.
    """
    if "readiness_score" in row and "recovery_score" in row and "air_strain_score" in row:
        # Backend already enriched — add internal aliases for chart column mapping
        return {
            **row,
            "room_readiness": row["readiness_score"],
            "air_strain":     row["air_strain_score"],
        }

    temp     = row.get("indoor_temp")     or 20.0
    humidity = row.get("indoor_humidity") or 50.0
    aq       = row.get("air_quality")     or 0.0
    eco2     = row.get("indoor_eco2")     or 400.0

    motion    = bool(row.get("motion", False))
    readiness = compute_readiness(temp, humidity, aq, eco2)
    recovery  = compute_recovery(temp, humidity, aq, eco2)
    strain    = compute_air_strain(temp, humidity, aq, eco2)
    state     = compute_room_state(readiness, recovery, strain, humidity, motion)

    return {
        **row,
        # spec-aligned names
        "readiness_score":  readiness,
        "recovery_score":   recovery,
        "air_strain_score": strain,
        "room_state":       state,
        # internal aliases
        "room_readiness": readiness,
        "air_strain":     strain,
    }


def enrich_rows(rows: list[dict]) -> list[dict]:
    return [enrich(r) for r in rows]


# ---------------------------------------------------------------------------
# 3.1  Build LatestRoomState contract
# ---------------------------------------------------------------------------

def to_latest_room_state(raw: dict, fetched_at: datetime) -> LatestRoomState:
    """
    Transform raw API response + computed metrics into a normalized LatestRoomState.
    fetched_at must be timezone-aware (UTC).
    """
    from .explanations import build_explanations

    enriched = enrich(raw)

    ts_age_min: int | None = None
    ts_iso = enriched.get("timestamp")
    if ts_iso:
        try:
            ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
            ts_age_min = int((fetched_at - ts).total_seconds() / 60)
        except Exception:
            pass

    source_state = _derive_source_state(enriched, ts_age_min)
    expl_raw     = build_explanations(enriched)

    indoor: IndoorData = {}
    if enriched.get("indoor_temp")     is not None: indoor["temperature_c"]  = enriched["indoor_temp"]
    if enriched.get("indoor_humidity") is not None: indoor["humidity_pct"]   = enriched["indoor_humidity"]
    if enriched.get("air_quality")     is not None:
        indoor["tvoc_ppb"]   = enriched["air_quality"]
        indoor["tvoc_label"] = enriched.get("air_quality_label") or _tvoc_label(enriched["air_quality"])
    if enriched.get("indoor_eco2")     is not None: indoor["eco2_ppm"]       = enriched["indoor_eco2"]
    if enriched.get("indoor_pressure") is not None: indoor["pressure_hpa"]   = enriched["indoor_pressure"]
    if enriched.get("motion")          is not None: indoor["motion"]         = bool(enriched["motion"])
    if enriched.get("wifi_rssi")       is not None: indoor["wifi_rssi"]      = enriched["wifi_rssi"]

    outdoor: OutdoorData = {}
    if enriched.get("outdoor_temp")        is not None: outdoor["temperature_c"]       = enriched["outdoor_temp"]
    if enriched.get("outdoor_humidity")    is not None: outdoor["humidity_pct"]        = enriched["outdoor_humidity"]
    if enriched.get("outdoor_weather")     is not None: outdoor["weather_main"]        = enriched["outdoor_weather"]
    if enriched.get("outdoor_description") is not None: outdoor["weather_description"] = enriched["outdoor_description"]
    if enriched.get("outdoor_icon")        is not None: outdoor["icon_code"]           = enriched["outdoor_icon"]
    outdoor["summary"] = "Live" if source_state == "live" else "Cached"

    sync: SyncInfo = {
        "fetched_at":        fetched_at.isoformat(),
        "weather_freshness": "fresh" if source_state in ("live", "cloud") else "stale",
        "telemetry_state":   "ok"    if source_state in ("live", "cloud") else "idle",
        "cloud_sync_state":  "ok"    if source_state in ("live", "cloud") else "none",
    }
    if ts_iso:
        sync["last_reading_at"] = ts_iso

    explanations: Explanations = {
        "readiness":           expl_raw["readiness"],
        "recovery":            expl_raw["recovery"],
        "air_strain":          expl_raw["air_strain"],
        "room_state_subtitle": expl_raw["room_state_subtitle"],
    }

    lrs: LatestRoomState = {
        "device_id":        enriched.get("device_id", ""),
        "timestamp":        ts_iso or "",
        "source_state":     source_state,
        "data_age_minutes": ts_age_min,
        "readiness_score":  enriched["room_readiness"],
        "recovery_score":   enriched["recovery_score"],
        "air_strain_score": enriched["air_strain"],
        "room_state":       enriched["room_state"],
        "indoor":           indoor,
        "outdoor":          outdoor,
        "sync":             sync,
        "explanations":     explanations,
    }
    return lrs


# ---------------------------------------------------------------------------
# 3.2  Build HistorySeries contract
# ---------------------------------------------------------------------------

def to_history_series(rows: list[dict], device_id: str, window_hours: int) -> HistorySeries:
    """
    Transform raw history rows into a normalized HistorySeries contract.
    Each point is independently enriched with computed room metrics.
    """
    points: list[HistoryPoint] = []
    for row in rows:
        e = enrich(row)
        pt: HistoryPoint = {
            "readiness_score":  e["room_readiness"],
            "recovery_score":   e["recovery_score"],
            "air_strain_score": e["air_strain"],
            "room_state":       e["room_state"],
        }
        if e.get("timestamp"):                  pt["timestamp"]             = e["timestamp"]
        if e.get("indoor_temp")     is not None: pt["temperature_c"]         = e["indoor_temp"]
        if e.get("indoor_humidity") is not None: pt["humidity_pct"]          = e["indoor_humidity"]
        if e.get("air_quality")     is not None: pt["tvoc_ppb"]              = e["air_quality"]
        if e.get("indoor_eco2")     is not None: pt["eco2_ppm"]              = e["indoor_eco2"]
        if e.get("indoor_pressure") is not None: pt["pressure_hpa"]          = e["indoor_pressure"]
        if e.get("motion")          is not None: pt["motion"]                = bool(e["motion"])
        if e.get("outdoor_temp")    is not None: pt["outdoor_temperature_c"] = e["outdoor_temp"]
        if e.get("outdoor_weather") is not None: pt["outdoor_weather"]       = e["outdoor_weather"]
        points.append(pt)

    return {"device_id": device_id, "window_hours": window_hours, "points": points}


# ---------------------------------------------------------------------------
# History DataFrame (for charts — uses HistorySeries or raw enriched rows)
# ---------------------------------------------------------------------------

def history_to_df(rows: list[dict]) -> pd.DataFrame | None:
    """Build a chart-ready DataFrame from raw enriched rows."""
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if "timestamp" not in df.columns or df.empty:
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    return df if not df.empty else None


def series_to_df(series: HistorySeries) -> pd.DataFrame | None:
    """Build a chart-ready DataFrame from a HistorySeries contract."""
    points = series.get("points", [])
    if not points:
        return None
    df = pd.DataFrame(points)
    if "timestamp" not in df.columns or df.empty:
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    # align column names to chart expectations
    renames = {
        "temperature_c":  "indoor_temp",
        "humidity_pct":   "indoor_humidity",
        "tvoc_ppb":       "air_quality",
        "eco2_ppm":       "indoor_eco2",
        "pressure_hpa":   "indoor_pressure",
        "readiness_score": "room_readiness",
        "air_strain_score": "air_strain",
    }
    df.rename(columns=renames, inplace=True)
    return df if not df.empty else None
