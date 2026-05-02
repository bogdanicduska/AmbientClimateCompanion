"""
Analysis helpers — summary sentences, pattern cards, notable moments.
All pure functions. No Streamlit calls.
"""

from __future__ import annotations
import pandas as pd


# ---------------------------------------------------------------------------
# Summary sentence (Home page hero copy)
# ---------------------------------------------------------------------------

def summary_sentence(lrs: dict) -> str:
    """
    Single sentence answering "What is happening now and why does it matter?"
    Examples from spec:
      "Your room is fresh and focus-friendly right now."
      "Recovery is limited by warmth, despite clean air."
      "Heavy air is reducing room quality."
    """
    state     = lrs.get("room_state", "")
    readiness = lrs.get("readiness_score")
    recovery  = lrs.get("recovery_score")
    strain    = lrs.get("air_strain_score")
    indoor    = lrs.get("indoor", {})
    temp      = indoor.get("temperature_c")
    humidity  = indoor.get("humidity_pct")
    tvoc      = indoor.get("tvoc_ppb")

    source = lrs.get("source_state", "")
    if source == "offline":
        return "Device is offline — last known state is shown."
    if source == "stale":
        return "Data is stale — room state may have changed since the last reading."

    if state == "Heavy" or (strain is not None and strain >= 65):
        return "Heavy air is reducing room quality — ventilation would help now."

    if state == "Dry" or (humidity is not None and humidity < 40):
        return "Dry air is reducing comfort — hydration and humidifying recommended."

    if readiness is not None and readiness >= 75 and state in ("Fresh", "Calm"):
        if tvoc is not None and tvoc < 50:
            return "Your room is fresh and focus-friendly right now."
        return "Good conditions — room is ready for work or rest."

    if state == "Sleep-Friendly":
        return "Your room is calm and conditions support rest tonight."

    if recovery is not None and recovery < 50:
        if temp is not None and temp > 24:
            return "Recovery is limited by warmth, despite clean air."
        if strain is not None and strain >= 45:
            return "Elevated air strain is limiting recovery right now."
        return "Recovery conditions are below ideal at the moment."

    if strain is not None and strain >= 45:
        return "Air strain is rising — consider ventilating the room."

    if state == "Restless":
        return "Room conditions are unbalanced — a brief reset may help."

    if readiness is not None and readiness >= 60:
        return "Room conditions are moderate and usable right now."

    return "Room is being monitored — conditions are within normal range."


# ---------------------------------------------------------------------------
# Why-this-score copy (one sentence per metric)
# ---------------------------------------------------------------------------

def readiness_why(lrs: dict) -> str:
    v = lrs.get("readiness_score")
    if v is None:
        return ""
    expl = lrs.get("explanations", {}).get("readiness", [])
    if not expl:
        return ""
    joined = ", ".join(expl[:2])
    if v >= 75:
        return f"High readiness driven by {joined}."
    if v >= 50:
        return f"Moderate readiness — {joined}."
    return f"Low readiness due to {joined}."


def recovery_why(lrs: dict) -> str:
    v = lrs.get("recovery_score")
    if v is None:
        return ""
    expl = lrs.get("explanations", {}).get("recovery", [])
    if not expl:
        return ""
    joined = ", ".join(expl[:2])
    if v >= 70:
        return f"Strong recovery — {joined}."
    return f"Recovery limited by {joined}."


def strain_why(lrs: dict) -> str:
    v = lrs.get("air_strain_score")
    if v is None:
        return ""
    expl = lrs.get("explanations", {}).get("air_strain", [])
    if not expl:
        return ""
    joined = ", ".join(expl[:2])
    if v < 30:
        return f"Low strain — {joined}."
    if v < 60:
        return f"Moderate strain — {joined}."
    return f"High strain — {joined}."


# ---------------------------------------------------------------------------
# Pattern summary cards (Rhythm page)
# ---------------------------------------------------------------------------

def get_pattern_summary(df: pd.DataFrame) -> list[dict]:
    """
    Return 3–4 cards describing peak/notable moments in the history window.
    Each card: {label, value, time, hint, color}
    """
    cards: list[dict] = []

    if "recovery_score" in df.columns and not df["recovery_score"].isna().all():
        best_idx = df["recovery_score"].idxmax()
        row      = df.loc[best_idx]
        cards.append({
            "label": "Best Recovery",
            "value": str(int(row["recovery_score"])),
            "time":  _fmt_time(row),
            "hint":  "highest recovery score in window",
            "color": "#66CCFF",
        })

    if "air_strain" in df.columns and not df["air_strain"].isna().all():
        peak_idx = df["air_strain"].idxmax()
        row      = df.loc[peak_idx]
        cards.append({
            "label": "Highest Strain",
            "value": str(int(row["air_strain"])),
            "time":  _fmt_time(row),
            "hint":  "peak air strain in window",
            "color": "#FF8844" if row["air_strain"] >= 60 else "#FFCC00",
        })

    if "room_readiness" in df.columns and not df["room_readiness"].isna().all():
        best_idx = df["room_readiness"].idxmax()
        row      = df.loc[best_idx]
        cards.append({
            "label": "Peak Readiness",
            "value": str(int(row["room_readiness"])),
            "time":  _fmt_time(row),
            "hint":  "highest readiness score in window",
            "color": "#3DFF8A",
        })

    if "indoor_humidity" in df.columns and not df["indoor_humidity"].isna().all():
        min_val  = df["indoor_humidity"].min()
        min_idx  = df["indoor_humidity"].idxmin()
        row      = df.loc[min_idx]
        cards.append({
            "label": "Humidity Low",
            "value": f"{min_val:.0f}%",
            "time":  _fmt_time(row),
            "hint":  "driest point in window",
            "color": "#FFD060" if min_val < 40 else "#66CCFF",
        })

    return cards


# ---------------------------------------------------------------------------
# Notable moments cards (Memory page)
# ---------------------------------------------------------------------------

def get_notable_moments(df: pd.DataFrame) -> list[dict]:
    """
    Return 4 cards highlighting key moments in the history window.
    Each card: {title, subtitle, value, time, color, icon}
    """
    moments: list[dict] = []

    # Freshest moment — lowest strain + highest readiness combined
    if "air_strain" in df.columns and "room_readiness" in df.columns:
        df = df.copy()
        df["_freshness"] = df["room_readiness"] - df["air_strain"]
        best_idx = df["_freshness"].idxmax()
        row      = df.loc[best_idx]
        moments.append({
            "title":    "Freshest Moment",
            "subtitle": "Lowest strain, highest readiness",
            "value":    f"Readiness {int(row['room_readiness'])}  ·  Strain {int(row['air_strain'])}",
            "time":     _fmt_time(row),
            "color":    "#3DFF8A",
            "icon":     "◆",
        })

    # Highest strain
    if "air_strain" in df.columns and not df["air_strain"].isna().all():
        peak_idx = df["air_strain"].idxmax()
        row      = df.loc[peak_idx]
        moments.append({
            "title":    "Highest Strain",
            "subtitle": "Air quality was most degraded",
            "value":    f"Air Strain {int(row['air_strain'])}",
            "time":     _fmt_time(row),
            "color":    "#FF8844",
            "icon":     "◈",
        })

    # Best recovery
    if "recovery_score" in df.columns and not df["recovery_score"].isna().all():
        best_idx = df["recovery_score"].idxmax()
        row      = df.loc[best_idx]
        moments.append({
            "title":    "Best Recovery",
            "subtitle": "Conditions most suited for rest",
            "value":    f"Recovery {int(row['recovery_score'])}",
            "time":     _fmt_time(row),
            "color":    "#66CCFF",
            "icon":     "◉",
        })

    # Dryness alert window
    if "indoor_humidity" in df.columns:
        dry = df[df["indoor_humidity"] < 40]
        if not dry.empty:
            first_dry = dry.iloc[0]
            last_dry  = dry.iloc[-1]
            span = f"{_fmt_time(first_dry)} – {_fmt_time(last_dry)}" if len(dry) > 1 else _fmt_time(first_dry)
            moments.append({
                "title":    "Dryness Alert",
                "subtitle": f"Humidity below 40% · {len(dry)} readings",
                "value":    f"Min {dry['indoor_humidity'].min():.0f}%",
                "time":     span,
                "color":    "#FFD060",
                "icon":     "◐",
            })

    return moments


# ---------------------------------------------------------------------------
# Replay snapshot at a specific history index
# ---------------------------------------------------------------------------

def replay_snapshot(points: list[dict], idx: int) -> dict:
    """
    Build a summary dict from a HistoryPoint at index idx.
    Returns a dict suitable for display in a snapshot card.
    """
    if not points or idx >= len(points):
        return {}
    pt = points[idx]
    return {
        "timestamp":       pt.get("timestamp", ""),
        "readiness_score": pt.get("readiness_score"),
        "recovery_score":  pt.get("recovery_score"),
        "air_strain_score": pt.get("air_strain_score"),
        "room_state":      pt.get("room_state", ""),
        "temperature_c":   pt.get("temperature_c"),
        "humidity_pct":    pt.get("humidity_pct"),
        "tvoc_ppb":        pt.get("tvoc_ppb"),
        "eco2_ppm":        pt.get("eco2_ppm"),
        "outdoor_temperature_c": pt.get("outdoor_temperature_c"),
        "outdoor_weather": pt.get("outdoor_weather", ""),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_time(row) -> str:
    try:
        return row["timestamp"].strftime("%H:%M")
    except Exception:
        return "—"
