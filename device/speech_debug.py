from m5stack import lcd, btnA, btnB, btnC, speaker
try:
    from m5stack import touch as _touch
    _HAS_TOUCH = True
except Exception as _t_imp_err:
    print("touch import failed:", _t_imp_err)
    _HAS_TOUCH = False
    _touch = None
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

# Speaker state — used by _release_speaker() to compute how long to wait for
# DMA to drain before probing teardown methods (some of which native-panic on
# this UIFlow1 firmware if called while DMA is still active).
_speaker_used         = False
_speaker_last_play_ms = 0
_speaker_attrs_dumped = False

try:
    from machine import SDCard, Pin
    _HAS_SDCARD = True
except Exception as _sd_imp_err:
    print("SD import failed:", _sd_imp_err)
    _HAS_SDCARD = False

try:
    from machine import I2S
    _HAS_I2S = True
except Exception as _i2s_imp_err:
    print("I2S import failed:", _i2s_imp_err)
    _HAS_I2S = False

import array

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
# 5s window matches a known-working classmate setup. The PDM mic on Core2
# eats ~200-400ms of head while it settles, so 2s left ~1.6s usable audio
# which Google STT often returned empty on.
RECORD_SECONDS = 5
RECORD_RATE = 16000

MIC_WS_PIN = 0
MIC_DATA_PIN = 34
MIC_BUF_MS = 5000
MIC_BLOCK_MS = 100

# Raw I2S PDM settings — matches the classmate's working constructor
# (I2S.NUM0, MASTER_PDM, B16, ONLY_RIGHT, 16k samplerate, dmacount=16, dmalen=256).
# Verified against M5Stack community forum thread on Core2 PDM mic access.
I2S_DMA_COUNT = 16
I2S_DMA_LEN   = 256
# 1024 int16 samples per readinto = 2048 bytes = 64 ms at 16 kHz, well below
# the DMA buffer size (16*256 = 4096 samples = 256 ms) so we never lose audio.
I2S_READ_SAMPLES = 1024

PLAY_VOLUME = 6

# -------------------------------------------------------
# Coach — guided breathing techniques. Press Btn B from idle to open
# the touch menu (defined below as COACH_MENU_ITEMS); tap any row to
# run that session. Btn A from the menu returns to idle.
# -------------------------------------------------------
COACH_TECHNIQUES = (
    {"id": "box", "name": "Box Breathing",
     "subtitle": "Focus + reset",
     "cycles": 4,
     "phases": (("INHALE", 4), ("HOLD", 4), ("EXHALE", 4), ("HOLD", 4))},
)


# Visual layout — Headspace-inspired coral orb on the existing dark bg.
# Vertical zones:
#   y= 12– 38  phase label
#   y= 44–176  orb (center 110, max radius 56)
#   y=185–216  big countdown digit
#   y=222–230  cycle progress dots
COACH_BG       = 0x0A1220
COACH_CX       = 160
COACH_CY       = 110
COACH_R_MIN    = 28
COACH_R_MAX    = 56
COACH_FPS      = 4          # frames per second for radius interpolation
COACH_FRAME_MS = 1000 // COACH_FPS

# Single coral palette — the orb stays one color through every phase.
# Phase is conveyed by size (small/big/hold) and the label text above.
ORB_COLOR        = 0xFE6E2E   # warm Headspace coral
PHASE_TEXT_COLOR = 0xFFD8C0   # soft cream-coral for the phase label
CYCLE_DOT_DIM    = 0x3A2418   # very dim coral for cycles not yet reached

# Wipe margin around the orb. UIFlow1's lcd.circle() fill uses a polygon
# approximation that produces visible triangular artifacts when thin
# colored rings overlap, so the orb is rendered as a single solid disc on
# the dark background — no halo, no glow ring.
ORB_WIPE_MARGIN = 4

# Phase label center-x positions (FONT_DejaVu24 char width ≈ 14px).
# Hardcoded because lcd.textWidth() isn't reliable on UIFlow1.
PHASE_LABEL_X = {"INHALE": 118, "HOLD": 132, "EXHALE": 118}

# Detect available large fonts at module load. UIFlow1 builds vary —
# DejaVu40 is preferred for the countdown but not on every firmware.
try:
    _COACH_FONT_BIG = lcd.FONT_DejaVu40
except AttributeError:
    try:
        _COACH_FONT_BIG = lcd.FONT_DejaVu24
    except AttributeError:
        _COACH_FONT_BIG = lcd.FONT_Default
try:
    _COACH_FONT_MED = lcd.FONT_DejaVu24
except AttributeError:
    _COACH_FONT_MED = lcd.FONT_Default
try:
    _COACH_FONT_SM = lcd.FONT_DejaVu18
except AttributeError:
    _COACH_FONT_SM = lcd.FONT_Default

# -------------------------------------------------------
# Coach menu (touch-driven). Three rows: voice Ask (record → STT → ASK
# → TTS → play), Box Breathing, Quick Advice (AdviceSlip API).
#
# Layout: rows of 44px height, 4px gap, starting at y=42.
# Row 0: 42-86 / Row 1: 90-134 / Row 2: 138-182.
# Bottom space before bezel buttons (y=240+).
# -------------------------------------------------------
COACH_MENU_ITEMS = (
    {"kind": "ask"},
    {"kind": "breathing", "tech_idx": 0},
    {"kind": "advice"},
)

COACH_ROW_TOP    = 42
COACH_ROW_HEIGHT = 44
COACH_ROW_GAP    = 4
COACH_ROW_PITCH  = COACH_ROW_HEIGHT + COACH_ROW_GAP

COACH_ROW_BG     = 0x0F1828   # slightly lighter than COACH_BG — card feel
COACH_ROW_FLASH  = 0xFE6E2E   # full coral flash on tap
COACH_TITLE_DIM  = 0x556677
COACH_SUBT_DIM   = 0x8899AA

# AdviceSlip API. Free, no auth, returns {"slip": {"id": ..., "advice": "..."}}.
# Practical short hints fit the device's environmental wellbeing role better
# than abstract affirmations.
ADVICE_URL  = "https://api.adviceslip.com/advice"
ADVICE_FALLBACKS = (
    "Drink a glass of water.",
    "Open a window for a minute.",
    "Stand up and stretch briefly.",
    "Take three slow breaths.",
)
_advice_fallback_idx = 0

# Pre-baked TTS prompts for the breathing session. Cached lazily on first
# Box session via fetch_tts_wav, then replayed offline during phase cues.
COACH_VOICE_WAVS = {
    "INHALE": "coach_inhale.wav",
    "HOLD":   "coach_hold.wav",
    "EXHALE": "coach_exhale.wav",
}

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
    show("Speech Debug",
         "A stt   B coach   C ask",
         "")


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

        # Validate the response is actually a WAV before saving it. If the
        # backend returned an error page (HTML/JSON), playWAV will native-panic
        # on a malformed RIFF header — fail loudly here instead.
        if not content or len(content) <= 1024:
            head_dump = "empty" if not content else repr(content[:8])
            print("TTS body too small:", len(content) if content else 0, head_dump)
            show("TTS body bad", "size " + str(len(content) if content else 0), head_dump[:35])
            return False, "body too small"

        if not content.startswith(b"RIFF"):
            head_dump = repr(content[:8])
            print("TTS not a WAV, head:", head_dump)
            show("TTS not WAV", head_dump[:35], "")
            return False, "not RIFF"

        last_err = "no path"
        for candidate in WAV_PATHS:
            try:
                with open(candidate, "wb") as f:
                    f.write(content)

                size = len(content) if content else 0
                _diag("WAV saved: " + candidate + " size=" + str(size))

                del content
                gc.collect()

                return True, candidate
            except Exception as e:
                last_err = "{0}: {1}".format(candidate, e)
                print("write failed:", last_err)

        return False, last_err

    except Exception as e:
        print("fetch_tts_wav error:", e)
        return False, str(e)


def _dump_wav_format(wav_path):
    """Read the fmt chunk and report channels / sample rate / bits.
    Distorted playback (chipmunk, buzz, slow) means the WAV the backend
    sent doesn't match what speaker.playWAV expects (16 kHz, mono, 16-bit)."""
    try:
        with open(wav_path, "rb") as f:
            hdr = f.read(44)
        if len(hdr) < 44 or not hdr.startswith(b"RIFF"):
            _diag("wav fmt: bad header")
            return None, None, None
        ch   = int.from_bytes(hdr[22:24], "little")
        rate = int.from_bytes(hdr[24:28], "little")
        bits = int.from_bytes(hdr[34:36], "little")
        _diag("wav fmt: ch={0} rate={1} bits={2}".format(ch, rate, bits))
        return ch, rate, bits
    except Exception as e:
        _diag("wav fmt err: " + str(e)[:30])
        return None, None, None


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

    _dump_wav_format(wav_path)
    _dump_speaker_attrs_once()

    # Match main_project.m5f's working call exactly. channel=CHN_R is the
    # critical kwarg on Core2 — without it audio routes to the wrong DAC and
    # comes out distorted/buzzy. data_format=F16B and rate must match the WAV.
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

    # Mark the speaker as used and timestamp DMA completion so _release_speaker
    # knows whether deinit() is safe to probe yet.
    global _speaker_used, _speaker_last_play_ms
    _speaker_used         = True
    _speaker_last_play_ms = time.ticks_ms()

    return True, "playWAV", est_secs


def _dump_speaker_attrs_once():
    """Dump dir(speaker) to diag on first speaker use. Tells us which teardown
    methods this firmware actually exposes, so we stop guessing at names."""
    global _speaker_attrs_dumped
    if _speaker_attrs_dumped:
        return
    _speaker_attrs_dumped = True
    try:
        attrs = [a for a in dir(speaker) if not a.startswith("_")]
        # Split across multiple diag lines so the LCD/log can show the full
        # list (LCD lines are ~38 chars). Console gets the full single line.
        print("speaker dir:", attrs)
        line = ",".join(attrs)
        _diag("speaker dir: " + line)
    except Exception as e:
        print("speaker dir failed:", e)
        _diag("speaker dir failed: " + str(e)[:40])


DIAG_LOG_PATH = "/flash/diag.log"


def _diag(msg):
    """Print + append to /flash/diag.log so we can review without a serial
    terminal. The file is overwritten on each fresh boot via _diag_reset()."""
    try:
        print(msg)
    except Exception:
        pass
    try:
        with open(DIAG_LOG_PATH, "a") as _f:
            _f.write(str(msg) + "\n")
    except Exception:
        pass


def _diag_reset():
    """Clear the diag log on boot so we only see the current session's output."""
    try:
        with open(DIAG_LOG_PATH, "w") as _f:
            _f.write("--- diag boot ---\n")
    except Exception:
        pass


def _release_speaker():
    """Wait for speaker DMA to drain before mic re-init.

    The speaker module on this firmware has NO teardown method (verified by
    dir(speaker) at boot — only playWAV/playTone/playRaw and format constants).
    The actual I2S0 reset is done by constructing a fresh I2S(NUM0,
    mode=MASTER_PDM, ...) instance inside _init_mic — that forcibly takes
    over the peripheral. Here we only ensure the last DMA buffer has finished
    so we don't yank I2S0 mid-frame."""
    if not _speaker_used:
        return
    idle_ms = time.ticks_diff(time.ticks_ms(), _speaker_last_play_ms)
    if idle_ms < 800:
        wait_s = (800 - idle_ms) / 1000.0
        _diag("speaker: waiting " + str(wait_s) + "s for DMA")
        time.sleep(wait_s)
    gc.collect()


def _init_mic():
    """Construct a raw I2S instance in MASTER_PDM mode on peripheral I2S0.

    This bypasses MicrophonePDM. Constructing a fresh I2S(NUM0, ...) forcibly
    reconfigures I2S0 from speaker-TX to mic-RX — that's the trick that
    makes the speaker→mic handoff work without a machine.reset(). The exact
    constructor signature is from a working classmate's code, cross-checked
    on the M5Stack community forum."""
    global _MIC

    if not _HAS_I2S:
        _diag("I2S unavailable — cannot init mic")
        show("I2S unavailable", "no machine.I2S", "")
        time.sleep(2)
        return

    # Drop any previous instance first so we don't double-claim I2S0.
    if _MIC is not None:
        try:
            _MIC.deinit()
        except Exception:
            pass
        _MIC = None
        gc.collect()

    try:
        _MIC = I2S(
            I2S.NUM0,
            ws=Pin(MIC_WS_PIN),
            sdin=Pin(MIC_DATA_PIN),
            mode=I2S.MASTER_PDM,
            dataformat=I2S.B16,
            channelformat=I2S.ONLY_RIGHT,
            samplerate=RECORD_RATE,
            dmacount=I2S_DMA_COUNT,
            dmalen=I2S_DMA_LEN,
        )
        _diag("I2S mic init OK (NUM0/PDM/16k)")
        show("MIC.begin OK", "ready to record", "")
        time.sleep(0.6)
    except Exception as e:
        err = str(e)[:38]
        _diag("I2S mic init FAIL: " + err)
        show("MIC.begin FAIL", err, "")
        _MIC = None
        time.sleep(2)


def _release_mic():
    global _MIC

    if _MIC is None:
        return

    try:
        _MIC.deinit()
        print("I2S mic deinit OK")
    except Exception as e:
        print("I2S mic deinit warn:", e)

    _MIC = None
    gc.collect()
    time.sleep(0.2)


MIC_GAIN = 5
MIC_SILENCE_THRESHOLD = 700


def _amplify_and_trim_wav(path):
    """Apply gain x5 to a recorded WAV in place (chunked for low memory) and
    trim trailing silence by adjusting the data chunk size in the header.

    Why: the Core2 PDM mic outputs very low-amplitude PCM — Google STT often
    returns empty transcripts on the raw signal. Boosting gain x5 (with clamp
    to int16 range) fixes the level. Trimming trailing silence helps STT
    detect end-of-utterance faster.

    Note: leading silence is intentionally NOT trimmed — that would require
    shifting file bytes, which MicroPython on this firmware handles poorly.
    A small leading silence has no impact on STT accuracy."""
    try:
        import array
    except Exception as e:
        _diag("array import fail: " + str(e)[:30])
        return

    try:
        size = uos.stat(path)[6]
    except Exception as e:
        _diag("amplify stat fail: " + str(e)[:30])
        return

    if size <= 44:
        _diag("amplify skip: tiny file " + str(size))
        return

    try:
        with open(path, "r+b") as f:
            header = f.read(44)
            if not header.startswith(b"RIFF") or header[36:40] != b"data":
                _diag("amplify skip: header layout unexpected")
                return

            CHUNK_BYTES   = 4096   # 2048 int16 samples per chunk
            max16         = 32767
            min16         = -32768
            threshold     = MIC_SILENCE_THRESHOLD
            gain          = MIC_GAIN
            last_loud_pos = 44
            pos           = 44

            while pos < size:
                f.seek(pos)
                buf = f.read(CHUNK_BYTES)
                if not buf:
                    break

                arr = array.array("h")
                arr.frombytes(buf)

                for i in range(len(arr)):
                    v = arr[i] * gain
                    if v > max16:
                        v = max16
                    elif v < min16:
                        v = min16
                    arr[i] = v
                    if v > threshold or v < -threshold:
                        last_loud_pos = pos + (i + 1) * 2

                f.seek(pos)
                f.write(arr.tobytes())
                pos += len(buf)
                gc.collect()

            # Pad ~80ms of silence past the last loud sample so STT gets a
            # clean end-of-utterance cue without cutting the speaker off.
            pad_bytes    = RECORD_RATE * 2 // 12
            new_data_end = min(size, last_loud_pos + pad_bytes)
            new_data_sz  = new_data_end - 44

            # Sanity floor: never declare a data chunk smaller than 100ms
            # of audio (3200 bytes). If we're below that, something went
            # wrong — leave the original size intact.
            min_data = RECORD_RATE * 2 // 10
            if new_data_sz < min_data:
                new_data_sz = size - 44

            new_riff_sz = 36 + new_data_sz

            f.seek(4)
            f.write(new_riff_sz.to_bytes(4, "little"))
            f.seek(40)
            f.write(new_data_sz.to_bytes(4, "little"))

        _diag("amplify x{0} done data={1} (was {2})".format(gain, new_data_sz, size - 44))
    except Exception as e:
        _diag("amplify error: " + str(e)[:40])

    gc.collect()


def _wav_header(data_size, sample_rate=RECORD_RATE, bits=16, channels=1):
    """Build a 44-byte WAV/RIFF header for PCM mono."""
    byte_rate   = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    riff_size   = 36 + data_size

    h = bytearray(44)
    h[0:4]   = b"RIFF"
    h[4:8]   = riff_size.to_bytes(4, "little")
    h[8:12]  = b"WAVE"
    h[12:16] = b"fmt "
    h[16:20] = (16).to_bytes(4, "little")          # fmt chunk size
    h[20:22] = (1).to_bytes(2, "little")           # PCM
    h[22:24] = channels.to_bytes(2, "little")
    h[24:28] = sample_rate.to_bytes(4, "little")
    h[28:32] = byte_rate.to_bytes(4, "little")
    h[32:34] = block_align.to_bytes(2, "little")
    h[34:36] = (bits).to_bytes(2, "little")
    h[36:40] = b"data"
    h[40:44] = data_size.to_bytes(4, "little")
    return h


def record_question():
    show("Listening", "Speak now (" + str(RECORD_SECONDS) + "s)", RECORD_PATH)

    try:
        uos.remove(RECORD_PATH)
    except Exception:
        pass

    # Wait for any in-flight speaker DMA to drain. The actual I2S0 mode flip
    # (TX→RX) happens inside _init_mic when we construct a fresh
    # I2S(NUM0, mode=MASTER_PDM, ...) — that reclaims the peripheral.
    _release_speaker()
    _init_mic()

    if _MIC is None:
        return False, "MIC unavailable", 0

    f = None
    try:
        f = open(RECORD_PATH, "wb")
        # Reserve 44 bytes for the header — we'll patch in the real sizes once
        # we know how many samples landed on disk.
        f.write(b"\x00" * 44)

        buf       = array.array("h", [0] * I2S_READ_SAMPLES)
        buf_bytes = I2S_READ_SAMPLES * 2
        gain      = MIC_GAIN
        max16     = 32767
        min16     = -32768

        target_bytes = RECORD_SECONDS * RECORD_RATE * 2
        data_bytes   = 0
        t_start      = time.ticks_ms()
        # Hard ceiling so a stuck readinto can't hang the watchdog past
        # RECORD_SECONDS + 2s.
        deadline_ms  = (RECORD_SECONDS + 2) * 1000

        while data_bytes < target_bytes:
            if time.ticks_diff(time.ticks_ms(), t_start) > deadline_ms:
                _diag("record: deadline reached at " + str(data_bytes) + " B")
                break

            try:
                n = _MIC.readinto(buf)
            except Exception as _re:
                _diag("readinto err: " + str(_re)[:40])
                break

            # Some firmware returns None — assume buffer fully filled.
            if n is None:
                n = buf_bytes
            if n <= 0:
                continue

            samples = n // 2
            # Apply ×5 gain inline (clamped). Matches classmate's working code:
            # the PDM mic outputs very low-amplitude PCM and Google STT returns
            # empty transcripts on the raw signal.
            for i in range(samples):
                v = buf[i] * gain
                if v > max16:
                    v = max16
                elif v < min16:
                    v = min16
                buf[i] = v

            if n == buf_bytes:
                f.write(buf)
            else:
                f.write(memoryview(buf)[:samples])
            data_bytes += n

            if _wdt is not None:
                try:
                    _wdt.feed()
                except Exception:
                    pass

        # Patch the WAV header with the actual data size now that we know it.
        f.seek(0)
        f.write(_wav_header(data_bytes))
        f.flush()
        f.close()
        f = None

        _release_mic()

        try:
            size = uos.stat(RECORD_PATH)[6]
            _diag("post-record size=" + str(size) + " data=" + str(data_bytes))
        except Exception:
            size = 0

        if data_bytes <= 0 or size <= 44:
            _diag("record FAIL tiny file " + str(size) + " B")
            return False, "tiny file ({0} B)".format(size), size

        gc.collect()
        time.sleep(0.4)
        return True, "I2S+gain x" + str(gain), size

    except Exception as e:
        if f is not None:
            try:
                f.close()
            except Exception:
                pass
        _release_mic()
        gc.collect()
        time.sleep(0.5)
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


def _smoothstep(t):
    """Cubic ease-in/out (3t² − 2t³). Linear interp reads mechanical;
    smoothstep gives the natural acceleration-then-deceleration that
    makes the orb feel like breath rather than a moving shape."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def _coach_draw_phase_label(phase):
    """Phase title at top of screen, larger font, hand-positioned center.
    Drawn once per phase (not per frame) — text doesn't change mid-phase."""
    lcd.rect(0, 8, 320, 32, COACH_BG, COACH_BG)
    lcd.font(_COACH_FONT_MED)
    lcd.setCursor(PHASE_LABEL_X.get(phase, 130), 12)
    lcd.setColor(PHASE_TEXT_COLOR)
    lcd.print(phase)


def _coach_draw_orb(radius):
    """Solid coral disc on dark background. The rectangular wipe is
    pixel-perfect; the orb is one filled circle with no surrounding
    rings. Anything more elaborate exposes UIFlow1's polygon-fill
    artifacts as visible triangular edges."""
    wipe_r = COACH_R_MAX + ORB_WIPE_MARGIN
    lcd.rect(COACH_CX - wipe_r, COACH_CY - wipe_r, wipe_r * 2, wipe_r * 2, COACH_BG, COACH_BG)
    lcd.circle(COACH_CX, COACH_CY, radius, ORB_COLOR, ORB_COLOR)


def _coach_draw_countdown(t_remaining):
    """Big coral digit just below the orb. FONT_DejaVu40 if available,
    falls back to DejaVu24 — detected once at module load."""
    lcd.rect(135, 182, 50, 38, COACH_BG, COACH_BG)
    lcd.font(_COACH_FONT_BIG)
    digit = str(int(t_remaining))
    # Width-aware center: ≈24px per digit at FONT_DejaVu40, ≈14 at DejaVu24.
    # Slightly off but reads centered enough at glance.
    half_w = 12 if len(digit) == 1 else 24
    lcd.setCursor(COACH_CX - half_w, 184)
    lcd.setColor(ORB_COLOR)
    lcd.print(digit)


def _coach_draw_cycle_dots(cycles_completed, total_cycles):
    """Row of small dots at the bottom — one per cycle. Past cycles
    filled in coral, future cycles dimmed. Reads like a progress bar."""
    DOT_R   = 5
    SPACING = 16
    total_w = max(0, total_cycles - 1) * SPACING
    start_x = COACH_CX - total_w // 2
    y       = 226
    lcd.rect(0, y - DOT_R - 1, 320, DOT_R * 2 + 2, COACH_BG, COACH_BG)
    for i in range(total_cycles):
        x   = start_x + i * SPACING
        col = ORB_COLOR if i < cycles_completed else CYCLE_DOT_DIM
        lcd.circle(x, y, DOT_R, col, col)


def _coach_feed_wdt():
    if _wdt is not None:
        try:
            _wdt.feed()
        except Exception:
            pass


class _CoachAbort(Exception):
    """Raised from inside the breathing render loop when the user presses
    Btn A. Bubbles cleanly out of all three nested loops (cycle → phase →
    frame) so we can show a 'Stopped' card and return to the menu."""
    pass


def _coach_check_abort():
    """Return True if the user pressed Btn A — used as a cancel signal
    inside the breathing session's frame loop."""
    try:
        return btnA.wasPressed()
    except Exception:
        return False


def _coach_voice_path(phase):
    """Cached WAV path for a phase word. Prefer /sd, fall back to /flash
    if SD isn't mounted (the 3 files are tiny — ~30 KB each)."""
    fname = COACH_VOICE_WAVS.get(phase)
    if not fname:
        return None
    if _sd_ok:
        return "/sd/" + fname
    return "/flash/" + fname


def _ensure_coach_voice_assets():
    """Pre-bake 'inhale', 'hold', 'exhale' TTS WAVs to disk on first use.
    Lazy: keeps boot fast; first Box session takes ~3 s extra. Subsequent
    sessions play offline from the cache. fetch_tts_wav saves to WAV_PATHS
    by default; we copy each result into the coach-specific path so a
    later ASK answer doesn't overwrite our prompts."""
    needed = []
    for phase in ("INHALE", "HOLD", "EXHALE"):
        path = _coach_voice_path(phase)
        if not path:
            continue
        try:
            uos.stat(path)
        except Exception:
            needed.append((phase, path))

    if not needed:
        return

    setScreenColor(COACH_BG)
    lcd.font(_COACH_FONT_MED)
    lcd.setCursor(20, 100)
    lcd.setColor(ORB_COLOR)
    lcd.print("Caching voice...")
    lcd.font(_COACH_FONT_SM)
    lcd.setCursor(20, 140)
    lcd.setColor(COACH_TITLE_DIM)
    lcd.print("First-time setup")

    for phase, path in needed:
        ok, info = fetch_tts_wav(phase.lower())
        if not ok:
            _diag("voice asset fetch failed: " + phase + " " + str(info))
            continue
        try:
            with open(info, "rb") as src:
                with open(path, "wb") as dst:
                    while True:
                        chunk = src.read(2048)
                        if not chunk:
                            break
                        dst.write(chunk)
            _diag("voice asset cached: " + path)
        except Exception as e:
            _diag("voice asset copy failed: " + str(e)[:40])
        gc.collect()


def _play_phase_cue(phase):
    """Fire-and-forget word at phase start. Non-blocking — DMA continues
    after the call returns, so the orb keeps animating. Word ~600 ms,
    Box phase 4 s, so DMA drains comfortably before the next cue."""
    path = _coach_voice_path(phase)
    if not path:
        return
    try:
        uos.stat(path)
    except Exception:
        return
    try:
        speaker.playWAV(path,
                        rate=WAV_RATE,
                        data_format=speaker.F16B,
                        channel=speaker.CHN_R,
                        volume=PLAY_VOLUME)
        global _speaker_used, _speaker_last_play_ms
        _speaker_used         = True
        _speaker_last_play_ms = time.ticks_ms()
    except Exception as e:
        print("phase cue err:", e)


def run_coach_session(tech):
    """Render a Headspace-inspired guided breathing session on the LCD.

    The orb grows during INHALE (smoothstep-eased), holds at max during HOLD
    after an inhale, shrinks during EXHALE, holds at min during HOLD after
    an exhale. A row of dots at the bottom tracks cycles completed.

    Btn A cancels the session at any point — the press is checked once per
    frame and raises _CoachAbort which unwinds all three nested loops."""
    # Reclaim I2S0 in case the user came here from Ask (mic-RX) or had a
    # recent answer playback (speaker-TX). Keeps phase cues from stomping
    # on a still-active peripheral configuration.
    _release_mic()
    _release_speaker()

    setScreenColor(COACH_BG)

    # ── Intro card ───────────────────────────────────────────────────────
    lcd.rect(0, 0, 320, 240, COACH_BG, COACH_BG)
    lcd.font(_COACH_FONT_MED)
    lcd.setCursor(20, 80)
    lcd.setColor(PHASE_TEXT_COLOR)
    lcd.print(tech["name"][:38])
    lcd.setCursor(20, 116)
    lcd.setColor(0xAAAAAA)
    lcd.print(tech["subtitle"][:38])
    lcd.setCursor(20, 152)
    lcd.setColor(0x556677)
    lcd.print("Get ready...")
    lcd.font(_COACH_FONT_SM)
    lcd.setCursor(20, 210)
    lcd.setColor(COACH_TITLE_DIM)
    lcd.print("Press A to stop anytime")
    time.sleep(1.5)
    # Drain any A-press that landed during the intro hold so it doesn't
    # immediately abort the session we're about to start.
    try:
        btnA.wasPressed()
    except Exception:
        pass

    # ── Session ──────────────────────────────────────────────────────────
    setScreenColor(COACH_BG)

    cycles    = tech["cycles"]
    phases    = tech["phases"]
    current_r = COACH_R_MIN
    aborted   = False

    try:
        for cycle in range(1, cycles + 1):
            # Cycle dots reflect cycles completed (cycle-1 fills before this one runs)
            _coach_draw_cycle_dots(cycle - 1, cycles)

            for (phase, secs) in phases:
                _coach_draw_phase_label(phase)
                _play_phase_cue(phase)

                if phase == "INHALE":
                    start_r, end_r = current_r, COACH_R_MAX
                elif phase == "EXHALE":
                    start_r, end_r = current_r, COACH_R_MIN
                else:
                    # HOLD: orb stays at whatever it was (max after inhale,
                    # min after exhale). end_r == start_r so easing is a no-op.
                    start_r, end_r = current_r, current_r

                total_frames = secs * COACH_FPS
                for f in range(total_frames):
                    if _coach_check_abort():
                        raise _CoachAbort()

                    frame_start = time.ticks_ms()
                    progress    = (f + 1) / total_frames if total_frames else 1.0
                    eased       = _smoothstep(progress)
                    radius      = int(start_r + (end_r - start_r) * eased)
                    _coach_draw_orb(radius)

                    # Countdown updates only at second boundaries
                    if f % COACH_FPS == 0:
                        t_remaining = secs - (f // COACH_FPS)
                        _coach_draw_countdown(t_remaining)
                        _coach_feed_wdt()

                    elapsed  = time.ticks_diff(time.ticks_ms(), frame_start)
                    sleep_ms = COACH_FRAME_MS - elapsed
                    if sleep_ms > 0:
                        time.sleep(sleep_ms / 1000.0)

                current_r = end_r
    except _CoachAbort:
        aborted = True

    if aborted:
        # ── Stopped card ─────────────────────────────────────────────────
        setScreenColor(COACH_BG)
        lcd.font(_COACH_FONT_MED)
        lcd.setCursor(20, 100)
        lcd.setColor(PHASE_TEXT_COLOR)
        lcd.print("Stopped")
        lcd.setCursor(20, 140)
        lcd.setColor(0x556677)
        lcd.print(tech["name"][:38])
        time.sleep(1.0)
        return

    # All cycles done — fill the final dot
    _coach_draw_cycle_dots(cycles, cycles)

    # ── Done card ────────────────────────────────────────────────────────
    setScreenColor(COACH_BG)
    lcd.font(_COACH_FONT_MED)
    lcd.setCursor(20, 80)
    lcd.setColor(ORB_COLOR)
    lcd.print("Done.")
    lcd.setCursor(20, 116)
    lcd.setColor(PHASE_TEXT_COLOR)
    lcd.print(tech["name"][:38])
    lcd.setCursor(20, 152)
    lcd.setColor(0x556677)
    lcd.print("Tap to continue")
    # Hold the done card up to ~3s but let the user dismiss with a tap
    _coach_wait_dismiss(3000)


def _menu_item_display(item):
    """Return (title, subtitle) for a menu row. Breathing items pull from
    COACH_TECHNIQUES so we don't duplicate the names."""
    kind = item["kind"]
    if kind == "breathing":
        tech = COACH_TECHNIQUES[item["tech_idx"]]
        return tech["name"], tech["subtitle"]
    if kind == "ask":
        return "Ask", "Weather, room, anything"
    if kind == "advice":
        return "Quick Advice", "A line for now"
    return item.get("title", ""), item.get("subtitle", "")


def _coach_row_y(row):
    return COACH_ROW_TOP + row * COACH_ROW_PITCH


def _coach_row_at(y):
    """Inverse of _coach_row_y: return row index for a y coordinate, or
    -1 if y is in a gap or outside the row band."""
    if y < COACH_ROW_TOP:
        return -1
    rel = y - COACH_ROW_TOP
    row = rel // COACH_ROW_PITCH
    if row >= len(COACH_MENU_ITEMS):
        return -1
    if (rel - row * COACH_ROW_PITCH) >= COACH_ROW_HEIGHT:
        return -1
    return row


def _draw_menu_row(row, item):
    title, subtitle = _menu_item_display(item)
    y = _coach_row_y(row)
    # Card bg
    lcd.rect(0, y, 320, COACH_ROW_HEIGHT, COACH_ROW_BG, COACH_ROW_BG)
    # Coral indicator bar on the left
    bar_color = ORB_COLOR
    lcd.rect(8, y + 8, 4, COACH_ROW_HEIGHT - 16, bar_color, bar_color)
    # Title + subtitle
    lcd.font(_COACH_FONT_MED)
    lcd.setCursor(24, y + 6)
    lcd.setColor(PHASE_TEXT_COLOR)
    lcd.print(title[:30])
    lcd.font(_COACH_FONT_SM)
    lcd.setCursor(24, y + 26)
    lcd.setColor(COACH_SUBT_DIM)
    lcd.print(subtitle[:36])


def _draw_coach_menu():
    setScreenColor(COACH_BG)
    # Title row at top — small, dim, "Coach" left, "A back" right
    lcd.font(_COACH_FONT_SM)
    lcd.setCursor(8, 10)
    lcd.setColor(PHASE_TEXT_COLOR)
    lcd.print("Coach")
    lcd.setCursor(252, 10)
    lcd.setColor(COACH_TITLE_DIM)
    lcd.print("A back")
    # Thin separator
    lcd.line(8, 34, 312, 34, 0x1A2A3A)
    # Rows
    for i, item in enumerate(COACH_MENU_ITEMS):
        _draw_menu_row(i, item)


def _flash_row(row):
    """Brief coral flash so the user knows their tap registered."""
    y = _coach_row_y(row)
    lcd.rect(0, y, 320, COACH_ROW_HEIGHT, COACH_ROW_FLASH, COACH_ROW_FLASH)
    time.sleep(0.1)


def _coach_wait_release():
    """Block until the touchscreen reports no contact. Used after we
    return from an action to consume the still-held press that opened it."""
    if not _HAS_TOUCH:
        return
    deadline = time.ticks_ms() + 1500
    while _touch.status():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            return
        time.sleep(0.02)


def _coach_wait_dismiss(timeout_ms):
    """Hold the current screen up to timeout_ms or until any tap.
    A short debounce up front so the tap that produced this card
    doesn't immediately dismiss it."""
    time.sleep(0.3)
    end = time.ticks_ms() + timeout_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if _HAS_TOUCH and _touch.status():
            _coach_wait_release()
            return
        if btnA.wasPressed() or btnB.wasPressed() or btnC.wasPressed():
            return
        time.sleep(0.04)
        _coach_feed_wdt()


def _wrap_text(text, max_chars):
    """Word-wrap a string into a list of lines no longer than max_chars."""
    words = text.split(" ")
    lines = []
    current = ""
    for w in words:
        if not current:
            current = w
        elif len(current) + 1 + len(w) <= max_chars:
            current = current + " " + w
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _fetch_advice():
    """GET adviceslip → returns the advice string, or a baked-in fallback
    if the request fails. Each fallback call cycles to a different message
    so repeated offline use isn't monotonous."""
    global _advice_fallback_idx
    try:
        r = urequests.get(ADVICE_URL)
        if r.status_code == 200:
            data = r.json()
            r.close()
            slip = data.get("slip", {}) if isinstance(data, dict) else {}
            text = slip.get("advice", "")
            if text:
                return text, True
        else:
            r.close()
    except Exception as e:
        print("advice fetch err:", e)

    fb = ADVICE_FALLBACKS[_advice_fallback_idx % len(ADVICE_FALLBACKS)]
    _advice_fallback_idx += 1
    return fb, False


def _draw_advice_card(text, online):
    setScreenColor(COACH_BG)
    # Title
    lcd.font(_COACH_FONT_SM)
    lcd.setCursor(8, 14)
    lcd.setColor(ORB_COLOR)
    lcd.print("Quick Advice" if online else "A reminder")
    # Body — wrap at ~22 chars/line for FONT_DejaVu24, max 4 lines
    lcd.font(_COACH_FONT_MED)
    lines = _wrap_text(text, 22)[:4]
    total_h    = len(lines) * 30
    start_y    = (240 - total_h) // 2
    for i, line in enumerate(lines):
        # Center each line horizontally — rough estimate at 14px per char
        text_w = len(line) * 14
        x      = max(8, (320 - text_w) // 2)
        lcd.setCursor(x, start_y + i * 30)
        lcd.setColor(PHASE_TEXT_COLOR)
        lcd.print(line)
    # Footer hint
    lcd.font(_COACH_FONT_SM)
    lcd.setCursor(110, 218)
    lcd.setColor(COACH_TITLE_DIM)
    lcd.print("tap to continue")


def _run_advice():
    setScreenColor(COACH_BG)
    lcd.font(_COACH_FONT_MED)
    lcd.setCursor(20, 110)
    lcd.setColor(COACH_TITLE_DIM)
    lcd.print("Fetching...")
    text, online = _fetch_advice()
    _draw_advice_card(text, online)
    _coach_wait_dismiss(30000)


def _draw_ask_status(title, subtitle=""):
    """Plain coach-themed status card — used for transient stages of the
    voice pipeline (Listening, Thinking, error states)."""
    setScreenColor(COACH_BG)
    lcd.font(_COACH_FONT_MED)
    lcd.setCursor(20, 90)
    lcd.setColor(ORB_COLOR)
    lcd.print(title[:30])
    if subtitle:
        lcd.font(_COACH_FONT_SM)
        lcd.setCursor(20, 130)
        lcd.setColor(COACH_TITLE_DIM)
        lcd.print(subtitle[:38])


def _draw_answer_card(answer, intent):
    """Final answer card. Coach header (with intent tag), centered body
    wrapped to 22 chars × 5 lines, tap-to-continue hint."""
    setScreenColor(COACH_BG)
    lcd.font(_COACH_FONT_SM)
    lcd.setCursor(8, 14)
    lcd.setColor(ORB_COLOR)
    lcd.print("Coach")
    if intent:
        intent_short = intent[:14]
        lcd.setCursor(max(120, 312 - len(intent_short) * 9), 14)
        lcd.setColor(COACH_TITLE_DIM)
        lcd.print(intent_short)

    lcd.font(_COACH_FONT_MED)
    lines   = _wrap_text(answer, 22)[:5]
    total_h = len(lines) * 28
    start_y = max(48, (240 - total_h) // 2)
    for i, line in enumerate(lines):
        text_w = len(line) * 14
        x      = max(8, (320 - text_w) // 2)
        lcd.setCursor(x, start_y + i * 28)
        lcd.setColor(PHASE_TEXT_COLOR)
        lcd.print(line)

    lcd.font(_COACH_FONT_SM)
    lcd.setCursor(110, 222)
    lcd.setColor(COACH_TITLE_DIM)
    lcd.print("tap to continue")


def _run_ask_session():
    """Voice question: record → STT → /speech/ask → TTS → play.

    The backend's regex-intent router answers weather/room data questions
    deterministically (temperature, humidity, recovery, air, rain, umbrella,
    readiness). Open-ended questions return intent='unknown' for now;
    LLM fallback is a deferred backend task."""
    # Listening card
    setScreenColor(COACH_BG)
    lcd.font(_COACH_FONT_MED)
    lcd.setCursor(20, 90)
    lcd.setColor(ORB_COLOR)
    lcd.print("Listening...")
    lcd.font(_COACH_FONT_SM)
    lcd.setCursor(20, 130)
    lcd.setColor(PHASE_TEXT_COLOR)
    lcd.print("Speak now (" + str(RECORD_SECONDS) + "s)")

    ok, info, size = record_question()
    if not ok:
        _draw_ask_status("Record failed", str(info)[:35])
        _coach_wait_dismiss(3000)
        return

    _draw_ask_status("Thinking...", "Transcribing")

    ok, text = transcribe_wav(RECORD_PATH)
    if not ok:
        _draw_ask_status("STT failed", str(text)[:35])
        _coach_wait_dismiss(3000)
        return
    if not text:
        _draw_ask_status("Did not hear you", "Try louder/closer")
        _coach_wait_dismiss(3000)
        return

    print("STT text:", text)
    _draw_ask_status("Asking...", text[:35])

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
            _draw_ask_status("ASK HTTP " + str(r.status_code), str(err)[:35])
            _coach_wait_dismiss(4000)
            return

        data = r.json()
        r.close()

        d      = data.get("data", {}) if isinstance(data, dict) else {}
        answer = d.get("answer", "")
        intent = d.get("intent", "")

    except Exception as e:
        _draw_ask_status("ASK error", str(e)[:35])
        _coach_wait_dismiss(3000)
        return

    if not answer:
        _draw_ask_status("No answer", intent[:35])
        _coach_wait_dismiss(3000)
        return

    print("ASK intent:", intent, "answer:", answer)
    _draw_answer_card(answer, intent)

    # Fetch + play TTS. Mic was released at end of record_question, so
    # I2S0 is free for speaker.playWAV.
    ok, result = fetch_tts_wav(answer)
    if ok:
        play_wav_file(result)

    _coach_wait_dismiss(8000)


def _execute_menu_item(row):
    item = COACH_MENU_ITEMS[row]
    kind = item["kind"]
    if kind == "ask":
        _run_ask_session()
    elif kind == "breathing":
        tech = COACH_TECHNIQUES[item["tech_idx"]]
        _ensure_coach_voice_assets()
        run_coach_session(tech)
    elif kind == "advice":
        _run_advice()


def coach_session():
    """Btn B handler: open the touch coach menu. Loops until Btn A is
    pressed for back. Each tap on a row runs that action and returns
    to the menu so the user can chain sessions."""
    try:
        while True:
            _draw_coach_menu()
            _coach_wait_release()  # consume the tap that opened the menu

            last_status = False
            selected   = -1
            while selected < 0:
                if btnA.wasPressed():
                    return
                if _HAS_TOUCH:
                    status = _touch.status()
                    if status and not last_status:
                        try:
                            x, y = _touch.read()
                        except Exception:
                            x, y = 0, 0
                        # Ignore taps on the bezel (y >= 240) — those are
                        # the A/B/C touch zones and have their own handlers.
                        if y < 232:
                            row = _coach_row_at(y)
                            if row >= 0:
                                _flash_row(row)
                                selected = row
                                break
                    last_status = status
                time.sleep(0.04)
                _coach_feed_wdt()

            _execute_menu_item(selected)
            # Loop: redraw menu and wait for the next selection
    finally:
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
    # Full local pipeline: record (mic) → STT → ASK → fetch TTS → play (speaker).
    # Tests both directions of the I2S0 handoff in one button press:
    #   - speaker→mic transition: record_question() calls _release_speaker()
    #     before _init_mic() so I2S0 drops output config first.
    #   - mic→speaker transition: record_question() calls _release_mic() at
    #     the end so I2S0 drops input config before play_wav_file opens
    #     the speaker.
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
        answer = d.get("answer", "")
        intent = d.get("intent", "")

    except Exception as e:
        show("ASK error", str(e)[:35], "")
        time.sleep(3)
        show_idle()
        return

    if not answer:
        show("No answer", intent[:35], "")
        time.sleep(3)
        show_idle()
        return

    print("ASK intent:", intent, "answer:", answer)
    show("Answer", answer[:38], intent[:35])
    time.sleep(1)

    # Fetch TTS + play. Mic was released at the end of record_question, so
    # I2S0 should be clean when speaker.playWAV claims it.
    ok, result = fetch_tts_wav(answer)
    if not ok:
        show("TTS failed", str(result)[:35], "")
        time.sleep(3)
        show_idle()
        return

    ok2, play_info, _est = play_wav_file(result)
    if ok2:
        show("Voice loop OK", play_info[:35], answer[:35])
    else:
        show("Play failed", str(play_info)[:35], "")

    time.sleep(3)
    show_idle()


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

# Reset the diag log so it only contains this session's output. The file
# accumulates across button presses but is wiped on each fresh boot.
_diag_reset()
_diag("boot — speech_debug ready")

# Dump speaker API at boot so we know exactly what teardown methods exist
# on this firmware — no more guessing at names in probes.
_dump_speaker_attrs_once()
if _HAS_I2S:
    try:
        _i2s_attrs = [a for a in dir(I2S) if not a.startswith("_")]
        _diag("I2S dir: " + ",".join(_i2s_attrs))
    except Exception as _i2s_err:
        _diag("I2S probe failed: " + str(_i2s_err)[:40])
else:
    _diag("I2S unavailable on this firmware")

btnA.wasPressed(_guard(test_record_stt))
btnB.wasPressed(_guard(coach_session))
btnC.wasPressed(_guard(test_voice_ask))

while True:
    if _wdt is not None:
        try:
            _wdt.feed()
        except Exception:
            pass
    time.sleep(1)

    time.sleep(1)