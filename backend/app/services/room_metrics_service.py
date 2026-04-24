from typing import Dict, Any


def compute_air_strain(temp: float, humidity: float, aq: float, eco2: float) -> int:
    """0 = fresh, 100 = very heavy/strained."""
    aq = aq or 0.0
    eco2 = eco2 or 400.0

    aq_factor   = min(100.0, aq / 2.0)                           # 0–200 ppb → 0–100
    eco2_factor = min(100.0, max(0.0, (eco2 - 400) / 16.0))      # 400–2000 ppm → 0–100
    temp_factor = min(100.0, max(0.0, (temp - 22.0) * 5.0)) if temp > 22.0 else 0.0

    return int(aq_factor * 0.50 + eco2_factor * 0.35 + temp_factor * 0.15)


def compute_recovery_score(temp: float, humidity: float, aq: float, eco2: float) -> int:
    """0 = poor recovery conditions, 100 = ideal. Optimised for rest (20°C, 52% RH, clean air)."""
    aq = aq or 0.0
    eco2 = eco2 or 400.0

    temp_score = max(0.0, 100.0 - abs(temp - 20.0) * 10.0)
    hum_score  = max(0.0, 100.0 - abs(humidity - 52.0) * 3.0)

    aq_penalty   = min(100.0, aq / 2.0)
    eco2_penalty = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    air_score    = max(0.0, 100.0 - (aq_penalty * 0.60 + eco2_penalty * 0.40))

    return int(temp_score * 0.35 + hum_score * 0.30 + air_score * 0.35)


def compute_room_readiness(temp: float, humidity: float, aq: float, eco2: float) -> int:
    """0 = poor focus conditions, 100 = ideal. Optimised for alertness (21°C, 50% RH, clean air)."""
    aq = aq or 0.0
    eco2 = eco2 or 400.0

    temp_score = max(0.0, 100.0 - abs(temp - 21.0) * 8.0)
    hum_score  = max(0.0, 100.0 - abs(humidity - 50.0) * 2.5)

    aq_penalty   = min(100.0, aq / 2.0)
    eco2_penalty = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    air_score    = max(0.0, 100.0 - (aq_penalty * 0.60 + eco2_penalty * 0.40))

    return int(temp_score * 0.40 + hum_score * 0.25 + air_score * 0.35)


def compute_room_state(readiness: int, recovery: int, strain: int, humidity: float) -> str:
    if humidity < 40:
        return "Dry"
    if strain >= 65:
        return "Heavy"
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
    """Attach computed room metrics to a BigQuery row dict."""
    temp     = row.get("indoor_temp") or 20.0
    humidity = row.get("indoor_humidity") or 50.0
    aq       = row.get("air_quality") or 0.0
    eco2     = row.get("indoor_eco2") or 400.0

    readiness = compute_room_readiness(temp, humidity, aq, eco2)
    recovery  = compute_recovery_score(temp, humidity, aq, eco2)
    strain    = compute_air_strain(temp, humidity, aq, eco2)
    state     = compute_room_state(readiness, recovery, strain, humidity)

    return {
        **row,
        "room_readiness": readiness,
        "recovery_score": recovery,
        "air_strain":     strain,
        "room_state":     state,
    }
