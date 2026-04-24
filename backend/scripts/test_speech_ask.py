import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL   = "http://127.0.0.1:8080/api/v1/speech/ask"
TOKEN      = os.getenv("DEVICE_AUTH_TOKEN", "changeme")
DEVICE_ID  = os.getenv("TEST_DEVICE_ID", "m5stack-ana-home")
HEADERS    = {"Authorization": f"Bearer {TOKEN}"}


def ask(name, question, expect=200, headers=None):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"Q:    {question}")
    print(f"{'='*60}")
    r = requests.post(
        BASE_URL,
        json={"device_id": DEVICE_ID, "question": question},
        headers=headers or HEADERS,
    )
    print(f"Status: {r.status_code}")
    try:
        body = r.json()
        print(json.dumps(body, indent=2))
        if r.status_code == expect and body.get("success"):
            data = body.get("data", {})
            print(f"  intent  : {data.get('intent')}")
            print(f"  answer  : {data.get('answer')}")
    except Exception:
        print(r.text)
    assert r.status_code == expect, f"Expected {expect}, got {r.status_code}"
    return r


# --- 1. Current room readiness ---
r = ask("CURRENT READINESS", "What is the room readiness right now?")
assert r.json()["data"]["intent"] == "current_readiness"
print("PASS")

# --- 2. Current recovery score ---
r = ask("CURRENT RECOVERY", "How is the recovery score tonight?")
assert r.json()["data"]["intent"] == "current_recovery"
print("PASS")

# --- 3. Current air quality ---
r = ask("CURRENT AIR", "How is the air quality right now?")
assert r.json()["data"]["intent"] == "current_air"
print("PASS")

# --- 4. Temperature yesterday ---
r = ask("TEMP YESTERDAY", "What was the temperature yesterday?")
assert r.json()["data"]["intent"] == "temp_yesterday"
print("PASS")

# --- 5. Humidity threshold ---
r = ask("HUMIDITY THRESHOLD", "Did humidity exceed 60 percent in the last 24 hours?")
assert r.json()["data"]["intent"] == "humidity_threshold"
print("PASS")

# --- 6. Recovery last night ---
r = ask("RECOVERY LAST NIGHT", "Was the room recovery friendly last night?")
assert r.json()["data"]["intent"] == "recovery_lastnight"
print("PASS")

# --- 7. Air strain peak ---
r = ask("AIR STRAIN PEAK", "When did air strain peak today?")
assert r.json()["data"]["intent"] == "air_strain_peak"
print("PASS")

# --- 8. Rain tomorrow ---
r = ask("RAIN TOMORROW", "Is it going to rain tomorrow morning?")
assert r.json()["data"]["intent"] == "rain_tomorrow"
print("PASS")

# --- 9. Umbrella ---
r = ask("UMBRELLA", "Do I need an umbrella tomorrow?")
assert r.json()["data"]["intent"] == "umbrella"
print("PASS")

# --- 10. Unknown intent — should still return 200 with fallback answer ---
r = ask("UNKNOWN INTENT", "What is the meaning of life?")
assert r.json()["data"]["intent"] == "unknown"
print("PASS")

# --- 11. Missing question — expect 400 ---
r = ask("MISSING QUESTION — expect 400", "", expect=400)
print("PASS")

# --- 12. Bad auth — expect 401 ---
r = ask("BAD AUTH — expect 401", "What is the readiness?",
        expect=401, headers={"Authorization": "Bearer WRONG"})
print("PASS")

# --- 13. Question too long — expect 400 ---
r = ask("QUESTION TOO LONG — expect 400", "A" * 301, expect=400)
print("PASS")

print(f"\n{'='*60}")
print("All speech/ask tests complete.")
print(f"{'='*60}\n")
