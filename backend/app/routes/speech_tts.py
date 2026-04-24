from flask import Blueprint, Response, jsonify, request, current_app

from app.services.tts_service import synthesize_speech, resolve_text, TEMPLATES, SUPPORTED_TTS_FORMATS
from app.services.auth_service import is_valid_device_token
from app.utils.validators import validate_tts_payload
from app.utils.logger import get_logger

speech_tts_bp = Blueprint("speech_tts", __name__)
logger = get_logger(__name__)


_MIME_MAP = {
    "mp3":  "audio/mpeg",
    "wav":  "audio/wav",
    "opus": "audio/ogg",
    "aac":  "audio/aac",
    "flac": "audio/flac",
    "pcm":  "application/octet-stream",
}


@speech_tts_bp.post("/speech/tts")
def tts():
    if not is_valid_device_token(current_app.config):
        logger.warning("Auth failed on /speech/tts")
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    is_valid, error = validate_tts_payload(payload)
    if not is_valid:
        logger.warning(f"TTS validation failed: {error}")
        return jsonify({"success": False, "message": error}), 400

    audio_format = str(payload.get("format", "mp3")).lower()
    if audio_format not in SUPPORTED_TTS_FORMATS:
        return jsonify({"success": False, "message": f"Unsupported format. Use one of: {sorted(SUPPORTED_TTS_FORMATS)}"}), 400

    try:
        spoken_text = resolve_text(payload.get("text"), payload.get("template"))
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    # ?raw=1 → return raw audio bytes (useful for embedded clients like M5Stack)
    raw = request.args.get("raw", "0") in ("1", "true", "yes")

    logger.info(f"TTS — device={payload['device_id']} fmt={audio_format} raw={raw} text={spoken_text!r}")

    try:
        result = synthesize_speech(spoken_text, current_app.config, audio_format=audio_format)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        current_app.logger.exception("TTS endpoint failed")
        return jsonify({"success": False, "message": "Internal server error"}), 500

    if raw:
        return Response(
            result["audio_bytes"],
            status=200,
            mimetype=_MIME_MAP.get(audio_format, "application/octet-stream"),
            headers={"X-Spoken-Text": spoken_text[:200]},
        )

    # JSON response — strip the raw bytes (only base64 is JSON-serializable)
    return jsonify({
        "success": True,
        "data": {
            "audio_b64":   result["audio_b64"],
            "duration_ms": result["duration_ms"],
            "text":        result["text"],
            "format":      result["format"],
        },
    }), 200


@speech_tts_bp.get("/speech/tts/templates")
def tts_templates():
    """Return the list of canned template keys for discoverability."""
    return jsonify({"success": True, "data": {"templates": TEMPLATES}}), 200
