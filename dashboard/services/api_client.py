import os
import requests

# Override at runtime via environment variables:
#   BACKEND_URL  — full API base URL (no trailing slash), e.g. https://your-backend/api/v1
#   DEVICE_ID    — default device shown in the sidebar selector
#   KNOWN_DEVICES — comma-separated list of device IDs available in the sidebar
BACKEND_URL = os.environ.get(
    "BACKEND_URL",
    "https://ambient-climate-backend-977755576323.europe-west6.run.app/api/v1",
)
DEFAULT_DEVICE_ID = os.environ.get("DEVICE_ID", "m5stack-duska-home")

_devices_env = os.environ.get("KNOWN_DEVICES", "")
KNOWN_DEVICES = (
    [d.strip() for d in _devices_env.split(",") if d.strip()]
    if _devices_env
    else ["m5stack-duska-home", "m5stack-ana-home"]
)


def fetch_latest(device_id: str = DEFAULT_DEVICE_ID) -> dict | None:
    try:
        r = requests.get(
            f"{BACKEND_URL}/latest",
            params={"device_id": device_id},
            timeout=8,
        )
        if r.status_code == 200:
            return r.json().get("data", {})
        return None
    except Exception:
        return None


def fetch_history(device_id: str = DEFAULT_DEVICE_ID, hours: int = 24) -> list[dict]:
    try:
        r = requests.get(
            f"{BACKEND_URL}/history",
            params={"device_id": device_id, "hours": hours},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("data", [])
        return []
    except Exception:
        return []


def fetch_daily_summary(device_id: str = DEFAULT_DEVICE_ID, date: str = "") -> dict | None:
    """Call GET /daily-summary and return a DailyRoomStory dict, or None on failure."""
    try:
        params: dict = {"device_id": device_id}
        if date:
            params["date"] = date
        r = requests.get(f"{BACKEND_URL}/daily-summary", params=params, timeout=8)
        if r.status_code == 200:
            return r.json().get("data")
        return None
    except Exception:
        return None


def fetch_events(device_id: str = DEFAULT_DEVICE_ID, limit: int = 20) -> list[dict]:
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
