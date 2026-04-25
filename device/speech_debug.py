# -------------------------------------------------------------------
# speech_debug.py
# Step by step debug version for Core2 speech
# Tests:
# 1. WiFi
# 2. ASK endpoint
# 3. TTS endpoint (WAV)
# 4. WAV save to /sd/
# 5. speaker.playWAV playback
#
# Buttons:
# A = test tone only
# B = test TTS only
# C = test ASK then TTS
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

# Backend ?profile=m5stack converts the OpenAI WAV to 16 kHz / 8-bit unsigned / mono,
# which is the only format M5Stack Core2 UIFlow `speaker.playWAV` decodes reliably.
WAV_RATE = 16000
WAV_BITS = 8

# speaker.playWAV usually wants SD on this firmware (same path that works in main_project.m5f).
# If SD isn't mounted, fall back to /flash so we can at least find out whether playWAV
# accepts flash on this build.
WAV_PATHS = ("/sd/answer.wav", "/flash/answer.wav")

# -------------------------------------------------------------------
# UI helpers
# -------------------------------------------------------------------
setScreenColor(0x111111)

def show(line1="", line2="", line3="", c1=0xFFFFFF, c2=0x00FFCC, c3=0xAAAAAA):
    lcd.clear()
    lcd.setCursor(5, 10)
    lcd.setColor(c1)
    lcd.print(line1[:38])

    if line2:
        lcd.setCursor(5, 45)
        lcd.setColor(c2)
        lcd.print(line2[:38])

    if line3:
        lcd.setCursor(5, 80)
        lcd.setColor(c3)
        lcd.print(line3[:38])

def show_idle():
    show(
        "Speech Debug",
        "A tone   B tts   C ask",
        "Check serial too"
    )

def _auth_headers():
    return {
        "Authorization": "Bearer " + DEVICE_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

# -------------------------------------------------------------------
# WiFi
# -------------------------------------------------------------------
def ensure_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        show("WiFi already OK", ip)
        time.sleep(2)
        return True

    show("Connecting WiFi", WIFI_SSID, "Please wait")
    wlan.connect(WIFI_SSID, WIFI_PASS)

    for _ in range(20):
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            show("WiFi connected", ip)
            time.sleep(2)
            return True
        time.sleep(0.5)

    show("WiFi failed", "Check SSID/password", "")
    time.sleep(3)
    return False

# -------------------------------------------------------------------
# Tone test — also wakes the AXP-controlled amp before WAV playback.
# -------------------------------------------------------------------
def _wake_amp():
    try:
        speaker.setVolume(100)
    except:
        pass
    try:
        speaker.playTone(440, 1)
    except:
        pass

def test_tone():
    show("Tone test", "Playing 3 beeps", "")
    try:
        _wake_amp()
        for _ in range(3):
            speaker.playTone(440, 400)
            time.sleep(0.6)
        show("Tone OK", "If you heard beeps", "")
    except Exception as e:
        show("Tone error", str(e)[:35], "")
    time.sleep(2)
    show_idle()

# -------------------------------------------------------------------
# Fetch WAV — backend returns 24 kHz / 16-bit / mono RIFF/WAVE.
# Tries each candidate path in WAV_PATHS until one accepts the write.
# -------------------------------------------------------------------
def fetch_tts_wav(text):
    try:
        body = ujson.dumps({
            "device_id": DEVICE_ID,
            "text": text,
            "format": "wav"
        }).encode("utf-8")

        url = BACKEND_URL + "/api/v1/speech/tts?raw=1&profile=m5stack"
        r = urequests.post(url, data=body, headers=_auth_headers())

        show("TTS HTTP", str(r.status_code), "Downloading")
        print("TTS status:", r.status_code)

        if r.status_code != 200:
            try:
                err = r.text
            except:
                err = "No error text"
            print("TTS error body:", err)
            r.close()
            return False, "HTTP " + str(r.status_code)

        try:
            content = r.content
        except Exception as e:
            print("No r.content:", e)
            r.close()
            return False, "No binary content"
        r.close()

        last_err = "no path tried"
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
                print("WAV write failed at", candidate, "->", e)

        return False, last_err

    except Exception as e:
        print("fetch_tts_wav error:", e)
        return False, str(e)

# -------------------------------------------------------------------
# Playback — `rate=` is the only kwarg this firmware's playWAV accepts.
# File is already 16 kHz / 8-bit unsigned / mono thanks to ?profile=m5stack.
# -------------------------------------------------------------------
def play_wav_file(wav_path):
    _wake_amp()
    try:
        show("Playing WAV", wav_path, "16k 8b mono")
        speaker.playWAV(wav_path, rate=WAV_RATE)
        return True, "playWAV"
    except Exception as e:
        print("play_wav_file error:", e)
        return False, str(e)

# -------------------------------------------------------------------
# TTS only test
# -------------------------------------------------------------------
def test_tts_only():
    show("TTS test", "Requesting audio", "")
    ok, result = fetch_tts_wav(TEST_TEXT)

    if not ok:
        show("TTS fetch failed", str(result)[:35], "")
        time.sleep(3)
        show_idle()
        return

    ok2, result2 = play_wav_file(result)

    if ok2:
        show("Playback OK", str(result2)[:35], "")
    else:
        show("Playback failed", str(result2)[:35], "")
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
            "question": question
        }).encode("utf-8")

        r = urequests.post(
            BACKEND_URL + "/api/v1/speech/ask",
            data=body,
            headers=_auth_headers()
        )

        print("ASK status:", r.status_code)

        if r.status_code != 200:
            try:
                err = r.text
            except:
                err = "No error text"
            print("ASK error body:", err)
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
            show("TTS fetch failed", str(result)[:35], "")
            time.sleep(3)
            show_idle()
            return

        ok2, result2 = play_wav_file(result)
        if ok2:
            show("ASK plus TTS OK", str(result2)[:35], "")
        else:
            show("Playback failed", str(result2)[:35], "")

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

btnA.wasPressed(test_tone)
btnB.wasPressed(test_tts_only)
btnC.wasPressed(test_ask_then_tts)

while True:
    time.sleep(1)
