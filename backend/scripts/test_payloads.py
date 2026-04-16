import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

BASE_URL = "http://127.0.0.1:8080/api/v1/telemetry"
VALID_TOKEN = os.getenv("DEVICE_AUTH_TOKEN", "changeme")


def run_test(name, payload, headers=None):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    response = requests.post(
        BASE_URL,
        json=payload,
        headers=headers or {"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    print(f"Status: {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)


# --- Test cases ---

good_payload = {
    "device_id":       "core2-livingroom",
    "timestamp":       "2026-04-16T10:30:00Z",
    "indoor_temp":     22.4,
    "indoor_humidity": 43.2,
    "air_quality":     118,
    "motion":          True,
    "wifi_rssi":       -61,
}

missing_device_id_payload = {
    "timestamp":       "2026-04-16T10:30:00Z",
    "indoor_temp":     22.4,
    "indoor_humidity": 43.2,
    "air_quality":     118,
    "motion":          True,
}

missing_humidity_payload = {
    "device_id":   "core2-livingroom",
    "timestamp":   "2026-04-16T10:30:00Z",
    "indoor_temp": 22.4,
    "air_quality": 118,
    "motion":      True,
}

non_numeric_temp_payload = {
    "device_id":       "core2-livingroom",
    "timestamp":       "2026-04-16T10:30:00Z",
    "indoor_temp":     "hot",
    "indoor_humidity": 43.2,
    "air_quality":     118,
    "motion":          True,
}

bad_motion_payload = {
    "device_id":       "core2-livingroom",
    "timestamp":       "2026-04-16T10:30:00Z",
    "indoor_temp":     22.4,
    "indoor_humidity": 43.2,
    "air_quality":     118,
    "motion":          "yes",
}

bad_timestamp_payload = {
    "device_id":       "core2-livingroom",
    "timestamp":       "not-a-date",
    "indoor_temp":     22.4,
    "indoor_humidity": 43.2,
    "air_quality":     118,
    "motion":          True,
}

# --- Run all tests ---

run_test("GOOD PAYLOAD — expect 201, success: true", good_payload)

run_test("MISSING DEVICE_ID — expect 400", missing_device_id_payload)

run_test(
    "BAD AUTH TOKEN — expect 401",
    good_payload,
    headers={"Authorization": "Bearer WRONG_TOKEN"},
)

run_test("MISSING INDOOR_HUMIDITY — expect 400", missing_humidity_payload)

run_test("NON-NUMERIC TEMP — expect 400", non_numeric_temp_payload)

run_test("NON-BOOLEAN MOTION — expect 400", bad_motion_payload)

run_test("INVALID TIMESTAMP FORMAT — expect 400", bad_timestamp_payload)

print(f"\n{'='*60}")
print("All tests complete.")
print(f"{'='*60}\n")
