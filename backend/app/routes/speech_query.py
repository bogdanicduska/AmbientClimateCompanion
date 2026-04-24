from flask import Blueprint, jsonify, request, current_app

from app.services.speech_pipeline_service import run_speech_query
from app.services.events_service import store_device_event
from app.services.auth_service import is_valid_device_token
from app.utils.validators import validate_query_payload
from app.utils.logger import get_logger

speech_query_bp = Blueprint("speech_query", __name__)
logger = get_logger(__name__)


@speech_query_bp.post("/speech/query")
def query():
    if not is_valid_device_token(current_app.config):
        logger.warning("Auth failed on /speech/query")
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    is_valid, error = validate_query_payload(payload)
    if not is_valid:
        logger.warning(f"Query validation failed: {error}")
        return jsonify({"success": False, "message": error}), 400

    device_id     = payload["device_id"]
    audio_format  = str(payload.get("format", "wav")).lower()
    output_format = str(payload.get("output_format", "mp3")).lower()
    logger.info(f"QUERY — device={device_id} in={audio_format} out={output_format}")

    try:
        result = run_speech_query(device_id, payload["audio_b64"], audio_format, current_app.config, output_format=output_format)
    except Exception:
        current_app.logger.exception("Speech query pipeline failed")
        return jsonify({"success": False, "message": "Internal server error"}), 500

    # Audit log — fire-and-forget (never fail the response on a logging error)
    try:
        store_device_event(
            {
                "device_id":  device_id,
                "event_type": "speech_query_received",
                "details":    {
                    "transcript": result.get("transcript"),
                    "intent":     result.get("intent"),
                    "confidence": result.get("confidence"),
                },
            },
            current_app.config,
        )
    except Exception as exc:
        logger.warning(f"speech_query_received event log failed (non-fatal): {exc}")

    return jsonify({"success": True, "data": result}), 200
