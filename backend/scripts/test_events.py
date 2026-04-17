import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

BASE_URL = "http://127.0.0.1:8080/api/v1/events"
VALID_TOKEN = os.getenv("DEVICE_AUTH_TOKEN", "changeme")
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "core2-livingroom")


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
    return response


# --- Test 1: valid boot_recovered event ---
r = run_test("BOOT RECOVERED — expect 201", {
    "device_id": DEVICE_ID,
    "event_type": "boot_recovered",
    "timestamp": "2026-04-17T08:00:00Z",
    "details": {"reason": "power_loss"},
})
assert r.status_code == 201, f"Expected 201, got {r.status_code}"
print("PASS")

# --- Test 2: wifi_disconnected with no details ---
r = run_test("WIFI DISCONNECTED — expect 201", {
    "device_id": DEVICE_ID,
    "event_type": "wifi_disconnected",
})
assert r.status_code == 201
print("PASS")

# --- Test 3: humidity_alert ---
r = run_test("HUMIDITY ALERT — expect 201", {
    "device_id": DEVICE_ID,
    "event_type": "humidity_alert",
    "details": {"value": 87.3, "threshold": 80},
})
assert r.status_code == 201
print("PASS")

# --- Test 4: air_quality_alert ---
r = run_test("AIR QUALITY ALERT — expect 201", {
    "device_id": DEVICE_ID,
    "event_type": "air_quality_alert",
    "details": {"value": 210, "label": "Hazardous"},
})
assert r.status_code == 201
print("PASS")

# --- Test 5: announcement_spoken ---
r = run_test("ANNOUNCEMENT SPOKEN — expect 201", {
    "device_id": DEVICE_ID,
    "event_type": "announcement_spoken",
    "details": {"text": "Air quality is poor"},
})
assert r.status_code == 201
print("PASS")

# --- Test 6: unknown event_type — expect 400 ---
r = run_test("UNKNOWN EVENT TYPE — expect 400", {
    "device_id": DEVICE_ID,
    "event_type": "self_destruct",
})
assert r.status_code == 400
assert "event_type" in r.json().get("message", "").lower()
print("PASS")

# --- Test 7: missing device_id — expect 400 ---
r = run_test("MISSING DEVICE_ID — expect 400", {
    "event_type": "boot_recovered",
})
assert r.status_code == 400
assert "device_id" in r.json().get("message", "").lower()
print("PASS")

# --- Test 8: bad auth token — expect 401 ---
r = run_test("BAD AUTH — expect 401", {
    "device_id": DEVICE_ID,
    "event_type": "boot_recovered",
}, headers={"Authorization": "Bearer WRONG_TOKEN"})
assert r.status_code == 401
print("PASS")

print(f"\n{'='*60}")
print("All event tests complete.")
print(f"{'='*60}\n")
