"""
Room performance metrics — canonical source of truth for Room Rhythm scores.

These formulas are the single source of truth for the project.
The dashboard uses them as a fallback; it prefers backend-computed scores
when the API returns them (which it always does after this was added).
The device mirrors these formulas for local display between telemetry sends.

FORMULA RATIONALE
=================
All three scores share the same air quality sub-formula:
  air_score = 100 - (tvoc_penalty * 0.60 + eco2_penalty * 0.40)
  where tvoc_penalty = min(100, tvoc_ppb / 2)      → 200 ppb maps to 100
        eco2_penalty = min(100, (ppm - 400) / 16)  → 2000 ppm maps to 100

Room Readiness (focus / presence)
  Ideal: 21°C, 50% RH, clean air
  Temp ideal slightly warmer than recovery — alertness needs mild warmth.
  Temp weight 40%: temperature is the dominant environmental focus cue.
  Humidity weight 25%: comfort matters but is secondary for focus.
  Air weight 35%: high TVOC / CO2 impairs cognition directly.

Recovery Score (rest / calm)
  Ideal: 20°C, 52% RH, clean air
  Temp ideal 1°C cooler than readiness — slightly cooler rooms promote sleep.
  Humidity ideal slightly higher (52% vs 50%) — more moisture helps airways at rest.
  Temp weight 35%, Humidity weight 30%, Air weight 35%: more balanced split
  because moisture matters more during sleep than during active use.

Air Strain (heaviness / staleness)
  Rises with TVOC (50%), eCO2 (35%), and heat above 22°C (15%).
  TVOC dominates because it is the most direct indicator of air freshness.
  eCO2 reflects occupancy and ventilation quality.
  Temperature contribution is minor but adds context when air and heat combine.

Room State (human label)
  Priority cascade: Dry → Heavy → Social → Fresh → Sleep-Friendly → Calm → Restless → Calm
  Social requires motion=True — only the backend receives motion data, so this
  state appears in API responses and on the device (which has a PIR sensor)
  but defaults to False when motion is unavailable.
"""

from typing import Dict, Any


def compute_air_strain(temp: float, humidity: float, aq: float, eco2: float) -> int:
    """
    0 = fresh air, 100 = very heavy/strained.
    TVOC 50% + eCO2 35% + heat-above-22°C 15%.
    """
    aq   = aq   or 0.0
    eco2 = eco2 or 400.0

    aq_factor   = min(100.0, aq / 2.0)
    eco2_factor = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    temp_factor = min(100.0, max(0.0, (temp - 22.0) * 5.0)) if temp > 22.0 else 0.0

    return int(aq_factor * 0.50 + eco2_factor * 0.35 + temp_factor * 0.15)


def compute_recovery_score(temp: float, humidity: float, aq: float, eco2: float) -> int:
    """
    0 = poor recovery conditions, 100 = ideal for rest.
    Ideal room: 20°C, 52% RH, clean air. Weights: temp 35%, RH 30%, air 35%.
    """
    aq   = aq   or 0.0
    eco2 = eco2 or 400.0

    temp_score = max(0.0, 100.0 - abs(temp - 20.0) * 10.0)   # ±10°C from 20 → 0
    hum_score  = max(0.0, 100.0 - abs(humidity - 52.0) * 3.0) # ±33% from 52 → 0

    aq_penalty   = min(100.0, aq / 2.0)
    eco2_penalty = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    air_score    = max(0.0, 100.0 - (aq_penalty * 0.60 + eco2_penalty * 0.40))

    return int(temp_score * 0.35 + hum_score * 0.30 + air_score * 0.35)


def compute_room_readiness(temp: float, humidity: float, aq: float, eco2: float) -> int:
    """
    0 = poor focus conditions, 100 = ideal for alertness.
    Ideal room: 21°C, 50% RH, clean air. Weights: temp 40%, RH 25%, air 35%.
    """
    aq   = aq   or 0.0
    eco2 = eco2 or 400.0

    temp_score = max(0.0, 100.0 - abs(temp - 21.0) * 8.0)    # ±12.5°C from 21 → 0
    hum_score  = max(0.0, 100.0 - abs(humidity - 50.0) * 2.5) # ±40% from 50 → 0

    aq_penalty   = min(100.0, aq / 2.0)
    eco2_penalty = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    air_score    = max(0.0, 100.0 - (aq_penalty * 0.60 + eco2_penalty * 0.40))

    return int(temp_score * 0.40 + hum_score * 0.25 + air_score * 0.35)


def compute_room_state(
    readiness: int,
    recovery: int,
    strain: int,
    humidity: float,
    motion: bool = False,
) -> str:
    """
    Derive a human label from computed scores.
    Priority cascade (first match wins):
      Dry           — humidity < 40%: discomfort dominates regardless of other scores
      Heavy         — strain >= 65: air quality is the story
      Social        — motion present: room is actively occupied
      Fresh         — strain low + humidity in range: best-case air
      Sleep-Friendly — recovery high: conditions support rest
      Calm          — moderate recovery: comfortable but not exceptional
      Restless      — strain elevated but not heavy: something to address
      Calm          — default fallback
    """
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


def enrich_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Attach computed room metrics to a raw BigQuery row dict.
    Returns both spec-aligned names (readiness_score / recovery_score / air_strain_score)
    and legacy aliases (room_readiness / air_strain) for backward compatibility
    with any consumers that predate the spec-aligned naming.
    """
    temp     = row.get("indoor_temp")     or 20.0
    humidity = row.get("indoor_humidity") or 50.0
    aq       = row.get("air_quality")     or 0.0
    eco2     = row.get("indoor_eco2")     or 400.0
    motion   = bool(row.get("motion", False))

    readiness = compute_room_readiness(temp, humidity, aq, eco2)
    recovery  = compute_recovery_score(temp, humidity, aq, eco2)
    strain    = compute_air_strain(temp, humidity, aq, eco2)
    state     = compute_room_state(readiness, recovery, strain, humidity, motion)

    return {
        **row,
        # spec-aligned names
        "readiness_score":  readiness,
        "recovery_score":   recovery,
        "air_strain_score": strain,
        "room_state":       state,
        # legacy aliases
        "room_readiness": readiness,
        "air_strain":     strain,
    }
