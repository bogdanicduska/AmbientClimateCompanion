# -------------------------------------------------------------------
# speech_demo.py  —  M5Stack Core2 voice demo for Ambient Climate
# -------------------------------------------------------------------
#
# HOW TO USE
#   Option 1 (UIFlow1): open this file in UIFlow1's "Python" tab,
#                       set BACKEND_URL + DEVICE_AUTH_TOKEN, run.
#   Option 2 (mpremote): mpremote cp speech_demo.py :main.py && mpremote reset
#
# WHAT IT DOES
#   Button A  -> "What is the room readiness right now?"
#   Button B  -> "How is the air quality right now?"
#   Button C  -> "Did humidity exceed 50 percent in the last 24 hours?"
#
# Each press:
#   1. GET text answer from  /api/v1/speech/ask
#   2. Display answer on the LCD
#   3. GET WAV audio from    /api/v1/speech/tts?raw=1   (binary, no base64)
#   4. Save to /flash/answer.wav
#   5. Play it through the speaker
# -------------------------------------------------------------------

from m5stack import lcd, btnA, btnB, btnC, speaker
import network
import urequests
import time
import gc

# ---------- CONFIG ----------
BACKEND_URL = "http://192.168.1.100:8080"   # <-- replace with your backend address
DEVICE_AUTH_TOKEN = "changeme"              # <-- must match backend DEVICE_AUTH_TOKEN
DEVICE_ID = "m5stack-ana-home"

WIFI_SSID = "your-wifi"                     # <-- or reuse /flash/last_wifi.txt from main project
WIFI_PASS = "your-wifi-password"

QUESTIONS = {
    "A": "What is the room readiness right now?",
    "B": "How is the air quality right now?",
    "C": "Did humidity exceed 50 percent in the last 24 hours?",
}

# ---------- UI HELPERS ----------
def show(line1, line2=""):
    lcd.clear()
    lcd.setCursor(5, 10)
    lcd.setColor(lcd.WHITE)
    lcd.print(line1[:40])
    if line2:
        lcd.setCursor(5, 40)
        lcd.setColor(lcd.CYAN)
        # Wrap long answer text across multiple lines (every ~28 chars)
        y = 40
        for i in range(0, len(line2), 28):
            lcd.setCursor(5, y)
            lcd.print(line2[i:i+28])
            y += 20
            if y > 200:
                break

def show_idle():
    show("Ambient Climate — Voice")
    lcd.setCursor(5, 50)
    lcd.setColor(lcd.YELLOW)
    lcd.print("A: Readiness")
    lcd.setCursor(5, 80)
    lcd.print("B: Air quality")
    lcd.setCursor(5, 110)
    lcd.print("C: Humidity 50%")

# ---------- NETWORK ----------
def ensure_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    show("Connecting WiFi...")
    wlan.connect(WIFI_SSID, WIFI_PASS)
    for _ in range(30):
        if wlan.isconnected():
            return True
        time.sleep(0.5)
    show("WiFi FAILED")
    return False

# ---------- CORE FLOW ----------
def ask_and_play(question):
    try:
        show("Thinking...", question)
        gc.collect()

        # 1. Text answer
        r = urequests.post(
            BACKEND_URL + "/api/v1/speech/ask",
            json={"device_id": DEVICE_ID, "question": question},
            headers={"Authorization": "Bearer " + DEVICE_AUTH_TOKEN,
                     "Content-Type":  "application/json"},
        )
        if r.status_code != 200:
            show("Ask failed", "HTTP " + str(r.status_code))
            r.close()
            return
        data = r.json().get("data", {})
        answer = data.get("answer", "")
        intent = data.get("intent", "")
        r.close()
        gc.collect()

        show("Answer (" + intent + ")", answer)

        # 2. TTS as raw WAV bytes  (raw=1 → no base64, no JSON, straight audio)
        r = urequests.post(
            BACKEND_URL + "/api/v1/speech/tts?raw=1",
            json={"device_id": DEVICE_ID, "text": answer, "format": "wav"},
            headers={"Authorization": "Bearer " + DEVICE_AUTH_TOKEN,
                     "Content-Type":  "application/json"},
        )
        if r.status_code != 200:
            show("TTS failed", "HTTP " + str(r.status_code))
            r.close()
            return

        # 3. Save to flash (stream bytes to avoid large in-memory buffers)
        with open("/flash/answer.wav", "wb") as f:
            f.write(r.content)
        r.close()
        gc.collect()

        # 4. Play it
        try:
            speaker.playWAV("/flash/answer.wav")
        except Exception as exc:
            # Fallback name on some firmware variants
            try:
                speaker.playWav("/flash/answer.wav")
            except Exception:
                show("Playback error", str(exc)[:60])
                return

    except Exception as exc:
        show("Error", str(exc)[:80])
        time.sleep(3)
    finally:
        time.sleep(1)
        show_idle()

# ---------- BUTTON BINDINGS ----------
def on_a():
    ask_and_play(QUESTIONS["A"])
def on_b():
    ask_and_play(QUESTIONS["B"])
def on_c():
    ask_and_play(QUESTIONS["C"])

btnA.wasPressed(on_a)
btnB.wasPressed(on_b)
btnC.wasPressed(on_c)

# ---------- BOOT ----------
if ensure_wifi():
    show_idle()
else:
    show("Check WiFi creds")

while True:
    time.sleep(1)
