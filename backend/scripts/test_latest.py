import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8080")
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "core2-livingroom")

EXPECTED_FIELDS = {
    "device_id", "timestamp", "indoor_temp", "indoor_humidity",
    "air_quality", "air_quality_label", "motion", "wifi_rssi",
    "indoor_pressure", "indoor_eco2",
    "outdoor_temp", "outdoor_humidity", "outdoor_weather", "outdoor_icon",
    "weather_status", "ingested_at", "sync_status",
}


def run_test(name, device_id):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")

    url = f"{BASE_URL}/api/v1/latest"
    params = {"device_id": device_id} if device_id is not None else {}

    response = requests.get(url, params=params)
    print(f"Status: {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)

    return response


# --- Test 1: valid device_id returns 200 and a data row ---
r = run_test("VALID device_id — expect 200", DEVICE_ID)
assert r.status_code == 200, f"Expected 200, got {r.status_code}"
assert r.json().get("success") is True
assert "data" in r.json()
print("PASS")

# --- Test 2: missing device_id returns 400 ---
r = run_test("MISSING device_id — expect 400", device_id=None)
assert r.status_code == 400, f"Expected 400, got {r.status_code}"
assert r.json().get("success") is False
assert "device_id" in r.json().get("message", "").lower()
print("PASS")

# --- Test 3: unknown device returns 404 ---
r = run_test("UNKNOWN device — expect 404", device_id="ghost-device-999")
assert r.status_code == 404, f"Expected 404, got {r.status_code}"
assert r.json().get("success") is False
print("PASS")

# --- Test 4: response field names match exactly ---
r = run_test("FIELD NAMES CHECK — expect exact keys", DEVICE_ID)
assert r.status_code == 200, f"Expected 200, got {r.status_code}"
returned_fields = set(r.json()["data"].keys())
missing = EXPECTED_FIELDS - returned_fields
extra = returned_fields - EXPECTED_FIELDS
if missing:
    print(f"FAIL — missing fields: {missing}")
elif extra:
    print(f"WARN — unexpected extra fields: {extra}")
else:
    print("PASS — all expected fields present")

print(f"\n{'='*60}")
print("All tests complete.")
print(f"{'='*60}\n")
