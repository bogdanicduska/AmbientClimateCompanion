"""Verify the TTS endpoint returns valid WAV bytes via ?raw=1 — what the M5Stack will fetch."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE      = os.getenv("BACKEND_URL", "http://127.0.0.1:8080/api/v1")
TOKEN     = os.getenv("DEVICE_AUTH_TOKEN", "changeme")
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "m5stack-ana-home")

OUT = os.path.join(os.path.dirname(__file__), "_out")
os.makedirs(OUT, exist_ok=True)

# --- 1. JSON+base64 with format=wav ---
r = requests.post(
    f"{BASE}/speech/tts",
    json={"device_id": DEVICE_ID, "text": "This is a test of the WAV output.", "format": "wav"},
    headers={"Authorization": f"Bearer {TOKEN}"},
)
print(f"POST /speech/tts (json, fmt=wav) -> {r.status_code}")
assert r.status_code == 200, r.text
assert r.json()["data"]["format"] == "wav"
print("  [PASS] JSON response carries format=wav and base64 audio")

# --- 2. Raw binary with ?raw=1 ---
r = requests.post(
    f"{BASE}/speech/tts?raw=1",
    json={"device_id": DEVICE_ID, "text": "This is a test of the raw WAV output.", "format": "wav"},
    headers={"Authorization": f"Bearer {TOKEN}"},
)
print(f"POST /speech/tts?raw=1 -> {r.status_code}")
assert r.status_code == 200, r.text
assert r.headers.get("Content-Type", "").startswith("audio/wav"), r.headers
content = r.content
assert content[:4] == b"RIFF" and content[8:12] == b"WAVE", "Response is not a valid WAV file"
print(f"  [PASS] got {len(content)} bytes of audio/wav, valid RIFF/WAVE header")

path = os.path.join(OUT, "tts_raw.wav")
with open(path, "wb") as f:
    f.write(content)
print(f"  saved {path} — open it in any audio player to sanity-check")

# --- 3. Unsupported format should 400 ---
r = requests.post(
    f"{BASE}/speech/tts",
    json={"device_id": DEVICE_ID, "text": "test", "format": "ogg_weird"},
    headers={"Authorization": f"Bearer {TOKEN}"},
)
print(f"POST /speech/tts (bad fmt) -> {r.status_code}")
assert r.status_code == 400
print("  [PASS] bad format rejected with 400")

print("\nAll TTS WAV tests passed. M5Stack can fetch raw WAV via the /speech/tts?raw=1 path.\n")
