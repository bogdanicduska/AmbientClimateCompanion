"""Hit the deployed /speech/tts endpoint, fetch raw PCM (what the M5Stack pulls),
and wrap it in a WAV header locally so you can play it on your laptop.

Usage:
    python scripts/test_tts_pcm_cloud.py
    python scripts/test_tts_pcm_cloud.py "your custom text here"
"""
import os
import struct
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

# Point at the deployed Cloud Run URL by default; override with TTS_BASE if needed.
BASE      = os.getenv("TTS_BASE", "https://ambient-climate-backend-977755576323.europe-west6.run.app/api/v1")
TOKEN     = os.getenv("DEVICE_AUTH_TOKEN", "weather2026")
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "m5stack-ana-home")

TEXT = sys.argv[1] if len(sys.argv) > 1 else "Hello. This is a speech test from your room assistant."

OUT = os.path.join(os.path.dirname(__file__), "_out")
os.makedirs(OUT, exist_ok=True)


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int, bits: int, channels: int) -> bytes:
    """Wrap raw signed-LE PCM in a minimal RIFF/WAVE header so any audio player can open it."""
    byte_rate   = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    data_size   = len(pcm_bytes)
    riff_size   = 36 + data_size
    return (
        b"RIFF" + struct.pack("<I", riff_size) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits)
        + b"data" + struct.pack("<I", data_size)
        + pcm_bytes
    )


print(f"POST {BASE}/speech/tts?raw=1&profile=m5stack  (format=wav, 16 kHz / 16-bit signed / mono)")
r = requests.post(
    f"{BASE}/speech/tts?raw=1&profile=m5stack",
    json={"device_id": DEVICE_ID, "text": TEXT, "format": "wav"},
    headers={"Authorization": f"Bearer {TOKEN}"},
    timeout=60,
)
print(f"  status: {r.status_code}")
r.raise_for_status()

ctype = r.headers.get("Content-Type", "")
rate  = int(r.headers.get("X-Sample-Rate", 16000))
bits  = int(r.headers.get("X-Bit-Depth",   16))
chans = int(r.headers.get("X-Channels",    1))
enc   = r.headers.get("X-Encoding", "")
spoken = r.headers.get("X-Spoken-Text", "")
print(f"  content-type: {ctype}")
print(f"  format hdrs : rate={rate} bits={bits} channels={chans} enc={enc}")
print(f"  spoken text : {spoken!r}")

audio = r.content
secs  = len(audio) / max(1, (rate * chans * bits // 8))
print(f"  bytes       : {len(audio)}  (~{secs:.2f} s)")

wav_path = os.path.join(OUT, "tts_cloud_m5.wav")
with open(wav_path, "wb") as f:
    f.write(audio)

print()
print(f"  WAV -> {wav_path}  (this is the exact file the M5Stack will save to /sd/answer.wav)")
print("  open it in VLC/QuickTime/Windows Media to verify it sounds right.")
print()
print("If this WAV plays on your laptop, the backend is good. Anything wrong on-device")
print("after that points at WiFi / SD card / amp on the Core2, not the server.")
