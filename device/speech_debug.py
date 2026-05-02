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
import network
import urequests
import ujson
import time
import gc
import uos
import ubinascii
import sys

# IMPORTANT: do NOT `import MicrophonePDM` at module load. On this UIFlow1
# firmware the mere import claims the I2S0 peripheral — same problem as
# `machine.I2S` — and the next speaker.playWAV fails with an I2S error and
# the device resets. We lazy-import inside _init_mic() and try to fully
# release I2S in _release_mic(). MIC is stashed globally as _MIC after first
# import so record_question() can use it.
_MIC = None

# Tracks whether speaker.playWAV has actually run in this session. We only
# call _release_speaker() when this is True — probing teardown methods like
# speaker.deinit() / speaker.stop() on a never-initialised speaker module
# natively panics on this UIFlow1 firmware and resets the device, which was
# being hit on the very first record press (A/C) on a fresh boot.
_speaker_used = False

# SDCard + Pin from machine are safe to import. machine.I2S is NOT — importing
# it locks the I2S peripheral on this firmware and speaker.playTone hangs.
try:
    from machine import SDCard, Pin
    _HAS_SDCARD = True
except Exception as _sd_imp_err:
    print("SD: machine.SDCard import failed:", _sd_imp_err)
    _HAS_SDCARD = False

# Hardware watchdog — if a native panic slips past _release_speaker() etc., the
# device auto-recovers in ~1s instead of bricking until manual reset. 90s is
# longer than the worst-case ASK round-trip (record + STT + ask + TTS fetch +
# playback settle ≈ 40s) so legitimate handlers never trip it. We feed it from
# the main loop only — handlers don't need to feed because they finish well
# under the timeout.
try:
    from machine import WDT
    _wdt = WDT(timeout=90000)
    print("WDT: armed (90s)")
except Exception as _wdt_err:
    print("WDT: not available:", _wdt_err)
    _wdt = None

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

# Speaker channel — Core2's built-in speaker is wired to ONE of the two I2S
# channels. If audio is missing or sounds bad, switch this to the other.
#   "R"  = speaker.CHN_R   (right channel)
#   "L"  = speaker.CHN_L   (left channel — try this if R sounds wrong)
#   "LR" = speaker.CHN_LR  (both, if the firmware exposes it)
SPEAKER_CHANNEL = "LR"   # UIFlow1 block default is "left and right"

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

        # NOTE: do NOT add &profile=m5stack here. On this firmware
        # speaker.playWAV(path) plays at a fixed I2S rate and does not
        # auto-detect from the WAV fmt chunk, so a 16 kHz "m5stack profile"
        # WAV plays high-pitched and overruns the buffer (panic + reset).
        # speech_demo.py succeeds because it uses the backend's default WAV,
        # whose rate matches the speaker's default rate. Keep that here.
        url = BACKEND_URL + "/api/v1/speech/tts?raw=1"
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

def _inspect_wav_header(wav_path):
    """Read the RIFF/fmt chunk and return (rate, bits, channels, data_size).
    Returns (None, None, None, 0) on any parse failure. We trust the file over
    WAV_RATE/WAV_BITS — the backend has been observed to ignore ?profile=m5stack
    and return 8-bit or stereo, which the speaker's I2S driver then rejects."""
    try:
        with open(wav_path, "rb") as f:
            hdr = f.read(44)
        if len(hdr) < 44 or hdr[0:4] != b"RIFF" or hdr[8:12] != b"WAVE":
            print("WAV header: not a RIFF/WAVE file")
            return None, None, None, 0
        # fmt chunk fields are little-endian.
        channels = hdr[22] | (hdr[23] << 8)
        rate = hdr[24] | (hdr[25] << 8) | (hdr[26] << 16) | (hdr[27] << 24)
        bits = hdr[34] | (hdr[35] << 8)
        data_size = hdr[40] | (hdr[41] << 8) | (hdr[42] << 16) | (hdr[43] << 24)
        print("WAV header: rate=" + str(rate)
              + " bits=" + str(bits)
              + " ch=" + str(channels)
              + " data=" + str(data_size))
        return rate, bits, channels, data_size
    except Exception as e:
        print("WAV header read failed:", e)
        return None, None, None, 0

def _bits_to_format(bits):
    """Map the WAV's bit depth to the speaker module's data_format constant.
    UIFlow1 on Core2 exposes F16B / F24B / F32B but no F8B — 8-bit WAVs are
    not playable directly and must be regenerated 16-bit on the backend."""
    if bits == 16:
        return getattr(speaker, "F16B", None)
    if bits == 24:
        return getattr(speaker, "F24B", None)
    if bits == 32:
        return getattr(speaker, "F32B", None)
    return None

def play_wav_file(wav_path):
    rate, bits, channels, data_size = _inspect_wav_header(wav_path)
    if rate is None:
        # Fall back to declared defaults so playback still attempts.
        rate, bits, channels = WAV_RATE, WAV_BITS, 1
        try:
            data_size = uos.stat(wav_path)[6] - 44
        except Exception:
            data_size = 0

    # Estimate duration from the actual fmt chunk, not WAV_RATE/WAV_BITS.
    bytes_per_sec = rate * (bits // 8) * max(1, channels)
    if bytes_per_sec <= 0:
        bytes_per_sec = WAV_RATE * (WAV_BITS // 8)
    est_secs = max(1.0, data_size / float(bytes_per_sec)) if data_size else 3.0
    if est_secs > 30:
        est_secs = 30

    fmt = _bits_to_format(bits)
    if fmt is None:
        print("playWAV: unsupported bit depth", bits, "(no F", bits, "B constant)")
        return False, "unsupported bits=" + str(bits), 0.0
    if channels != 1:
        # Speaker is mono; UIFlow1's playWAV does not down-mix. Warn loudly.
        print("playWAV: WAV is", channels, "channels, expected mono")

    # Free heap before kicking off async DMA — fewer allocations during the
    # speaker IRQ path means lower chance of a panic during DMA cleanup.
    gc.collect()

    show("Playing", wav_path, str(rate) + "Hz " + str(bits) + "b ch" + str(channels))

    # Set volume separately if the speaker exposes it — keeps playWAV() call
    # itself minimal so the firmware can parse the WAV header and pick I2S
    # params itself (matches the working speech_demo.py path).
    for vname in ("setVolume", "volume"):
        vfn = getattr(speaker, vname, None)
        if callable(vfn):
            try:
                vfn(PLAY_VOLUME)
                break
            except Exception:
                pass

    # Resolve the configured channel — defaults to right if the constant is
    # unrecognised or the firmware doesn't expose CHN_LR.
    ch_name = "CHN_" + SPEAKER_CHANNEL
    ch = getattr(speaker, ch_name, None)
    if ch is None:
        ch = getattr(speaker, "CHN_R", None)
        print("speaker." + ch_name + " not found, using CHN_R")

    last_err = None

    # Attempt 1: explicit params from the WAV's actual fmt chunk + configured
    # channel. This is the safe form — bare playWAV(path) on this firmware
    # plays at a fixed default rate/channel and produced "sounds terrible"
    # output when the WAV's rate didn't match those defaults.
    global _speaker_used
    try:
        speaker.playWAV(
            wav_path,
            rate=rate,
            data_format=fmt,
            channel=ch,
            volume=PLAY_VOLUME,
        )
        print("playWAV(path, rate=" + str(rate) + ", ch=" + SPEAKER_CHANNEL + ") OK")
        _speaker_used = True
    except Exception as e:
        last_err = "params: " + str(e)[:40]
        print("playWAV(params) error:", e)

        # Attempt 2: bare path — let the speaker module pick its own defaults.
        try:
            speaker.playWAV(wav_path)
            print("playWAV(path) bare OK")
            _speaker_used = True
            last_err = None
        except Exception as e2:
            last_err = last_err + " | bare: " + str(e2)[:40]
            print("playWAV(path) bare error:", e2)
            return False, last_err[:50], 0.0

    # IMPORTANT: do NOT call wait_ms / time.sleep here racing the async DMA.
    # speech_demo.py returns immediately after playWAV and lets the caller's
    # natural sleep cover playback. wait_ms inside this function competed
    # with DMA cleanup and was triggering a panic + reset shortly after the
    # WAV finished. Returning est_secs lets the caller scale its sleep to the
    # actual audio length — fixed time.sleep(3) was too short for longer
    # answers and let the next _release_speaker probe the bus mid-DMA.
    gc.collect()
    return True, "playWAV", est_secs

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

    ok2, info, est_secs = play_wav_file(result)
    if ok2:
        show("Playback OK", text[:38], str(info)[:35])
    else:
        show("Playback failed", str(info)[:35], "")
    # Sleep proportionally to the WAV's actual length so DMA always finishes
    # draining before this handler returns. We deliberately do NOT call
    # _release_speaker() here — probing teardown methods on a still-hot
    # speaker is what was triggering the "reproduces one audio and then
    # restarts" reset. The next record_question() releases safely at the
    # top, after the speaker has been idle long enough for DMA to settle.
    time.sleep(min(20.0, max(1.5, est_secs * 1.3 + 1.0)))
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
_attrs_dumped = False
def _dump_attrs_once():
    """Print every public method on speaker and _MIC the FIRST time we touch
    either. We need this to pick the real teardown name on this firmware —
    blindly probing stop/end/deinit/etc. is what's failing right now."""
    global _attrs_dumped
    if _attrs_dumped:
        return
    _attrs_dumped = True
    try:
        attrs = [a for a in dir(speaker) if not a.startswith("_")]
        print("speaker dir:", attrs)
    except Exception as e:
        print("speaker dir failed:", e)
    if _MIC is not None:
        try:
            attrs = [a for a in dir(_MIC) if not a.startswith("_")]
            print("MIC dir:", attrs)
        except Exception as e:
            print("MIC dir failed:", e)

def _init_mic():
    """Best-effort MIC begin. Safe to call multiple times — if begin raises
    because the peripheral is already bound, we ignore it and proceed.
    Performs the lazy import on first call so I2S0 isn't claimed at boot."""
    global _MIC
    if _MIC is None:
        # Block-generated code uses `import MicrophonePDM as MIC`, then calls
        # MIC.begin(...) — i.e. the module IS the API surface, not a class
        # to instantiate. Just bind the module to _MIC.
        try:
            import MicrophonePDM as _mod
            _MIC = _mod
        except Exception as e:
            print("MicrophonePDM import failed:", e)
            return
    _dump_attrs_once()
    # Generated block code uses .begin(...) with these exact kwargs. There is
    # no .init() variant on this firmware — confirmed by the block dump.
    try:
        _MIC.begin(pin_ws=MIC_WS_PIN, pin_data=MIC_DATA_PIN,
                   sample_rate_hz=RECORD_RATE,
                   buffer_length_ms=MIC_BUF_MS,
                   block_length_ms=MIC_BLOCK_MS)
        print("MIC.begin OK")
    except Exception as e:
        print("MIC.begin warn:", e)

def _release_mic():
    """Release I2S0 so the speaker can claim it. Block-confirmed API:
        MIC.recordStop()    # stop in-flight recording
        MIC.deinit(10000)   # deinit with timeout in ms
    Then drop the module reference + sys.modules pop + gc to ensure the
    underlying I2S peripheral is fully relinquished before the speaker
    tries to take it."""
    global _MIC
    if _MIC is None:
        return
    # Probe for each method by getattr first — calling a non-existent or
    # mis-signature method on this firmware doesn't always raise a Python
    # exception; some natively panic and reset the device.
    fn = getattr(_MIC, "recordStop", None)
    if callable(fn):
        try:
            fn()
            print("MIC.recordStop() OK")
        except Exception as e:
            print("MIC.recordStop warn:", e)
    fn = getattr(_MIC, "deinit", None)
    if callable(fn):
        try:
            fn(10000)
            print("MIC.deinit(10000) OK")
        except Exception as e:
            print("MIC.deinit warn:", e)
    _MIC = None
    sys.modules.pop("MicrophonePDM", None)
    gc.collect()
    time.sleep(0.3)
    print("MIC released (recordStop + deinit + module popped + gc'd)")

def _release_speaker():
    """Release I2S0 from the speaker module so the mic can re-claim it. After
    speaker.playWAV the speaker keeps I2S configured for output, which means
    the next MIC.begin() succeeds but recordStart writes a tiny/empty file.

    Probe list is intentionally narrow — only stop/end. deinit, stopWAV,
    stopAll and close were observed to natively panic on this firmware
    (both on a fresh-boot speaker that has never been initialised AND on
    a still-hot speaker whose DMA hasn't fully drained), which is the
    "reproduces one audio and then restarts" bug. stop/end are the only
    teardown names that reliably quiesce the I2S0 bus without crashing.

    NO-OP until a playWAV has actually happened — _speaker_used gates this
    so a fresh-boot mic press doesn't probe a never-initialised speaker."""
    if not _speaker_used:
        return
    for name in ("stop", "end"):
        fn = getattr(speaker, name, None)
        if fn is None:
            continue
        try:
            fn()
            print("speaker." + name + "() OK")
        except Exception as e:
            print("speaker." + name + " warn:", e)
    gc.collect()
    # Longer settle than mic side — the speaker DMA may still be draining.
    # Bumped from 0.5s to 2.0s after observing speaker→mic resets when this
    # was called from record_question() shortly after a poll-played WAV.
    # The user-visible cost is a ~2s delay between pressing C and the
    # "Listening" prompt, which is acceptable.
    time.sleep(2.0)
    print("speaker released (stop/end + gc'd + 2s settle)")

def record_question():
    show("Listening", "Speak now (" + str(RECORD_SECONDS) + "s)", RECORD_PATH)

    # Wipe any previous recording so a failed write can't masquerade as success.
    try:
        uos.remove(RECORD_PATH)
    except Exception:
        pass

    # If a prior playWAV ran in this session, the speaker still owns I2S0 —
    # _init_mic() would silently bind to a wrong-state peripheral and
    # recording would write 44 bytes of header + nothing. Force-release.
    _release_speaker()
    _init_mic()

    if _MIC is None:
        return False, "MIC unavailable (import failed)", 0

    record_ms = RECORD_SECONDS * 1000
    f = None
    try:
        # Use BINARY mode — the C extension writes raw PCM bytes to the
        # descriptor, and text mode ('w') triggered a native crash in
        # earlier testing. This pattern previously produced valid WAVs.
        f = open(RECORD_PATH, "wb")
        _MIC.recordStart(f, record_ms)
        print("MIC.recordStart(file, " + str(record_ms) + ") OK")

        # Sleep for the recording duration plus margin. We don't call
        # waitDone() here because calling it without an active recording —
        # or with the wrong signature — causes a native panic that bypasses
        # Python's try/except. The blind sleep is what previously worked.
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
# Voice ASK — record + STT + upload only.
#
# We deliberately do NOT play the answer in this handler. The mic and speaker
# share I2S0 on Core2 — the firmware panics when we try to flip the bus from
# input to output mid-handler. Instead, /speech/ask synthesizes the answer
# audio server-side and queues it; the main loop's poll_pending_audio() picks
# it up within ~3 seconds and plays it. By that time the mic peripheral has
# been fully released and idle for several seconds → no I2S race.
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
    time.sleep(1)

    # 3. ASK upload — backend queues the answer audio; main loop plays it.
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
        d      = data.get("data", {}) if isinstance(data, dict) else {}
        intent = d.get("intent", "")
        queued = d.get("queued", False)
    except Exception as e:
        show("ASK error", str(e)[:35], ""); time.sleep(3); show_idle(); return

    print("ASK intent:", intent, "queued:", queued)
    if queued:
        show("Got it", intent[:35], "Answer coming...")
    else:
        show("ASK done", intent[:35], "no audio queued")
    # Handler ends — mic released. The main-loop poll will play the answer.
    time.sleep(2)
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

        ok2, info, est_secs = play_wav_file(result)
        if ok2:
            show("ASK plus TTS OK", str(info)[:35], "")
        else:
            show("Playback failed", str(info)[:35], "")
        # See test_tts_only — sleep proportional to playback, no release here.
        time.sleep(min(20.0, max(1.5, est_secs * 1.3 + 1.0)))

    except Exception as e:
        print("ASK test error:", e)
        show("ASK error", str(e)[:35], "")
        time.sleep(3)
    show_idle()

# -------------------------------------------------------------------
# Pending-audio poll — the speaker side of the decoupled ASK loop.
#
# Hits /speech/proactive?raw=1 which returns:
#   - 200 + WAV bytes  → an ASK answer was queued, OR a proactive trigger fired
#   - 204 (no content) → nothing to play
#
# We use ?raw=1 so the device gets a binary WAV body it can stream straight
# to disk. The legacy JSON path returns audio_b64 which would peak heap by
# ~50–100 KB during the decode — too risky on a 110 KB heap.
#
# This runs from the main loop only when not _busy, wrapped in _guard, so it
# can never collide with a button handler. It also can't collide with itself —
# the guard makes nested polls a no-op.
# -------------------------------------------------------------------
PROACTIVE_PATH    = "/flash/proactive.wav"
POLL_INTERVAL_MS  = 3000

def poll_pending_audio():
    try:
        url = (BACKEND_URL
               + "/api/v1/speech/proactive?device_id="
               + DEVICE_ID
               + "&raw=1")
        # GET, not POST — matches the route. Bearer auth same as other calls.
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
        # Try to read source/text headers if the firmware exposes them — purely
        # cosmetic for the LCD, fall back to generic labels if not available.
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

        ok, info, est_secs = play_wav_file(PROACTIVE_PATH)
        if ok:
            label = "Answer" if source == "ask" else "Announcement"
            show(label, (text or info)[:38], "")
            time.sleep(min(20.0, max(1.5, est_secs * 1.3 + 1.0)))
            show_idle()
        else:
            print("poll play failed:", info)

    except Exception as e:
        print("poll error:", e)


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

# First poll deferred ~5s after boot so the WiFi/cloud sync has settled.
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
    # returns, so the mic and speaker are never active in the same tick.
    if not _busy:
        now = time.ticks_ms()
        if time.ticks_diff(now, _last_poll_ms) >= POLL_INTERVAL_MS:
            _last_poll_ms = now
            _guarded_poll()

    time.sleep(1)
