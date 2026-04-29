# -------------------------------------------------------------------
# speech_debug.py
# Step by step debug version for Core2 speech.
#
# Buttons (each handler is re-entry guarded):
#   A = 2 short tones (verifies firmware speaker)
#   B = TTS only — cycles through TEST_TEXTS, plays each via speaker.playWAV
#   C = Voice ASK — record mic → /speech/stt → /speech/ask → /speech/tts → play
#       (the real voice loop the project spec asks for)
#
# Fallback: test_ask_then_tts() exists in this file but is unbound. To test
# the answer pipeline with TYPED text instead of voice, switch the btnC.wasPressed
# binding at the bottom of this file from test_voice_ask to test_ask_then_tts.
#
# Notes:
# - We do NOT import machine.I2S at module load on this firmware. Doing so
#   locks the I2S peripheral and speaker.playTone hangs.
# - WAV files are 44.1 kHz / 16-bit / mono — same shape as the working
#   /sd/test.wav in main_project.m5f. Saved to /sd/ if mounted, else /flash.
# -------------------------------------------------------------------

from m5stack import lcd, btnA, btnB, btnC, speaker, mic
from m5ui import *
from uiflow import *
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
# valid". 16 kHz keeps a 3 s clip ~100 KB which playRaw / playWAV can load.
# The fmt chunk read off /sd/answer.wav after download MUST show
# "PCM 16000Hz 16b ch1" for playback to work.
WAV_RATE = 16000
WAV_BITS = 16

WAV_PATHS = ("/sd/answer.wav", "/flash/answer.wav")

# Microphone recording config — kept SHORT because the mic.record2file output
# becomes a base64 JSON body that urequests buffers in RAM. ESP32 heap on this
# firmware is around 110 KB, so we have to stay well under that.
#   2 s @ 16 kHz / 16-bit / mono = 64 KB raw → ~85 KB base64
# If we still OOM on upload, drop RECORD_RATE to 8000 (32 KB raw → 43 KB b64).
RECORD_PATH    = "/sd/question.wav"
RECORD_SECONDS = 2
RECORD_RATE    = 16000

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
    show("Speech Debug", "A tone   B tts   C ask", "")

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
# WAV inspector — read the saved file's RIFF/fmt chunk and return
# (is_riff_ok, "rate=44100 bits=16 ch=1 fmt=PCM size=277408"). If
# the firmware silently rejects the WAV, this tells us *exactly*
# what format the file actually has on disk vs what we expected.
# -------------------------------------------------------------------
def _inspect_wav(path):
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            if len(head) < 12 or head[0:4] != b"RIFF" or head[8:12] != b"WAVE":
                return False, "no RIFF/WAVE"
            # Walk chunks looking for "fmt ". Skip everything else.
            while True:
                chunk_hdr = f.read(8)
                if len(chunk_hdr) < 8:
                    return True, "no fmt chunk"
                cid = chunk_hdr[0:4]
                csize = (chunk_hdr[4] | (chunk_hdr[5] << 8)
                         | (chunk_hdr[6] << 16) | (chunk_hdr[7] << 24))
                body = f.read(csize)
                if cid == b"fmt ":
                    if len(body) < 16:
                        return True, "fmt too short"
                    fmt_code = body[0] | (body[1] << 8)
                    nchan    = body[2] | (body[3] << 8)
                    rate     = (body[4] | (body[5] << 8)
                                | (body[6] << 16) | (body[7] << 24))
                    bits     = body[14] | (body[15] << 8)
                    fmt_name = {1: "PCM", 3: "FLOAT", 0xFFFE: "EXT"}.get(fmt_code, str(fmt_code))
                    return True, "{0} {1}Hz {2}b ch{3}".format(fmt_name, rate, bits, nchan)
    except Exception as e:
        return False, "read err: " + str(e)[:25]

# -------------------------------------------------------------------
# Tone test — known-good baseline. 3 short beeps, then if /sd/test.wav
# exists, attempt to play it. main_project.m5f confirmed test.wav plays
# on this firmware — so if we hear it here, speaker.playWAV is fine and
# the TTS-WAV silence is a backend-format issue. If we don't, the issue
# is the playWAV call signature itself.
# -------------------------------------------------------------------
def test_tone():
    show("Tone test", "2 short beeps", "")
    try:
        try:
            speaker.setVolume(4)  # quieter — speaker vibration was retriggering capA
        except:
            pass
        # 2 brief tones, ~0.6s total. Keeps the handler short so the touch
        # button has less chance to self-trigger from speaker vibration.
        speaker.playTone(440, 120)
        time.sleep(0.18)
        speaker.playTone(660, 120)
        time.sleep(0.5)  # silent cooldown — settles capacitive touch noise
        show("Tone OK", "Heard 2 beeps?", "")
    except Exception as e:
        show("Tone error", str(e)[:35], "")
    time.sleep(1)
    show_idle()

# -------------------------------------------------------------------
# Fetch the WAV — backend ?profile=m5stack returns 44.1 kHz / 16-bit / mono.
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
                hdr_ok, fmt_info = _inspect_wav(candidate)
                print("WAV saved:", candidate, "size:", size,
                      "hdr_ok:", hdr_ok, "fmt:", fmt_info)
                if hdr_ok:
                    show("WAV saved",
                         "size " + str(size),
                         fmt_info)
                else:
                    show("WAV saved",
                         "BAD HDR " + str(size),
                         fmt_info)
                gc.collect()
                time.sleep(2)
                if not hdr_ok:
                    return False, "bad WAV header at " + candidate
                return True, candidate
            except Exception as e:
                last_err = "{0}: {1}".format(candidate, e)
                print("write failed:", last_err)
        return False, last_err

    except Exception as e:
        print("fetch_tts_wav error:", e)
        return False, str(e)

# -------------------------------------------------------------------
# Playback — uses speaker.playRaw with explicit format constants
# (F16B / CHN_L) which is the bypass-the-WAV-parser API exposed by this
# firmware. We strip the RIFF header to get raw PCM bytes and hand them
# directly to playRaw. playWAV is kept as a final fallback.
#
# IMPORTANT: playRaw / playWAV are asynchronous. We sleep through the
# estimated clip duration so the next press doesn't cut the buffer.
# -------------------------------------------------------------------
_speaker_dir_logged = False

def _log_speaker_methods():
    global _speaker_dir_logged
    if _speaker_dir_logged:
        return
    _speaker_dir_logged = True
    try:
        attrs = [a for a in dir(speaker) if not a.startswith("_")]
        print("speaker dir:", attrs)
    except Exception as e:
        print("speaker dir failed:", e)

def _load_pcm_from_wav(path):
    """Walk RIFF chunks and return the raw PCM bytes from the data chunk
    (and total bytes). Without this, OpenAI WAVs sometimes carry a LIST/INFO
    chunk before data, so a naive "skip 44 bytes" assumption misaligns audio."""
    with open(path, "rb") as f:
        head = f.read(12)
        if len(head) < 12 or head[0:4] != b"RIFF" or head[8:12] != b"WAVE":
            return None
        while True:
            chunk_hdr = f.read(8)
            if len(chunk_hdr) < 8:
                return None
            cid = chunk_hdr[0:4]
            csize = (chunk_hdr[4] | (chunk_hdr[5] << 8)
                     | (chunk_hdr[6] << 16) | (chunk_hdr[7] << 24))
            if cid == b"data":
                return f.read(csize)
            f.read(csize)  # skip non-data chunk

# Volume range on this firmware — empirically 0..11 for setVolume, 0..6 for the
# inline `volume=` kwarg on playWAV. Keep these in one place for easy tweaking.
PLAY_VOLUME = 6

def play_wav_file(wav_path):
    _log_speaker_methods()

    # Estimate WAV duration so we can sleep through async playback.
    try:
        wav_size = uos.stat(wav_path)[6]
    except Exception:
        wav_size = 0
    bytes_per_sec = WAV_RATE * (WAV_BITS // 8)  # mono
    est_secs = max(1.0, (wav_size - 44) / float(bytes_per_sec)) if wav_size else 3.0
    if est_secs > 30:
        est_secs = 30  # safety cap

    # Format constants exposed by the speaker module on UIFlow1 firmware.
    # IMPORTANT: kwarg names are `data_format=` and `channel=` (singular) —
    # NOT `bits=` / `channels=`. Wrong kwargs raise TypeError silently.
    F16B  = getattr(speaker, "F16B",  16)
    CHN_R = getattr(speaker, "CHN_R", 1)
    CHN_L = getattr(speaker, "CHN_L", 0)

    # Pre-load raw PCM bytes once so playRaw fallbacks use the same buffer.
    pcm = _load_pcm_from_wav(wav_path)
    pcm_len = len(pcm) if pcm else 0
    print("PCM extracted:", pcm_len, "bytes")

    # KNOWN-WORKING signature on M5Stack Core2 UIFlow1 (confirmed on device):
    #     speaker.playWAV(path, rate=16000, data_format=speaker.F16B,
    #                     channel=speaker.CHN_R, volume=6)
    # Order: try the working signature first, then a left-channel variant,
    # then progressively simpler fallbacks if firmware ever changes.
    variants = [
        ("playWAV-good-R",  lambda p: speaker.playWAV(p, rate=WAV_RATE,
                                                       data_format=F16B,
                                                       channel=CHN_R,
                                                       volume=PLAY_VOLUME)),
        ("playWAV-good-L",  lambda p: speaker.playWAV(p, rate=WAV_RATE,
                                                       data_format=F16B,
                                                       channel=CHN_L,
                                                       volume=PLAY_VOLUME)),
        ("playWAV-rate-kw", lambda p: speaker.playWAV(p, rate=WAV_RATE)),
        ("playWAV-path",    lambda p: speaker.playWAV(p)),
    ]
    if pcm:
        variants.append(
            ("playRaw-good-R", lambda p: speaker.playRaw(pcm, rate=WAV_RATE,
                                                          data_format=F16B,
                                                          channel=CHN_R,
                                                          volume=PLAY_VOLUME)),
        )

    last_err = "no variant tried"
    for label, fn in variants:
        try:
            show("Playing", label, wav_path)
            print("variant:", label, "est_secs:", est_secs)
            fn(wav_path)
            # Block while async playback drains.
            time.sleep(est_secs + 0.5)
            return True, label
        except TypeError as e:
            last_err = "{0} TypeError: {1}".format(label, e)
            print(last_err)
        except AttributeError as e:
            last_err = "{0} missing: {1}".format(label, e)
            print(last_err)
        except Exception as e:
            print("play non-TypeError:", e)
            last_err = "{0}: {1}".format(label, e)
            continue
    return False, last_err

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
# file on /sd. UIFlow1 exposes only `mic.record2file` on this firmware
# (we confirmed via dir(mic) probe). We don't know the exact kwarg names
# yet, so we try the common variants and lock the first one that works.
# -------------------------------------------------------------------
def record_question():
    show("Listening", "Speak now (" + str(RECORD_SECONDS) + "s)", RECORD_PATH)

    variants = [
        ("kw-second-rate",  lambda: mic.record2file(filename=RECORD_PATH,
                                                     second=RECORD_SECONDS,
                                                     rate=RECORD_RATE)),
        ("kw-seconds-rate", lambda: mic.record2file(filename=RECORD_PATH,
                                                     seconds=RECORD_SECONDS,
                                                     rate=RECORD_RATE)),
        ("pos-3arg",        lambda: mic.record2file(RECORD_PATH,
                                                     RECORD_SECONDS,
                                                     RECORD_RATE)),
        ("pos-2arg",        lambda: mic.record2file(RECORD_PATH,
                                                     RECORD_SECONDS)),
        ("kw-second",       lambda: mic.record2file(filename=RECORD_PATH,
                                                     second=RECORD_SECONDS)),
        ("pos-1arg",        lambda: mic.record2file(RECORD_PATH)),
    ]

    last_err = "no variant tried"
    for label, fn in variants:
        try:
            print("record variant:", label)
            fn()
            try:
                size = uos.stat(RECORD_PATH)[6]
            except Exception:
                size = 0
            return True, label, size
        except TypeError as e:
            last_err = "{0} TypeError: {1}".format(label, e)
            print(last_err)
        except Exception as e:
            print("record fail:", label, e)
            return False, "{0}: {1}".format(label, e), 0
    return False, last_err, 0

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
# Show every public method on the speaker module on the LCD. We need
# to know what's available (playWAV / playMp3 / playWavFile / etc.) to
# pick the right play API for this firmware build, but `print(dir())`
# only goes to the serial console — this dumps it to the screen so we
# can read it off the device.
# -------------------------------------------------------------------
def show_speaker_dir():
    try:
        attrs = [a for a in dir(speaker) if not a.startswith("_")]
    except Exception as e:
        attrs = ["err:" + str(e)[:30]]
    print("speaker dir:", attrs)
    blob = ",".join(attrs)
    lcd.clear()
    lcd.setCursor(5, 5);  lcd.setColor(0xFFFFFF); lcd.print("speaker methods:")
    y = 30
    # ~38 chars/line at default font.
    for i in range(0, len(blob), 38):
        lcd.setCursor(5, y); lcd.setColor(0x00FFCC); lcd.print(blob[i:i+38])
        y += 22
        if y > 220:
            break
    time.sleep(8)  # long enough to read or photograph

# -------------------------------------------------------------------
# Probe the firmware for a microphone API. UIFlow1 surfaces the Core2's
# built-in PDM mic under different names depending on the build —
# `microphone`, `mic`, `m5mic`, or attached to the `m5stack` module.
# We try each candidate, catch every exception, and dump whatever we
# find to the LCD so we can pick the correct record() signature without
# needing a serial console.
#
# We deliberately do NOT try `from machine import I2S` here — that would
# lock the speaker (per the existing comment at the top of this file).
# -------------------------------------------------------------------
def show_mic_dir():
    candidates = []  # list of (label, attrs_list)

    # Direct module imports
    for mod_name in ("microphone", "mic", "m5mic"):
        try:
            mod = __import__(mod_name)
            attrs = [a for a in dir(mod) if not a.startswith("_")]
            candidates.append((mod_name, attrs))
        except Exception as e:
            print("mic probe", mod_name, "import failed:", e)

    # Attributes hanging off m5stack (e.g. m5stack.mic)
    try:
        import m5stack as _m5
        for sub in ("mic", "microphone", "Mic", "Microphone"):
            obj = getattr(_m5, sub, None)
            if obj is not None:
                attrs = [a for a in dir(obj) if not a.startswith("_")]
                candidates.append(("m5stack." + sub, attrs))
    except Exception as e:
        print("mic probe m5stack.* failed:", e)

    print("mic candidates:", candidates)

    lcd.clear()
    lcd.setCursor(5, 5); lcd.setColor(0xFFFFFF); lcd.print("mic probe:")
    y = 28
    if not candidates:
        lcd.setCursor(5, y); lcd.setColor(0xFF6666)
        lcd.print("none found — no mic module")
        time.sleep(8)
        return

    for label, attrs in candidates:
        lcd.setCursor(5, y); lcd.setColor(0xFFFF66); lcd.print(label[:38])
        y += 18
        blob = ",".join(attrs) if attrs else "(empty)"
        for i in range(0, len(blob), 38):
            if y > 218:
                break
            lcd.setCursor(5, y); lcd.setColor(0x00FFCC); lcd.print(blob[i:i+38])
            y += 16
        y += 4
        if y > 218:
            break
    time.sleep(10)

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
_sd_ok = mount_sd()
show("SD: " + ("mounted /sd" if _sd_ok else "not mounted"),
     "WAV will use " + ("/sd" if _sd_ok else "/flash"), "")
time.sleep(1)

show_speaker_dir()
show_mic_dir()

if ensure_wifi():
    show_idle()
else:
    show("No WiFi", "Fix config first", "")

btnA.wasPressed(_guard(test_tone))
btnB.wasPressed(_guard(test_tts_only))
btnC.wasPressed(_guard(test_voice_ask))

while True:
    time.sleep(1)
