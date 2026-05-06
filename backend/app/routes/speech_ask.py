from flask import Blueprint, jsonify, request, current_app

from app.services.agent_service import answer_question
from app.services.auth_service import is_valid_device_token
from app.services.pending_audio_service import enqueue as enqueue_audio
from app.services.tts_service import synthesize_speech, convert_wav_for_m5stack
from app.utils.validators import validate_ask_payload
from app.utils.logger import get_logger

speech_ask_bp = Blueprint("speech_ask", __name__)
logger = get_logger(__name__)


@speech_ask_bp.post("/speech/ask")
def ask():
    if not is_valid_device_token(current_app.config):
        logger.warning("Auth failed on /speech/ask")
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    is_valid, error = validate_ask_payload(payload)
    if not is_valid:
        logger.warning(f"ASK validation failed: {error}")
        return jsonify({"success": False, "message": error}), 400

    device_id = payload["device_id"]
    question  = payload["question"].strip()
    logger.info(f"ASK — device={device_id} question={question!r}")

    try:
        result = answer_question(device_id, question, current_app.config)
    except Exception:
        current_app.logger.exception("ASK endpoint failed")
        return jsonify({"success": False, "message": "Internal server error"}), 500

    # Synthesize the answer audio and enqueue it for the device's next proactive
    # poll. Decouples the answer from this request's response so the device can
    # release its mic peripheral before the speaker is asked to play — works
    # around the M5Stack Core2 I2S0 mic↔speaker hardware conflict.
    answer_text = (result.get("answer") or "").strip()
    queued      = False
    if answer_text:
        try:
            tts = synthesize_speech(answer_text, current_app.config, audio_format="wav")
            # Re-encode to the M5Stack Core2 profile (16 kHz / 16-bit / mono).
            # OpenAI TTS returns 24 kHz WAV which the device's playWAV rejects
            # silently — the original /speech/tts route applies this same
            # conversion via ?profile=m5stack, so we mirror it here.
            audio_bytes = convert_wav_for_m5stack(tts["audio_bytes"])
            enqueue_audio(device_id, {
                "audio_bytes": audio_bytes,
                "text":        answer_text,
                "source":      "ask",
                "trigger_id":  "ask_" + (result.get("intent") or "unknown"),
            })
            queued = True
            logger.info(f"ASK queued audio for device={device_id} intent={result.get('intent')} bytes={len(audio_bytes)}")
        except Exception:
            current_app.logger.exception(f"ASK TTS/enqueue failed for device={device_id}")

    return jsonify({
        "success": True,
        "data":    {**result, "queued": queued},
    }), 200
