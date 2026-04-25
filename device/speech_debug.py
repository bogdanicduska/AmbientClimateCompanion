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

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------
WIFI_SSID = "LopezLed"
WIFI_PASS = "Chuma12345"

BACKEND_URL = "https://ambient-climate-backend-977755576323.europe-west6.run.app"
DEVICE_AUTH_TOKEN = "weather2026"
DEVICE_ID = "m5stack-ana-home"

TEST_TEXT = "Hello. This is a speech test from your room assistant."

# Backend ?profile=m5stack returns 44.1 kHz / 16-bit signed / mono — the same
# format that worked for /sd/test.wav in main_project.m5f.
WAV_RATE = 44100
WAV_BITS = 16

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
# Tone test — known-good baseline. 3 short beeps, ~3 seconds total.
# -------------------------------------------------------------------
def test_tone():
    show("Tone test", "3 short beeps", "")
    try:
        try:
            speaker.setVolume(100)
        except:
            pass
        for _ in range(3):
            speaker.playTone(440, 400)
            time.sleep(0.6)
        show("Tone OK", "If you heard 3 beeps", "")
    except Exception as e:
        show("Tone error", str(e)[:35], "")
    time.sleep(2)
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
                print("WAV saved:", candidate, "size:", size)
                show("WAV saved", candidate, "size " + str(size))
                gc.collect()
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
# Playback — try several speaker.playWAV signatures. The first one that
# raises a non-TypeError (or raises nothing) is what this firmware accepts.
# -------------------------------------------------------------------
def play_wav_file(wav_path):
    try:
        speaker.setVolume(100)
    except:
        pass

    variants = (
        ("path-only",  lambda p: speaker.playWAV(p)),
        ("rate-kw",    lambda p: speaker.playWAV(p, rate=WAV_RATE)),
        ("positional", lambda p: speaker.playWAV(p, WAV_RATE, WAV_BITS)),
    )
    last_err = "no variant tried"
    for label, fn in variants:
        try:
            show("Playing WAV", label, wav_path)
            print("playWAV variant:", label)
            fn(wav_path)
            return True, label
        except TypeError as e:
            last_err = "{0} TypeError: {1}".format(label, e)
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
if ensure_wifi():
    show_idle()
else:
    show("No WiFi", "Fix config first", "")

btnA.wasPressed(_guard(test_tone))
btnB.wasPressed(_guard(test_tts_only))
btnC.wasPressed(_guard(test_ask_then_tts))

while True:
    time.sleep(1)
