from flask import Blueprint, jsonify, request, current_app

from app.services.agent_service import answer_question
from app.services.auth_service import is_valid_device_token
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

    # The device plays the answer inline: it reads `answer` from this response,
    # fetches /speech/tts itself, and plays immediately (the I2S0 mic↔speaker
    # handoff is solved on-device, so no decoupling is needed). We deliberately
    # do NOT enqueue the answer for the proactive poll — doing so replayed every
    # answer minutes later as a phantom "proactive" announcement.
    return jsonify({
        "success": True,
        "data":    result,
    }), 200
