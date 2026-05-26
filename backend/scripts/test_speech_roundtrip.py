"""
Speech round-trip test — proves the full chain works without a real microphone.

Flow:
  1. POST /speech/tts with known text       -> get MP3 audio back
  2. POST /speech/stt with that MP3 audio   -> get transcript back
  3. Compare transcript to original text    -> should be close

Also tests the combined /speech/query endpoint.
"""
import base64
import json
import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

BASE      = os.getenv("BACKEND_URL", "http://127.0.0.1:8080/api/v1")
TOKEN     = os.getenv("DEVICE_AUTH_TOKEN", "changeme")
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "m5stack-ana-home")
HEADERS   = {"Authorization": f"Bearer {TOKEN}"}

OUT_DIR = os.path.join(os.path.dirname(__file__), "_out")
os.makedirs(OUT_DIR, exist_ok=True)


def _words(s: str) -> set:
    return set(re.findall(r"[a-z]+", s.lower()))


def header(title):
    print(f"\n{'='*64}\n{title}\n{'='*64}")


# ---------------------------------------------------------------------------
# 1. TTS — synthesize every template and the fallback
# ---------------------------------------------------------------------------
header("STEP 1 — TTS: synthesize canned templates")

tmpl_resp = requests.get(f"{BASE}/speech/tts/templates")
print(f"GET /speech/tts/templates -> {tmpl_resp.status_code}")
assert tmpl_resp.status_code == 200, tmpl_resp.text
templates = tmpl_resp.json()["data"]["templates"]
print(f"  Found {len(templates)} templates: {sorted(templates.keys())}")

synth_cases = [
    ("room_ready",     None),
    ("air_strain_low", None),
    ("dry_air",        None),
    (None, "The readiness is seventy eight out of one hundred."),
]

saved_audios = []
for template_key, text in synth_cases:
    payload = {"device_id": DEVICE_ID}
    if template_key:
        payload["template"] = template_key
        label = f"template={template_key}"
    else:
        payload["text"] = text
        label = f"text={text!r}"

    r = requests.post(f"{BASE}/speech/tts", json=payload, headers=HEADERS)
    print(f"  POST /speech/tts ({label}) -> {r.status_code}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    audio_b64 = data["audio_b64"]
    assert len(audio_b64) > 1000, "Audio too small — TTS likely failed"

    # Save for manual playback
    fname = f"tts_{template_key or 'custom'}.mp3"
    fpath = os.path.join(OUT_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(base64.b64decode(audio_b64))
    print(f"    saved {fpath} ({len(audio_b64)} b64 chars, ~{data['duration_ms']}ms)")
    saved_audios.append((data["text"], audio_b64))

print("  [PASS] all TTS templates synthesized")


# ---------------------------------------------------------------------------
# 2. STT — feed the TTS-generated MP3 back in and check the transcript
# ---------------------------------------------------------------------------
header("STEP 2 — STT: transcribe TTS output (round-trip)")

for original_text, audio_b64 in saved_audios:
    r = requests.post(
        f"{BASE}/speech/stt",
        json={"device_id": DEVICE_ID, "audio_b64": audio_b64, "format": "mp3"},
        headers=HEADERS,
    )
    print(f"  POST /speech/stt -> {r.status_code}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    transcript = data.get("transcript", "")
    confidence = data.get("confidence", 0.0)
    print(f"    original : {original_text!r}")
    print(f"    heard    : {transcript!r}  (confidence={confidence})")

    # Rough overlap check — at least 40% of content words should match
    orig_words = _words(original_text)
    heard_words = _words(transcript)
    if orig_words:
        overlap = len(orig_words & heard_words) / len(orig_words)
        print(f"    overlap  : {overlap:.0%}")
        assert overlap >= 0.4, f"Round-trip lost too many words ({overlap:.0%})"

print("  [PASS] STT transcribes TTS output with acceptable overlap")


# ---------------------------------------------------------------------------
# 3. Combined /speech/query — audio in, spoken answer out
# ---------------------------------------------------------------------------
header("STEP 3 — /speech/query: end-to-end pipeline")

# Generate a spoken question via TTS first
tts_r = requests.post(
    f"{BASE}/speech/tts",
    json={"device_id": DEVICE_ID, "text": "What is the room readiness right now?"},
    headers=HEADERS,
)
assert tts_r.status_code == 200
question_audio = tts_r.json()["data"]["audio_b64"]

# Feed it into /speech/query
r = requests.post(
    f"{BASE}/speech/query",
    json={"device_id": DEVICE_ID, "audio_b64": question_audio, "format": "mp3"},
    headers=HEADERS,
)
print(f"  POST /speech/query -> {r.status_code}")
assert r.status_code == 200, r.text

data = r.json()["data"]
print(f"    transcript : {data.get('transcript')!r}")
print(f"    confidence : {data.get('confidence')}")
print(f"    intent     : {data.get('intent')}")
print(f"    answer     : {data.get('answer')!r}")
print(f"    audio_bytes: {len(data.get('audio_b64', ''))} b64 chars")

# Save the spoken answer
with open(os.path.join(OUT_DIR, "query_answer.mp3"), "wb") as f:
    f.write(base64.b64decode(data["audio_b64"]))
print(f"    saved {OUT_DIR}/query_answer.mp3")

assert data["intent"] in {"current_readiness", "unclear", "unknown"}, \
    f"Unexpected intent: {data['intent']}"
print("  [PASS] end-to-end pipeline responded with audio")


# ---------------------------------------------------------------------------
# 4. Fallback path — garbage audio should route to fallback gracefully
# ---------------------------------------------------------------------------
header("STEP 4 — fallback: invalid-ish audio should NOT crash the pipeline")

garbage = base64.b64encode(b"\x00" * 16000).decode("utf-8")
r = requests.post(
    f"{BASE}/speech/query",
    json={"device_id": DEVICE_ID, "audio_b64": garbage, "format": "raw"},
    headers=HEADERS,
)
print(f"  POST /speech/query (garbage) -> {r.status_code}")
# Even on garbage, the pipeline should return 200 with a fallback
assert r.status_code == 200, r.text
data = r.json()["data"]
print(f"    intent   : {data.get('intent')}")
print(f"    answer   : {data.get('answer')!r}")
assert data["intent"] in {"unclear", "unknown", "stt_error"}
print("  [PASS] fallback triggered cleanly on unintelligible audio")


print(f"\n{'='*64}\nAll speech round-trip tests passed.\nAudio artifacts saved in {OUT_DIR}\n{'='*64}\n")
