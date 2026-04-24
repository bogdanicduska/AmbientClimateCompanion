"""
Proactive assistant tests.

1. Dry-run evaluation with current room state.
2. Unit-test every trigger's condition function with synthetic snapshots.
3. Live call — if a trigger fires, verify audio is returned and cooldown is logged.
4. Immediate re-call — confirms cooldown blocks repeat announcements.
"""
import base64
import json
import os
import sys
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.proactive_service import PROACTIVE_TRIGGERS

load_dotenv()

BASE      = "http://127.0.0.1:8080/api/v1"
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "m5stack-ana-home")

OUT_DIR = os.path.join(os.path.dirname(__file__), "_out")
os.makedirs(OUT_DIR, exist_ok=True)


def header(title):
    print(f"\n{'='*64}\n{title}\n{'='*64}")


# ---------------------------------------------------------------------------
# 1. Unit-test trigger condition functions with synthetic snapshots
# ---------------------------------------------------------------------------
header("STEP 1 — unit: each trigger fires for its intended condition")

trigger_cases = {
    "air_strain_rising":       ({"air_strain": 72, "indoor_humidity": 50, "recovery_score": 40, "forecast_morning_rain": False}, 12),
    "dry_air":                 ({"air_strain": 10, "indoor_humidity": 34, "recovery_score": 60, "forecast_morning_rain": False}, 12),
    "recovery_good_evening":   ({"air_strain": 15, "indoor_humidity": 52, "recovery_score": 82, "forecast_morning_rain": False}, 22),
    "rain_tomorrow_morning":   ({"air_strain": 15, "indoor_humidity": 50, "recovery_score": 60, "forecast_morning_rain": True}, 12),
}

triggers_by_id = {t["id"]: t for t in PROACTIVE_TRIGGERS}

for trigger_id, (snapshot, hour) in trigger_cases.items():
    t = triggers_by_id[trigger_id]
    fires = t["check"](snapshot, hour)
    status = "PASS" if fires else "FAIL"
    print(f"  [{status}] {trigger_id} fires when expected -> {fires}")
    assert fires, f"{trigger_id} should have fired for {snapshot} @ hour {hour}"

# Negative case — all calm → nothing should fire
calm = {"air_strain": 10, "indoor_humidity": 50, "recovery_score": 50, "forecast_morning_rain": False}
any_fired = any(t["check"](calm, 14) for t in PROACTIVE_TRIGGERS)
print(f"  [{'PASS' if not any_fired else 'FAIL'}] calm state fires nothing -> {not any_fired}")
assert not any_fired


# ---------------------------------------------------------------------------
# 2. Dry run against real endpoint (does NOT affect cooldown)
# ---------------------------------------------------------------------------
header("STEP 2 — dry-run: what does the current room state evaluate to?")

r = requests.get(f"{BASE}/speech/proactive", params={"device_id": DEVICE_ID, "dry_run": 1})
print(f"  GET /speech/proactive?dry_run=1 -> {r.status_code}")
assert r.status_code == 200, r.text
data = r.json()["data"]
print(json.dumps(data, indent=2))

if data.get("announce"):
    print(f"  [INFO] current state would fire trigger: {data['trigger_id']}")
else:
    print("  [INFO] current state would not fire any trigger (that's fine — conditions are calm)")


# ---------------------------------------------------------------------------
# 3. Live call — if something fires, audio should come back
# ---------------------------------------------------------------------------
header("STEP 3 — live call: audio + event log (may skip if nothing fires)")

live = requests.get(f"{BASE}/speech/proactive", params={"device_id": DEVICE_ID})
print(f"  GET /speech/proactive -> {live.status_code}")
assert live.status_code == 200, live.text
live_data = live.json()["data"]

if live_data.get("announce"):
    audio_b64 = live_data.get("audio_b64", "")
    assert len(audio_b64) > 1000, "Audio too small — TTS likely failed"
    fname = f"proactive_{live_data['trigger_id']}.mp3"
    with open(os.path.join(OUT_DIR, fname), "wb") as f:
        f.write(base64.b64decode(audio_b64))
    print(f"  [PASS] {live_data['trigger_id']} spoken -> {OUT_DIR}/{fname}")
    print(f"         text: {live_data['text']!r}")

    # --- 4. Cooldown — a second call should NOT re-announce the same trigger ---
    header("STEP 4 — cooldown: second call must NOT re-announce same trigger")
    r2 = requests.get(f"{BASE}/speech/proactive", params={"device_id": DEVICE_ID})
    assert r2.status_code == 200
    d2 = r2.json()["data"]
    if d2.get("announce") and d2.get("trigger_id") == live_data["trigger_id"]:
        print(f"  [FAIL] same trigger {d2['trigger_id']} re-announced within cooldown")
        sys.exit(1)
    elif d2.get("announce"):
        print(f"  [PASS] first trigger suppressed; next trigger surfaced: {d2['trigger_id']}")
    else:
        print(f"  [PASS] cooldown suppressed the announcement")
else:
    print("  [SKIP] nothing fired on current state — cannot test cooldown this run")


# ---------------------------------------------------------------------------
# 5. Force every trigger — demo-ready audio for all 4 scenarios
# ---------------------------------------------------------------------------
header("STEP 5 — force each trigger and save demo audio")

for trigger in PROACTIVE_TRIGGERS:
    tid = trigger["id"]
    r = requests.get(f"{BASE}/speech/proactive", params={"device_id": DEVICE_ID, "force": tid})
    print(f"  GET /speech/proactive?force={tid} -> {r.status_code}")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d.get("announce") is True
    assert d.get("forced") is True
    assert d.get("trigger_id") == tid

    audio_b64 = d.get("audio_b64", "")
    assert len(audio_b64) > 1000, f"Audio too small for {tid}"
    fname = f"proactive_force_{tid}.mp3"
    with open(os.path.join(OUT_DIR, fname), "wb") as f:
        f.write(base64.b64decode(audio_b64))
    print(f"    [PASS] {tid}: {d['text']!r}")
    print(f"           saved -> {OUT_DIR}/{fname}")

# Invalid trigger_id — expect 400
r = requests.get(f"{BASE}/speech/proactive", params={"device_id": DEVICE_ID, "force": "not_a_real_trigger"})
assert r.status_code == 400
print(f"  [PASS] unknown trigger -> 400")


print(f"\n{'='*64}\nProactive tests complete. Audio saved in {OUT_DIR}\n{'='*64}\n")
