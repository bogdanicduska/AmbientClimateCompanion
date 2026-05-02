from m5stack import lcd, btnA, btnB, btnC, speaker
from m5ui import *
from uiflow import *
import network
import urequests
import ujson
import time
import gc
import uos
import ubinascii
import sys

_MIC = None

try:
    from machine import SDCard, Pin
    _HAS_SDCARD = True
except Exception as _sd_imp_err:
    print("SD import failed:", _sd_imp_err)
    _HAS_SDCARD = False

# Hardware watchdog — auto-reboots in ~1s if a native panic slips past us.
# 90s is longer than any legitimate handler (record + STT + ASK upload ≈ 10s).
try:
    from machine import WDT
    _wdt = WDT(timeout=90000)
    print("WDT armed (90s)")
except Exception as _wdt_err:
    print("WDT not available:", _wdt_err)
    _wdt = None

WIFI_SSID = "LopezLed"
WIFI_PASS = "Chuma12345"

BACKEND_URL = "https://ambient-climate-backend-977755576323.europe-west6.run.app"
DEVICE_AUTH_TOKEN = "weather2026"
DEVICE_ID = "m5stack-ana-home"

TEST_TEXTS = (
    "Hi.",
    "The room feels good.",
    "Air quality is fine.",
    "Humidity is comfortable.",
)
_test_idx = 0

ASK_QUESTIONS = (
    "How is the air quality?",
    "Is the room ready?",
    "What is the temperature?",
)
_ask_idx = 0

WAV_RATE = 16000
WAV_BITS = 16
WAV_PATHS = ("/sd/answer.wav", "/flash/answer.wav")

RECORD_PATH = "/sd/question.wav"
RECORD_SECONDS = 2
RECORD_RATE = 16000

MIC_WS_PIN = 0
MIC_DATA_PIN = 34
MIC_BUF_MS = 5000
MIC_BLOCK_MS = 100

PLAY_VOLUME = 6

_busy = False


def _guard(handler):
    def wrapped():
        global _busy
        if _busy:
            print("guard busy")
            return
        _busy = True
        try:
            handler()
        except Exception as e:
            print("handler error:", e)
        finally:
            _busy = False
    return wrapped


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
    show("Speech Debug", "A stt   B tts   C ask", "")


def _auth_headers():
    return {
        "Authorization": "Bearer " + DEVICE_AUTH_TOKEN,
        "Content-Type": "application/json",
    }


def mount_sd():
    if not _HAS_SDCARD:
        return False

    try:
        uos.listdir("/sd")
        print("SD already mounted")
        return True
    except Exception:
        pass

    try:
        sd = SDCard(slot=2, sck=Pin(23), miso=Pin(33), mosi=Pin(19), freq=10000000)
    except Exception as e:
        print("SDCard failed:", e)
        return False

    fn = getattr(uos, "mountsd", None)
    if fn:
        try:
            fn(sd, "/sd")
            print("SD mounted via mountsd")
            return True
        except Exception as e:
            print("mountsd failed:", e)

    try:
        uos.mount(sd, "/sd")
        print("SD mounted via mount")
        return True
    except Exception as e:
        print("mount failed:", e)
        return False


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


def fetch_tts_wav(text):
    try:
        body = ujson.dumps({
            "device_id": DEVICE_ID,
            "text": text,
            "format": "wav",
        }).encode("utf-8")

        url = BACKEND_URL + "/api/v1/speech/tts?raw=1&profile=m5stack"
        r = urequests.post(url, data=body, headers=_auth_headers())
        show("TTS HTTP", str(r.status_code), "Downloading")
        print("TTS status:", r.status_code)

        if r.status_code != 200:
            try:
                err = r.text
            except Exception:
                err = "no text"
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


def play_wav_file(wav_path):
    try:
        wav_size = uos.stat(wav_path)[6]
    except Exception:
        wav_size = 0

    bytes_per_sec = WAV_RATE * (WAV_BITS // 8)
    est_secs = max(1.0, (wav_size - 44) / float(bytes_per_sec)) if wav_size else 3.0
    if est_secs > 30:
        est_secs = 30

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
        return False, str(e)[:50], 0.0

    try:
        wait_ms(int(est_secs * 1000) + 500)
    except Exception:
        time.sleep(est_secs + 0.5)

    return True, "playWAV", est_secs


def _init_mic():
    global _MIC

    if _MIC is None:
        try:
            import MicrophonePDM as _mod
            _MIC = _mod
        except Exception as e:
            print("MicrophonePDM import failed:", e)
            return

    try:
        _MIC.begin(
            pin_ws=MIC_WS_PIN,
            pin_data=MIC_DATA_PIN,
            sample_rate_hz=RECORD_RATE,
            buffer_length_ms=MIC_BUF_MS,
            block_length_ms=MIC_BLOCK_MS
        )
        print("MIC.begin OK")
    except Exception as e:
        print("MIC.begin warn:", e)


def _release_mic():
    global _MIC

    if _MIC is None:
        return

    for name in ("recordStop", "stop", "deinit", "end"):
        fn = getattr(_MIC, name, None)
        if fn is None:
            continue
        try:
            fn()
            print("MIC." + name + "() OK")
        except Exception as e:
            print("MIC." + name + " warn:", e)

    _MIC = None

    try:
        sys.modules.pop("MicrophonePDM", None)
    except Exception:
        pass

    gc.collect()
    time.sleep(0.3)
    print("MIC released")


def record_question():
    show("Listening", "Speak now (" + str(RECORD_SECONDS) + "s)", RECORD_PATH)

    try:
        uos.remove(RECORD_PATH)
    except Exception:
        pass

    _init_mic()

    if _MIC is None:
        return False, "MIC unavailable", 0

    f = None
    try:
        f = open(RECORD_PATH, "wb")
        _MIC.recordStart(f, RECORD_SECONDS * 1000)

        time.sleep(RECORD_SECONDS + 1)

        try:
            f.flush()
        except Exception:
            pass

        try:
            f.close()
        except Exception:
            pass

        f = None

        try:
            size = uos.stat(RECORD_PATH)[6]
        except Exception:
            size = 0

        _release_mic()

        if size <= 44:
            return False, "tiny file ({0} B)".format(size), size

        gc.collect()
        time.sleep(0.7)
        return True, "MicrophonePDM", size

    except Exception as e:
        if f is not None:
            try:
                f.close()
            except Exception:
                pass

        _release_mic()
        gc.collect()
        time.sleep(0.7)
        print("record fail:", e)
        return False, str(e)[:60], 0


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

        b64 = ubinascii.b2a_base64(wav_bytes).decode("utf-8").rstrip("\n")
        del wav_bytes
        gc.collect()

        body = ujson.dumps({
            "device_id": DEVICE_ID,
            "audio_b64": b64,
            "format": "wav",
        }).encode("utf-8")

        del b64
        gc.collect()

        r = urequests.post(
            BACKEND_URL + "/api/v1/speech/stt",
            data=body,
            headers=_auth_headers(),
        )

        del body
        gc.collect()

        print("STT status:", r.status_code)

        if r.status_code != 200:
            try:
                err = r.text
            except Exception:
                err = "no body"
            print("STT err body:", err)
            r.close()
            return False, "HTTP {0}: {1}".format(r.status_code, str(err)[:50])

        data = r.json()
        r.close()

        d = data.get("data", {}) if isinstance(data, dict) else {}
        text = (
            d.get("transcript")
            or d.get("text")
            or d.get("transcription")
            or ""
        )
        return True, text

    except Exception as e:
        print("STT error:", e)
        return False, str(e)[:60]


def test_record_stt():
    ok, info, size = record_question()
    if not ok:
        show("Record failed", str(info)[:35], "")
        time.sleep(3)
        show_idle()
        return

    show("Recorded", info[:35], "size " + str(size))
    time.sleep(1)

    ok, text = transcribe_wav(RECORD_PATH)
    if not ok:
        show("STT failed", str(text)[:35], "")
        time.sleep(4)
        show_idle()
        return

    if not text:
        show("STT empty", "no transcription", "try louder/closer")
        time.sleep(4)
        show_idle()
        return

    print("STT text:", text)
    show("You said", text[:38], "")
    time.sleep(5)
    show_idle()


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

    ok2, info, _est = play_wav_file(result)
    if ok2:
        show("Playback OK", text[:38], str(info)[:35])
    else:
        show("Playback failed", str(info)[:35], "")

    time.sleep(3)
    show_idle()


def test_voice_ask():
    # Record + STT + ASK upload only. The answer audio is synthesized on the
    # backend and queued; the main-loop poll plays it ~3s later. This avoids
    # the I2S0 mic→speaker race that resets the device when both peripherals
    # are touched in the same handler.
    ok, info, size = record_question()
    if not ok:
        show("Record failed", str(info)[:35], "")
        time.sleep(3)
        show_idle()
        return

    show("Recorded", info[:35], "size " + str(size))
    time.sleep(1)

    ok, text = transcribe_wav(RECORD_PATH)
    if not ok:
        show("STT failed", str(text)[:35], "")
        time.sleep(4)
        show_idle()
        return

    if not text:
        show("STT empty", "no transcription", "try louder/closer")
        time.sleep(4)
        show_idle()
        return

    print("STT text:", text)
    show("You said", text[:38], "asking backend...")
    time.sleep(1)

    try:
        body = ujson.dumps({
            "device_id": DEVICE_ID,
            "question": text,
        }).encode("utf-8")

        r = urequests.post(
            BACKEND_URL + "/api/v1/speech/ask",
            data=body,
            headers=_auth_headers(),
        )

        if r.status_code != 200:
            try:
                err = r.text
            except Exception:
                err = ""
            r.close()
            show("ASK failed", "HTTP " + str(r.status_code), str(err)[:35])
            time.sleep(4)
            show_idle()
            return

        data = r.json()
        r.close()

        d      = data.get("data", {}) if isinstance(data, dict) else {}
        intent = d.get("intent", "")
        queued = d.get("queued", False)

    except Exception as e:
        show("ASK error", str(e)[:35], "")
        time.sleep(3)
        show_idle()
        return

    print("ASK intent:", intent, "queued:", queued)
    if queued:
        show("Got it", intent[:35], "Answer coming...")
    else:
        show("ASK done", intent[:35], "no audio queued")
    # Handler ends — mic released. Main-loop poll will play the answer.
    time.sleep(2)
    show_idle()


# -------------------------------------------------------------------
# poll_pending_audio — speaker side of the decoupled ASK loop.
# Hits /speech/proactive?raw=1, which returns:
#   200 + WAV bytes  → an ASK answer was queued, OR a proactive trigger fired
#   204 (no content) → nothing to play
# Wrapped in _guard from the main loop so it never collides with a button
# handler. Mic is never touched here — speaker only.
# -------------------------------------------------------------------
PROACTIVE_PATH   = "/flash/proactive.wav"
POLL_INTERVAL_MS = 3000

def poll_pending_audio():
    try:
        url = (BACKEND_URL
               + "/api/v1/speech/proactive?device_id="
               + DEVICE_ID
               + "&raw=1")
        r = urequests.get(url, headers={"Authorization": "Bearer " + DEVICE_AUTH_TOKEN})
        status = r.status_code

        if status == 204:
            r.close()
            return

        if status != 200:
            print("poll status:", status)
            r.close()
            return

        try:
            content = r.content
        except Exception as e:
            r.close()
            print("poll body read failed:", e)
            return

        # Best-effort header read for LCD label — not all firmwares expose this.
        source = "play"
        text   = ""
        try:
            hdrs = getattr(r, "headers", {}) or {}
            source = hdrs.get("X-Source", source) or source
            text   = hdrs.get("X-Text", text) or text
        except Exception:
            pass
        r.close()

        try:
            with open(PROACTIVE_PATH, "wb") as f:
                f.write(content)
            size = len(content) if content else 0
        except Exception as e:
            print("poll write failed:", e)
            return

        del content
        gc.collect()
        print("poll wrote " + PROACTIVE_PATH + " size=" + str(size))

        ok, info, _est = play_wav_file(PROACTIVE_PATH)
        if ok:
            label = "Answer" if source == "ask" else "Announcement"
            show(label, (text or info)[:38], "")
            time.sleep(1)
            show_idle()
        else:
            print("poll play failed:", info)

    except Exception as e:
        print("poll error:", e)


_sd_ok = mount_sd()
show(
    "SD: " + ("mounted /sd" if _sd_ok else "not mounted"),
    "WAV will use " + ("/sd" if _sd_ok else "/flash"),
    ""
)
time.sleep(1)

if ensure_wifi():
    show_idle()
else:
    show("No WiFi", "Fix config first", "")

btnA.wasPressed(_guard(test_record_stt))
btnB.wasPressed(_guard(test_tts_only))
btnC.wasPressed(_guard(test_voice_ask))

# First poll deferred ~5s after boot so WiFi/cloud sync has settled.
_last_poll_ms = time.ticks_add(time.ticks_ms(), -POLL_INTERVAL_MS + 5000)
_guarded_poll = _guard(poll_pending_audio)

while True:
    if _wdt is not None:
        try:
            _wdt.feed()
        except Exception:
            pass

    # Poll for queued audio (ASK answers + proactive announcements). Only when
    # idle — _busy from a button handler suppresses this until the handler
    # returns, so mic and speaker are never active in the same tick.
    if not _busy:
        now = time.ticks_ms()
        if time.ticks_diff(now, _last_poll_ms) >= POLL_INTERVAL_MS:
            _last_poll_ms = now
            _guarded_poll()

    time.sleep(1)