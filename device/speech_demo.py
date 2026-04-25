# -------------------------------------------------------------------
# speech_demo.py  —  M5Stack Core2 voice demo for Ambient Climate
# -------------------------------------------------------------------
#
# HOW TO USE
#   Option 1 (UIFlow1): open this file in UIFlow1's "Python" tab,
#                       set the 5 CONFIG values, press Run.
#   Option 2 (mpremote): mpremote cp speech_demo.py :main.py && mpremote reset
#
# BUTTONS
#   A  ->  "What is the room readiness right now?"
#   B  ->  "How is the air quality right now?"
#   C  ->  "Did humidity exceed 50 percent in the last 24 hours?"
#
# PROACTIVE BEHAVIOUR
#   The PIR sensor on PORTB detects motion. When presence is detected
#   the device asks the backend /speech/proactive — the backend decides
#   whether to speak. Cooldowns are enforced per trigger (e.g. weather
#   announcement once per hour, air strain alerts every 2h, etc).
# -------------------------------------------------------------------

from m5stack import lcd, btnA, btnB, btnC
import unit
import network
import urequests
import ujson
import time
import gc

# Speaker module — UIFlow1 exposes `speaker` from m5stack; UIFlow2 uses M5.Speaker
try:
    from m5stack import speaker as _spk
    SPEAKER_KIND = "uiflow1"
except ImportError:
    try:
        from M5 import Speaker as _spk
        SPEAKER_KIND = "uiflow2"
    except ImportError:
        _spk = None
        SPEAKER_KIND = "none"

# =====================================================================
# CONFIG — edit these 5 values for your setup
# =====================================================================
BACKEND_URL       = "https://ambient-climate-backend-977755576323.europe-west6.run.app"
DEVICE_AUTH_TOKEN = "weather2026"
DEVICE_ID         = "m5stack-ana-home"
WIFI_SSID         = "your-wifi"
WIFI_PASS         = "your-wifi-password"
# =====================================================================

QUESTIONS = {
    "A": "What is the room readiness right now?",
    "B": "How is the air quality right now?",
    "C": "Did humidity exceed 50 percent in the last 24 hours?",
}

# Motion-poll throttle — PIR fires fast; we only hit the backend this
# often at most. The backend has its own per-trigger cooldowns on top.
MOTION_COOLDOWN_S = 60

# Hardware
try:
    pir = unit.get(unit.PIR, unit.PORTB)
except Exception:
    pir = None

# State
_last_motion_handled = 0


# =====================================================================
# UI
# =====================================================================
def show(line1, line2=""):
    try:
        lcd.clear()
        lcd.setCursor(5, 10)
        lcd.setColor(lcd.WHITE)
        lcd.print(line1[:40])
        if line2:
            y = 40
            for i in range(0, len(line2), 28):
                lcd.setCursor(5, y)
                lcd.setColor(lcd.CYAN)
                lcd.print(line2[i:i+28])
                y += 22
                if y > 220:
                    break
    except Exception:
        pass


def show_idle():
    try:
        lcd.clear()
        lcd.setColor(lcd.WHITE)
        lcd.setCursor(5, 10)
        lcd.print("Ambient Climate Voice")
        lcd.setColor(lcd.YELLOW)
        lcd.setCursor(5, 50)
        lcd.print("A: Readiness")
        lcd.setCursor(5, 80)
        lcd.print("B: Air quality")
        lcd.setCursor(5, 110)
        lcd.print("C: Humidity")
        lcd.setColor(lcd.GREEN)
        lcd.setCursor(5, 170)
        lcd.print("Motion -> weather, etc")
    except Exception:
        pass


# =====================================================================
# HTTP — build the body manually. MicroPython urequests on UIFlow1 does
# NOT always honour the json= kwarg; we use data=bytes to be safe.
# =====================================================================
def _auth_headers():
    return {
        "Authorization": "Bearer " + DEVICE_AUTH_TOKEN,
        "Content-Type":  "application/json",
    }


def http_post(path, body_dict, raw_response=False):
    body = ujson.dumps(body_dict).encode("utf-8")
    url  = BACKEND_URL + path + ("?raw=1" if raw_response else "")
    return urequests.post(url, data=body, headers=_auth_headers())


def http_get(path):
    return urequests.get(BACKEND_URL + path, headers=_auth_headers())


# =====================================================================
# SPEAKER — robust across UIFlow1 / UIFlow2 variants
# =====================================================================
def _set_volume(level=6):
    if _spk is None:
        return
    for name in ("setVolume", "set_volume", "setVol"):
        fn = getattr(_spk, name, None)
        if fn:
            try:
                fn(level)
                return
            except Exception:
                pass


def _beep(freq=1000, ms=250):
    """Short diagnostic beep. If you hear it, the speaker chain is alive."""
    if _spk is None:
        return
    for name in ("tone", "playTone", "beep", "sing"):
        fn = getattr(_spk, name, None)
        if fn:
            try:
                fn(freq, ms)
                return
            except Exception:
                pass


def _speaker_attrs():
    """List available methods on the speaker module — shown on screen when play fails."""
    if _spk is None:
        return "no module"
    return ", ".join([a for a in dir(_spk) if not a.startswith("_")][:10])


def _call_speaker_play(path):
    if _spk is None:
        return False, None, "no speaker module"
    _set_volume(6)
    for name in ("playWAV", "playWav", "playWavFile", "play_wav", "playFile"):
        fn = getattr(_spk, name, None)
        if fn:
            try:
                fn(path)
                return True, name, None
            except Exception as exc:
                return False, name, str(exc)[:60]
    return False, None, "no play API. attrs: " + _speaker_attrs()


def play_spoken_text(text, wav_path="/flash/answer.wav"):
    if not text:
        return
    try:
        r = http_post("/api/v1/speech/tts",
                      {"device_id": DEVICE_ID, "text": text, "format": "wav"},
                      raw_response=True)
        if r.status_code != 200:
            err = r.text[:80]
            r.close()
            show("TTS " + str(r.status_code), err)
            time.sleep(3)
            return
        wav_bytes = r.content
        r.close()
        with open(wav_path, "wb") as f:
            f.write(wav_bytes)
        gc.collect()
        wav_size = len(wav_bytes)
    except Exception as exc:
        show("TTS error", str(exc)[:80])
        time.sleep(3)
        return

    # Pre-beep — if you hear this but not the speech, the WAV format is incompatible.
    _beep(800, 150)
    time.sleep(0.1)

    ok, api_used, err = _call_speaker_play(wav_path)
    if ok:
        show("Speaking [" + (api_used or "?") + "]",
             "WAV " + str(wav_size) + " B, kind=" + SPEAKER_KIND)
    else:
        show("Speaker FAIL", (err or "unknown") + " | kind=" + SPEAKER_KIND)
        time.sleep(5)


# =====================================================================
# ASK (button-triggered)
# =====================================================================
def ask_and_speak(question):
    show("Thinking...", question)
    gc.collect()
    try:
        r = http_post("/api/v1/speech/ask",
                      {"device_id": DEVICE_ID, "question": question})
        if r.status_code != 200:
            err = r.text[:120]
            r.close()
            show("ASK " + str(r.status_code), err)
            time.sleep(4)
            show_idle()
            return

        data   = r.json().get("data", {})
        answer = data.get("answer", "")
        intent = data.get("intent", "")
        r.close()
        gc.collect()

        show("[" + intent + "]", answer)
        play_spoken_text(answer)

    except Exception as exc:
        show("Error", str(exc)[:80])
        time.sleep(3)
    finally:
        time.sleep(1)
        show_idle()


# =====================================================================
# PROACTIVE (motion-triggered)
# =====================================================================
def handle_motion():
    """PIR fired — ask the backend if there's anything worth saying."""
    global _last_motion_handled
    now = time.time()
    if now - _last_motion_handled < MOTION_COOLDOWN_S:
        return  # throttle at device level too
    _last_motion_handled = now

    try:
        r = http_get("/api/v1/speech/proactive?device_id=" + DEVICE_ID)
        if r.status_code != 200:
            r.close()
            return
        data = r.json().get("data", {})
        r.close()

        if not data.get("announce"):
            return  # backend is in cooldown — stay quiet

        trigger = data.get("trigger_id", "")
        text    = data.get("text", "")
        show("[" + trigger + "]", text)
        play_spoken_text(text)

    except Exception:
        # Silent fail — proactive is a "nice to have", never block the UI
        pass
    finally:
        time.sleep(1)
        show_idle()


def poll_motion():
    if pir is None:
        return
    try:
        state = pir.state
    except Exception:
        try:
            state = pir.value()
        except Exception:
            return
    if state:
        handle_motion()


# =====================================================================
# WIFI
# =====================================================================
def ensure_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    show("Connecting WiFi...", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    for _ in range(40):
        if wlan.isconnected():
            return True
        time.sleep(0.5)
    return False


# =====================================================================
# BUTTON BINDINGS
# =====================================================================
btnA.wasPressed(lambda: ask_and_speak(QUESTIONS["A"]))
btnB.wasPressed(lambda: ask_and_speak(QUESTIONS["B"]))
btnC.wasPressed(lambda: ask_and_speak(QUESTIONS["C"]))


# =====================================================================
# MAIN LOOP
# =====================================================================
if not ensure_wifi():
    show("WiFi failed", "check SSID / password")
else:
    show_idle()

while True:
    try:
        poll_motion()
    except Exception:
        pass
    time.sleep(2)
