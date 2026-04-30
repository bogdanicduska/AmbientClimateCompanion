import os
import requests

BACKEND_URL = os.environ.get(
    "BACKEND_URL",
    "https://ambient-climate-backend-977755576323.europe-west6.run.app/api/v1",
)
DEFAULT_DEVICE_ID = os.environ.get("DEVICE_ID", "m5stack-duska-home")

KNOWN_DEVICES = [
    "m5stack-duska-home",
    "m5stack-ana-home",
]


def fetch_latest(device_id: str = DEFAULT_DEVICE_ID) -> dict | None:
    """Call GET /latest and return the enriched row, or None on failure."""
    try:
        r = requests.get(
            f"{BACKEND_URL}/latest",
            params={"device_id": device_id},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            return _enrich(data)
        return None
    except Exception:
        return None


def fetch_events(device_id: str = DEFAULT_DEVICE_ID, limit: int = 20) -> list[dict]:
    """Call GET /events and return recent device events."""
    try:
        r = requests.get(
            f"{BACKEND_URL}/events",
            params={"device_id": device_id, "limit": limit},
            timeout=8,
        )
        if r.status_code == 200:
            return r.json().get("data", [])
        return []
    except Exception:
        return []


def fetch_history(device_id: str = DEFAULT_DEVICE_ID, hours: int = 24) -> list[dict]:
    """Call GET /history and return a list of enriched rows."""
    try:
        r = requests.get(
            f"{BACKEND_URL}/history",
            params={"device_id": device_id, "hours": hours},
            timeout=10,
        )
        if r.status_code == 200:
            rows = r.json().get("data", [])
            return [_enrich(row) for row in rows]
        return []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Room metrics — mirror of backend/app/services/room_metrics_service.py
# ---------------------------------------------------------------------------

def _compute_air_strain(temp, humidity, aq, eco2) -> int:
    aq    = aq    or 0.0
    eco2  = eco2  or 400.0
    aq_f  = min(100.0, aq / 2.0)
    eco2_f = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    temp_f = min(100.0, max(0.0, (temp - 22.0) * 5.0)) if temp > 22.0 else 0.0
    return int(aq_f * 0.50 + eco2_f * 0.35 + temp_f * 0.15)


def _compute_recovery(temp, humidity, aq, eco2) -> int:
    aq   = aq   or 0.0
    eco2 = eco2 or 400.0
    temp_s = max(0.0, 100.0 - abs(temp - 20.0) * 10.0)
    hum_s  = max(0.0, 100.0 - abs(humidity - 52.0) * 3.0)
    aq_pen   = min(100.0, aq / 2.0)
    eco2_pen = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    air_s = max(0.0, 100.0 - (aq_pen * 0.60 + eco2_pen * 0.40))
    return int(temp_s * 0.35 + hum_s * 0.30 + air_s * 0.35)


def _compute_readiness(temp, humidity, aq, eco2) -> int:
    aq   = aq   or 0.0
    eco2 = eco2 or 400.0
    temp_s = max(0.0, 100.0 - abs(temp - 21.0) * 8.0)
    hum_s  = max(0.0, 100.0 - abs(humidity - 50.0) * 2.5)
    aq_pen   = min(100.0, aq / 2.0)
    eco2_pen = min(100.0, max(0.0, (eco2 - 400) / 16.0))
    air_s = max(0.0, 100.0 - (aq_pen * 0.60 + eco2_pen * 0.40))
    return int(temp_s * 0.40 + hum_s * 0.25 + air_s * 0.35)


def _compute_room_state(readiness, recovery, strain, humidity) -> str:
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


def _enrich(row: dict) -> dict:
    temp     = row.get("indoor_temp")     or 20.0
    humidity = row.get("indoor_humidity") or 50.0
    aq       = row.get("air_quality")     or 0.0
    eco2     = row.get("indoor_eco2")     or 400.0

    readiness = _compute_readiness(temp, humidity, aq, eco2)
    recovery  = _compute_recovery(temp, humidity, aq, eco2)
    strain    = _compute_air_strain(temp, humidity, aq, eco2)
    state     = _compute_room_state(readiness, recovery, strain, humidity)

    return {
        **row,
        "room_readiness": readiness,
        "recovery_score": recovery,
        "air_strain":     strain,
        "room_state":     state,
    }
