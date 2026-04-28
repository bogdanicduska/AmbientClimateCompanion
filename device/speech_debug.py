# -------------------------------------------------------------------
# speech_debug.py
# Step by step debug version for Core2 speech.
#
# Buttons (each handler is re-entry guarded):
#   A = 3 short tones (verifies firmware speaker)
#   B = TTS only — fetch WAV from backend, play via speaker.playWAV
#   C = ASK then TTS — full pipeline
#
# Notes:
# - We do NOT import machine.I2S at module load on this firmware. Doing so
#   locks the I2S peripheral and speaker.playTone hangs.
# - WAV files are 44.1 kHz / 16-bit / mono — same shape as the working
#   /sd/test.wav in main_project.m5f. Saved to /sd/ if mounted, else /flash.
# -------------------------------------------------------------------

from m5stack import lcd, btnA, btnB, btnC, speaker
from m5ui import *
from uiflow import *
import network
import urequests
import ujson
import time
import gc
import uos

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

TEST_TEXT = "Hello. This is a speech test from your room assistant."

# Backend ?profile=m5stack returns 16 kHz / 8-bit *unsigned* / mono. That is
# the only PCM shape this UIFlow1 build's speaker.playWAV decodes reliably
# (44.1 kHz / 16-bit downloads fine but plays silent — confirmed on device).
# The fmt chunk we read off /sd/answer.wav after download must show
# "PCM 16000Hz 8b ch1" for playback to work.
WAV_RATE = 16000
WAV_BITS = 8

WAV_PATHS = ("/sd/answer.wav", "/flash/answer.wav")

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
# Playback — try several speaker.playWAV signatures. The first one that
# raises a non-TypeError (or raises nothing) is what this firmware accepts.
#
# IMPORTANT: speaker.playWAV is asynchronous on UIFlow1. It returns
# immediately after queuing; "no exception" does NOT mean it played sound.
# We pre-beep first to prove the audio chain is alive, and we sleep after
# play so the next button press doesn't cut the buffer.
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

def play_wav_file(wav_path):
    _log_speaker_methods()
    try:
        # 0..11 scale on UIFlow1. 6 is comfortable; 100 silently clips to silence.
        speaker.setVolume(6)
    except:
        pass

    # Pre-beep — if you hear this but not the WAV, the WAV format / playWAV
    # signature is the issue. If you hear NEITHER, volume / speaker init is.
    try:
        speaker.playTone(880, 150)
        time.sleep(0.25)
    except Exception as e:
        print("pre-beep failed:", e)

    # Estimate WAV duration so we can sleep through async playback.
    try:
        wav_size = uos.stat(wav_path)[6]
    except Exception:
        wav_size = 0
    bytes_per_sec = WAV_RATE * (WAV_BITS // 8)  # mono
    est_secs = max(1.0, (wav_size - 44) / float(bytes_per_sec)) if wav_size else 3.0
    if est_secs > 30:
        est_secs = 30  # safety cap

    variants = (
        ("playWAV-path",    lambda p: speaker.playWAV(p)),
        ("playWav-path",    lambda p: speaker.playWav(p)),
        ("playWavFile",     lambda p: speaker.playWavFile(p)),
        ("play_wav-path",   lambda p: speaker.play_wav(p)),
        ("playWAV-rate-kw", lambda p: speaker.playWAV(p, rate=WAV_RATE)),
        ("playWAV-pos",     lambda p: speaker.playWAV(p, WAV_RATE, WAV_BITS)),
    )
    last_err = "no variant tried"
    for label, fn in variants:
        try:
            show("Playing WAV", label, wav_path)
            print("playWAV variant:", label, "est_secs:", est_secs)
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
            print("playWAV non-TypeError:", e)
            return False, "{0}: {1}".format(label, e)
    return False, last_err

# -------------------------------------------------------------------
# TTS only test
# -------------------------------------------------------------------
def test_tts_only():
    show("TTS test", "Requesting audio", "")
    ok, result = fetch_tts_wav(TEST_TEXT)
    if not ok:
        show("Fetch failed", str(result)[:35], "")
        time.sleep(3)
        show_idle()
        return

    ok2, info = play_wav_file(result)
    if ok2:
        show("Playback OK", str(info)[:35], "")
    else:
        show("Playback failed", str(info)[:35], "")
    time.sleep(3)
    show_idle()

# -------------------------------------------------------------------
# ASK then TTS
# -------------------------------------------------------------------
def test_ask_then_tts():
    question = "How is the air quality right now?"
    show("ASK test", question[:24], "")

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

if ensure_wifi():
    show_idle()
else:
    show("No WiFi", "Fix config first", "")

btnA.wasPressed(_guard(test_tone))
btnB.wasPressed(_guard(test_tts_only))
btnC.wasPressed(_guard(test_ask_then_tts))

while True:
    time.sleep(1)
