# -------------------------------------------------------------------
# speech_debug.py
# Step by step debug version for Core2 speech.
#
# Buttons (each handler is re-entry guarded):
#   A = Record + STT — record mic → /speech/stt → display transcription
#   B = TTS only — cycles through TEST_TEXTS, plays each via speaker.playWAV
#   C = Voice ASK — record mic → /speech/stt → /speech/ask → /speech/tts → play
#       (the real voice loop the project spec asks for)
#
# Fallback: test_ask_then_tts() exists in this file but is unbound. To test
# the answer pipeline with TYPED text instead of voice, switch the btnC.wasPressed
# binding at the bottom of this file from test_voice_ask to test_ask_then_tts.
#
# Notes:
# - Mic uses MicrophonePDM (Core2 built-in PDM mic, WS=0 / DATA=34, 16 kHz
#   16-bit mono). The PDM mic and speaker share the I2S0 peripheral on the
#   Core2, so we MUST init the mic only when recording and release it again
#   before doing any speaker.playWAV — leaving MIC.begin() active across a
#   playback causes the device to reset when the speaker DMA completes.
# - We do NOT import machine.I2S at module load on this firmware. Doing so
#   locks the I2S peripheral and speaker.playTone hangs.
# - Outgoing WAVs (recorded) and incoming WAVs (TTS) are both 16 kHz / 16-bit
#   mono, saved to /sd/ if mounted, else /flash.
# -------------------------------------------------------------------

from m5stack import lcd, btnA, btnB, btnC, speaker
from m5ui import *
from uiflow import *
import MicrophonePDM as MIC
import network
import urequests
import ujson
import time
import gc
import uos
import ubinascii

# SDCard + Pin from machine are safe to import. machine.I2S is NOT — importing
# it locks the I2S peripheral on this firmware and speaker.playTone hangs.
try:
    from machine import SDCard, Pin
    _HAS_SDCARD = True
except Exception as _sd_imp_err:
    print("SD: machine.SDCard import failed:", _sd_imp_err)
    _HAS_SDCARD = False

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------
WIFI_SSID = "LopezLed"
WIFI_PASS = "Chuma12345"

BACKEND_URL = "https://ambient-climate-backend-977755576323.europe-west6.run.app"
DEVICE_AUTH_TOKEN = "weather2026"
DEVICE_ID = "m5stack-ana-home"

# Short test phrases for button B. Press B repeatedly to cycle through them —
# each press hits /speech/tts with a different text so we exercise the endpoint
# with varied inputs without re-flashing. Keep these short (under ~1 second of
# audio ≈ 32 KB at 16 kHz / 16-bit) until the chunked-download fix is in.
TEST_TEXTS = (
    "Hi.",
    "The room feels good.",
    "Air quality is fine.",
    "Humidity is comfortable.",
)
_test_idx = 0

# Short questions for button C — same idea, hits /speech/ask with variety.
ASK_QUESTIONS = (
    "How is the air quality?",
    "Is the room ready?",
    "What is the temperature?",
)
_ask_idx = 0

# Backend ?profile=m5stack returns 16 kHz / 16-bit signed / mono. UIFlow1's
# speaker module on this firmware exposes constants F16B / F24B / F32B for
# bit depth — there is no F8B, so 8-bit is rejected as "data format is not
# valid". 16 kHz keeps a 3 s clip ~100 KB which playWAV can stream from disk.
# The fmt chunk read off /sd/answer.wav after download MUST show
# "PCM 16000Hz 16b ch1" for playback to work.
WAV_RATE = 16000
WAV_BITS = 16

WAV_PATHS = ("/sd/answer.wav", "/flash/answer.wav")

# Microphone recording config — kept SHORT because the recorded WAV gets
# base64-wrapped into a JSON body that urequests buffers in RAM. ESP32 heap on
# this firmware is around 110 KB, so we have to stay well under that.
#   2 s @ 16 kHz / 16-bit / mono = 64 KB raw → ~85 KB base64
# If we OOM on upload, drop RECORD_RATE to 8000 (32 KB raw → 43 KB b64).
RECORD_PATH    = "/sd/question.wav"
RECORD_SECONDS = 2
RECORD_RATE    = 16000

# PDM mic pins on M5Stack Core2: WS=0, DATA=34. buffer_length_ms must be >=
# the longest recording we'll make (give headroom). Initialised once at boot.
MIC_WS_PIN     = 0
MIC_DATA_PIN   = 34
MIC_BUF_MS     = 5000
MIC_BLOCK_MS   = 100

# -------------------------------------------------------------------
# Re-entry guard — capacitive touch buttons can self-trigger from speaker
# vibration; without this, pressing A locks the device into endless beeps.
# -------------------------------------------------------------------
_busy = False
def _guard(handler):
    def wrapped():
        global _busy
        if _busy:
            print("guard: handler already running, ignoring press")
            return
        _busy = True
        try:
            handler()
        except Exception as e:
            print("handler error:", e)
        finally:
            _busy = False
    return wrapped

# -------------------------------------------------------------------
# UI
# -------------------------------------------------------------------
setScreenColor(0x111111)

def show(line1="", line2="", line3="", c1=0xFFFFFF, c2=0x00FFCC, c3=0xAAAAAA):
    lcd.clear()
    lcd.setCursor(5, 10);  lcd.setColor(c1); lcd.print(line1[:38])
    if line2:
        lcd.setCursor(5, 45); lcd.setColor(c2); lcd.print(line2[:38])
    if line3:
        lcd.setCursor(5, 80); lcd.setColor(c3); lcd.print(line3[:38])

def show_idle():
    show("Speech Debug", "A stt   B tts   C ask", "")

def _auth_headers():
    return {
        "Authorization": "Bearer " + DEVICE_AUTH_TOKEN,
        "Content-Type":  "application/json",
    }

# -------------------------------------------------------------------
# SD card mount — Core2 built-in slot uses sck=23, miso=33, mosi=19.
# We try this in order:
#   1. uos.listdir('/sd')   — already mounted by firmware? then we're done.
#   2. uos.mountsd(sd, ...) — UIFlow1 helper.
#   3. uos.mount(sd, ...)   — generic MicroPython VFS mount.
# Returns True if /sd is usable after the call.
# -------------------------------------------------------------------
def mount_sd():
    if not _HAS_SDCARD:
        return False
    try:
        uos.listdir("/sd")
        print("SD: already mounted at /sd")
        return True
    except Exception:
        pass
    try:
        sd = SDCard(slot=2, sck=Pin(23), miso=Pin(33), mosi=Pin(19), freq=10000000)
    except Exception as e:
        print("SD: SDCard() failed:", e)
        return False
    fn = getattr(uos, "mountsd", None)
    if fn:
        try:
            fn(sd, "/sd")
            print("SD: mounted via uos.mountsd")
            return True
        except Exception as e:
            print("SD: uos.mountsd failed:", e)
    try:
        uos.mount(sd, "/sd")
        print("SD: mounted via uos.mount")
        return True
    except Exception as e:
        print("SD: uos.mount failed:", e)
        return False

# -------------------------------------------------------------------
# WiFi
# -------------------------------------------------------------------
def ensure_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        show("WiFi already OK", wlan.ifconfig()[0])
        time.sleep(1)
        return True
    show("Connecting WiFi", WIFI_SSID, "")
    wlan.connect(WIFI_SSID, WIFI_PASS)
    for _ in range(20):
        if wlan.isconnected():
            show("WiFi connected", wlan.ifconfig()[0])
            time.sleep(1)
            return True
        time.sleep(0.5)
    show("WiFi failed", "Check SSID/pass", "")
    time.sleep(2)
    return False

# -------------------------------------------------------------------
# Fetch the WAV — backend ?profile=m5stack returns 16 kHz / 16-bit / mono.
# -------------------------------------------------------------------
def fetch_tts_wav(text):
    try:
        body = ujson.dumps({
            "device_id": DEVICE_ID,
            "text":      text,
            "format":    "wav",
        }).encode("utf-8")

        url = BACKEND_URL + "/api/v1/speech/tts?raw=1&profile=m5stack"
        r = urequests.post(url, data=body, headers=_auth_headers())
        show("TTS HTTP", str(r.status_code), "Downloading")
        print("TTS status:", r.status_code)

        if r.status_code != 200:
            try: err = r.text
            except: err = "no text"
            print("TTS err body:", err)
            r.close()
            return False, "HTTP " + str(r.status_code)

        try:
            content = r.content
        except Exception as e:
            r.close()
            return False, "no body: " + str(e)
        r.close()

        last_err = "no path"
        for candidate in WAV_PATHS:
            try:
                with open(candidate, "wb") as f:
                    f.write(content)
                size = len(content) if content else 0
                print("WAV saved:", candidate, "size:", size)
                # Drop the in-memory copy ASAP — we already wrote it to disk
                # and playWAV will stream from the file. Holding ~50-100 KB of
                # WAV bytes alive across playback fragments the heap and the
                # device resets when async DMA cleanup tries to allocate.
                del content
                gc.collect()
                show("WAV saved", "size " + str(size), candidate)
                time.sleep(1)
                return True, candidate
            except Exception as e:
                last_err = "{0}: {1}".format(candidate, e)
                print("write failed:", last_err)
        return False, last_err

    except Exception as e:
        print("fetch_tts_wav error:", e)
        return False, str(e)

# -------------------------------------------------------------------
# Playback — minimal. Mirrors the standalone player script exactly:
#     speaker.playWAV(path, rate=16000, data_format=speaker.F16B,
#                      channel=speaker.CHN_R, volume=3)
#     wait_ms(<duration>)
# We deliberately do NOT pre-read the WAV into a Python bytes object — that
# previously held ~100 KB live across async DMA playback, fragmenting the
# heap and causing the device to reset right after playback finished.
#
# Volume kept at 3 (matches the working player). Pushing to 6 measurably
# increases the chance of a brownout reset on USB power.
# -------------------------------------------------------------------
PLAY_VOLUME = 3

def play_wav_file(wav_path):
    # Estimate WAV duration so we can sleep through async playback.
    try:
        wav_size = uos.stat(wav_path)[6]
    except Exception:
        wav_size = 0
    bytes_per_sec = WAV_RATE * (WAV_BITS // 8)  # mono
    est_secs = max(1.0, (wav_size - 44) / float(bytes_per_sec)) if wav_size else 3.0
    if est_secs > 30:
        est_secs = 30

    # Free heap before kicking off async DMA — fewer allocations during the
    # speaker IRQ path means lower chance of a panic during DMA cleanup.
    gc.collect()

    show("Playing", wav_path, "")
    try:
        speaker.playWAV(
            wav_path,
            rate=WAV_RATE,
            data_format=speaker.F16B,
            channel=speaker.CHN_R,
            volume=PLAY_VOLUME,
        )
    except Exception as e:
        print("playWAV error:", e)
        return False, str(e)[:50]

    # Block while the async DMA drains. Use wait_ms (uiflow) to match the
    # working player script exactly.
    try:
        wait_ms(int(est_secs * 1000) + 500)
    except Exception:
        time.sleep(est_secs + 0.5)
    return True, "playWAV"

# -------------------------------------------------------------------
# TTS only test
# -------------------------------------------------------------------
def test_tts_only():
    global _test_idx
    text = TEST_TEXTS[_test_idx % len(TEST_TEXTS)]
    _test_idx += 1
    show("TTS [" + str(_test_idx) + "]", text[:38], "Requesting audio")
    ok, result = fetch_tts_wav(text)
    if not ok:
        show("Fetch failed", str(result)[:35], "")
        time.sleep(3)
        show_idle()
        return

    ok2, info = play_wav_file(result)
    if ok2:
        show("Playback OK", text[:38], str(info)[:35])
    else:
        show("Playback failed", str(info)[:35], "")
    time.sleep(3)
    show_idle()

# -------------------------------------------------------------------
# Microphone — record audio from M5Stack Core2 built-in PDM mic to a WAV
# file via MicrophonePDM. MIC.recordStart is asynchronous: it returns
# immediately and writes audio in the background, so we sleep for the
# recording duration plus a small margin before flushing/closing.
# Confirmed working signature on UIFlow1:
#     MIC.begin(pin_ws=0, pin_data=34, sample_rate_hz=16000,
#               buffer_length_ms=5000, block_length_ms=100)
#     MIC.recordStart(file_handle, duration_ms)
# CRITICAL: the PDM mic and the speaker share I2S0. We must init the mic
# right before recording and release it right after, otherwise the next
# speaker.playWAV crashes the device when the DMA completes.
# -------------------------------------------------------------------
def _init_mic():
    """Best-effort MIC.begin. Safe to call multiple times — if begin raises
    because the peripheral is already bound, we ignore it and proceed."""
    try:
        MIC.begin(pin_ws=MIC_WS_PIN, pin_data=MIC_DATA_PIN,
                  sample_rate_hz=RECORD_RATE,
                  buffer_length_ms=MIC_BUF_MS,
                  block_length_ms=MIC_BLOCK_MS)
        print("MIC.begin OK")
    except Exception as e:
        print("MIC.begin warn:", e)

def _release_mic():
    """Release the I2S peripheral so speaker.playWAV can claim it. UIFlow1's
    MicrophonePDM exposes the teardown under different names across builds, so
    we probe for any of them."""
    for name in ("recordStop", "end", "deinit", "stop"):
        fn = getattr(MIC, name, None)
        if fn is None:
            continue
        try:
            fn()
            print("MIC." + name + "() OK")
        except Exception as e:
            print("MIC." + name + " warn:", e)
    # Small settle delay so the I2S driver finishes tearing down DMA before
    # the speaker tries to bring it back up.
    time.sleep(0.2)

def record_question():
    show("Listening", "Speak now (" + str(RECORD_SECONDS) + "s)", RECORD_PATH)

    # Wipe any previous recording so a failed write can't masquerade as success.
    try:
        uos.remove(RECORD_PATH)
    except Exception:
        pass

    _init_mic()

    f = None
    try:
        f = open(RECORD_PATH, "wb")
        MIC.recordStart(f, RECORD_SECONDS * 1000)
        # Wait through the async record + small margin for buffer drain.
        time.sleep(RECORD_SECONDS + 1)
        try:
            f.flush()
        except Exception:
            pass
        f.close()
        f = None

        try:
            size = uos.stat(RECORD_PATH)[6]
        except Exception:
            size = 0
        if size <= 44:
            _release_mic()
            return False, "tiny file ({0} B)".format(size), size
        _release_mic()
        return True, "MicrophonePDM", size

    except Exception as e:
        if f is not None:
            try:
                f.close()
            except Exception:
                pass
        _release_mic()
        print("record fail:", e)
        return False, str(e)[:60], 0

# -------------------------------------------------------------------
# Send the recorded WAV to the backend's /speech/stt endpoint and get
# the transcribed text back. Body is a base64-encoded WAV in JSON.
# -------------------------------------------------------------------
def transcribe_wav(wav_path):
    try:
        size = uos.stat(wav_path)[6]
    except Exception:
        return False, "no recording on disk"
    if size == 0:
        return False, "0-byte recording"

    show("Transcribing", "size " + str(size), "uploading")

    try:
        with open(wav_path, "rb") as f:
            wav_bytes = f.read()
        # b2a_base64 appends a trailing newline; strip it before JSON-wrapping.
        b64 = ubinascii.b2a_base64(wav_bytes).decode("utf-8").rstrip("\n")
        # Free the raw bytes ASAP — peak memory matters more than total.
        del wav_bytes
        gc.collect()

        body = ujson.dumps({
            "device_id": DEVICE_ID,
            "audio_b64": b64,
            "format":    "wav",
        }).encode("utf-8")
        del b64
        gc.collect()

        r = urequests.post(
            BACKEND_URL + "/api/v1/speech/stt",
            data=body, headers=_auth_headers(),
        )
        del body
        gc.collect()

        print("STT status:", r.status_code)
        if r.status_code != 200:
            try: err = r.text
            except: err = "no body"
            print("STT err body:", err)
            r.close()
            return False, "HTTP {0}: {1}".format(r.status_code, str(err)[:50])

        data = r.json()
        r.close()
        # Backend returns {"success": True, "data": {... transcript or text ...}}
        d = data.get("data", {}) if isinstance(data, dict) else {}
        text = (d.get("transcript")
                or d.get("text")
                or d.get("transcription")
                or "")
        return True, text

    except Exception as e:
        print("STT error:", e)
        return False, str(e)[:60]

# -------------------------------------------------------------------
# Record + STT only — exercises the mic and /speech/stt endpoint without
# the ask/TTS/playback stages. We do NOT play the recording back; the
# whole point is to verify we can turn speech into text.
# -------------------------------------------------------------------
def test_record_stt():
    ok, info, size = record_question()
    if not ok:
        show("Record failed", str(info)[:35], "")
        time.sleep(3); show_idle(); return
    show("Recorded", info[:35], "size " + str(size))
    time.sleep(1)

    ok, text = transcribe_wav(RECORD_PATH)
    if not ok:
        show("STT failed", str(text)[:35], "")
        time.sleep(4); show_idle(); return
    if not text:
        show("STT empty", "no transcription", "try louder/closer")
        time.sleep(4); show_idle(); return
    print("STT text:", text)
    show("You said", text[:38], "")
    time.sleep(5)
    show_idle()

# -------------------------------------------------------------------
# Voice ASK — the real loop the spec asks for:
#   record mic → /speech/stt → /speech/ask → /speech/tts → playWAV
# Each step shows a status on the LCD so we can pinpoint where it fails.
# -------------------------------------------------------------------
def test_voice_ask():
    # 1. Record
    ok, info, size = record_question()
    if not ok:
        show("Record failed", str(info)[:35], "")
        time.sleep(3); show_idle(); return
    show("Recorded", info[:35], "size " + str(size))
    time.sleep(1)

    # 2. STT
    ok, text = transcribe_wav(RECORD_PATH)
    if not ok:
        show("STT failed", str(text)[:35], "")
        time.sleep(4); show_idle(); return
    if not text:
        show("STT empty", "no transcription", "try louder/closer")
        time.sleep(4); show_idle(); return
    print("STT text:", text)
    show("You said", text[:38], "asking backend...")
    time.sleep(2)

    # 3. ASK
    try:
        body = ujson.dumps({
            "device_id": DEVICE_ID,
            "question":  text,
        }).encode("utf-8")
        r = urequests.post(
            BACKEND_URL + "/api/v1/speech/ask",
            data=body, headers=_auth_headers(),
        )
        if r.status_code != 200:
            try: err = r.text
            except: err = ""
            r.close()
            show("ASK failed", "HTTP " + str(r.status_code), str(err)[:35])
            time.sleep(4); show_idle(); return
        data = r.json(); r.close()
        answer = data.get("data", {}).get("answer", "")
        intent = data.get("data", {}).get("intent", "")
    except Exception as e:
        show("ASK error", str(e)[:35], ""); time.sleep(3); show_idle(); return

    if not answer:
        show("No answer", intent[:35], ""); time.sleep(3); show_idle(); return
    print("ASK intent:", intent, "answer:", answer)
    show("Answer", answer[:38], intent[:35])
    time.sleep(2)

    # 4. TTS + 5. play
    ok, result = fetch_tts_wav(answer)
    if not ok:
        show("TTS failed", str(result)[:35], "")
        time.sleep(3); show_idle(); return
    ok2, play_info = play_wav_file(result)
    if ok2:
        show("Voice loop OK", play_info[:35], answer[:35])
    else:
        show("Play failed", str(play_info)[:35], "")
    time.sleep(3)
    show_idle()

# -------------------------------------------------------------------
# ASK then TTS  (typed-text fallback — kept available but not bound)
# Useful when the mic / STT path is broken; rebind btnC to this in the
# Main section below to test the answer pipeline without speaking.
# -------------------------------------------------------------------
def test_ask_then_tts():
    global _ask_idx
    question = ASK_QUESTIONS[_ask_idx % len(ASK_QUESTIONS)]
    _ask_idx += 1
    show("ASK [" + str(_ask_idx) + "]", question[:38], "")

    try:
        body = ujson.dumps({
            "device_id": DEVICE_ID,
            "question":  question,
        }).encode("utf-8")

        r = urequests.post(
            BACKEND_URL + "/api/v1/speech/ask",
            data=body, headers=_auth_headers(),
        )
        print("ASK status:", r.status_code)

        if r.status_code != 200:
            try: err = r.text
            except: err = "no text"
            print("ASK err body:", err)
            r.close()
            show("ASK failed", "HTTP " + str(r.status_code), "")
            time.sleep(3)
            show_idle()
            return

        data = r.json()
        r.close()
        answer = data.get("data", {}).get("answer", "")
        intent = data.get("data", {}).get("intent", "")
        print("ASK intent:", intent)
        print("ASK answer:", answer)
        show("ASK OK", intent[:28], answer[:28])
        time.sleep(2)

        if not answer:
            show("No answer text", "", "")
            time.sleep(2)
            show_idle()
            return

        ok, result = fetch_tts_wav(answer)
        if not ok:
            show("Fetch failed", str(result)[:35], "")
            time.sleep(3)
            show_idle()
            return

        ok2, info = play_wav_file(result)
        if ok2:
            show("ASK plus TTS OK", str(info)[:35], "")
        else:
            show("Playback failed", str(info)[:35], "")

    except Exception as e:
        print("ASK test error:", e)
        show("ASK error", str(e)[:35], "")
    time.sleep(3)
    show_idle()

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
_sd_ok = mount_sd()
show("SD: " + ("mounted /sd" if _sd_ok else "not mounted"),
     "WAV will use " + ("/sd" if _sd_ok else "/flash"), "")
time.sleep(1)

# Mic is NOT initialised at boot. record_question() calls _init_mic() right
# before recording and _release_mic() right after, because the PDM mic and
# speaker share I2S0 — leaving the mic active across a playWAV crashes the
# device when the speaker DMA completes.

if ensure_wifi():
    show_idle()
else:
    show("No WiFi", "Fix config first", "")

btnA.wasPressed(_guard(test_record_stt))
btnB.wasPressed(_guard(test_tts_only))
btnC.wasPressed(_guard(test_voice_ask))

while True:
    time.sleep(1)
