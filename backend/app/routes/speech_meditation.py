from flask import Blueprint, current_app, jsonify, request

from app.services.auth_service import is_valid_device_token
from app.services.meditation_service import get_session, list_sessions
from app.utils.logger import get_logger

speech_meditation_bp = Blueprint("speech_meditation", __name__)
logger = get_logger(__name__)


@speech_meditation_bp.get("/speech/meditation/sessions")
def list_meditation_sessions():
    """Catalog of available sessions — id / title / subtitle / duration."""
    if not is_valid_device_token(current_app.config):
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    return jsonify({"success": True, "data": list_sessions()}), 200


@speech_meditation_bp.get("/speech/meditation")
def get_meditation_session():
    """Return one session's full config (incl. timed prompts).
    Defaults to 'calm' if no session id is given."""
    if not is_valid_device_token(current_app.config):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    session_id = request.args.get("session", "").strip() or None
    session = get_session(session_id)
    if session is None:
        logger.info(f"Meditation session not found: {session_id!r}")
        return jsonify({"success": False, "message": "Unknown session"}), 404

    return jsonify({"success": True, "data": session}), 200
