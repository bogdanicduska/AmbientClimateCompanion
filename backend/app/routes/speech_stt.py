from flask import Blueprint, jsonify, request, current_app

from app.services.stt_service import transcribe_audio
from app.services.auth_service import is_valid_device_token
from app.utils.validators import validate_stt_payload
from app.utils.logger import get_logger

speech_stt_bp = Blueprint("speech_stt", __name__)
logger = get_logger(__name__)


@speech_stt_bp.post("/speech/stt")
def stt():
    if not is_valid_device_token(current_app.config):
        logger.warning("Auth failed on /speech/stt")
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    is_valid, error = validate_stt_payload(payload)
    if not is_valid:
        logger.warning(f"STT validation failed: {error}")
        return jsonify({"success": False, "message": error}), 400

    audio_format = str(payload.get("format", "wav")).lower()
    logger.info(f"STT — device={payload['device_id']} format={audio_format}")

    try:
        result = transcribe_audio(payload["audio_b64"], audio_format, current_app.config)
        return jsonify({"success": True, "data": result}), 200
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        current_app.logger.exception("STT endpoint failed")
        return jsonify({"success": False, "message": "Internal server error"}), 500
