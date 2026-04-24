from flask import Blueprint, jsonify, request, current_app

from app.services.proactive_service import evaluate_proactive
from app.services.tts_service import synthesize_speech
from app.services.events_service import store_device_event
from app.utils.logger import get_logger

speech_proactive_bp = Blueprint("speech_proactive", __name__)
logger = get_logger(__name__)


@speech_proactive_bp.get("/speech/proactive")
def proactive():
    """Return at most one pending proactive announcement for the device, respecting cooldowns."""
    device_id = request.args.get("device_id")
    if not device_id:
        return jsonify({"success": False, "message": "device_id is required"}), 400

    # Optional ?dry_run=1 — evaluates triggers but does not synthesize audio or log cooldown
    dry_run = request.args.get("dry_run", "0") in ("1", "true", "yes")
    # Optional ?force=<trigger_id> — bypass condition + cooldown (demos/tests only)
    force = request.args.get("force")

    try:
        trigger = evaluate_proactive(device_id, current_app.config, force_trigger=force)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        current_app.logger.exception(f"Proactive evaluation failed for {device_id}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

    if not trigger:
        return jsonify({"success": True, "data": {"announce": False}}), 200

    if dry_run:
        logger.info(f"Proactive dry-run — trigger={trigger['trigger_id']}")
        return jsonify({
            "success": True,
            "data": {
                "announce":   True,
                "dry_run":    True,
                "trigger_id": trigger["trigger_id"],
                "text":       trigger["text"],
                "snapshot":   trigger["snapshot"],
            },
        }), 200

    # Synthesize the spoken audio
    try:
        tts = synthesize_speech(trigger["text"], current_app.config)
    except Exception:
        current_app.logger.exception(f"Proactive TTS failed for trigger={trigger['trigger_id']}")
        return jsonify({"success": False, "message": "TTS failure"}), 500

    # Log the event so the cooldown check sees it next time.
    # Forced (demo) runs do NOT log — they would otherwise suppress real triggers.
    if not trigger.get("forced"):
        try:
            store_device_event(
                {
                    "device_id":  device_id,
                    "event_type": "speech_summary_spoken",
                    "details":    {
                        "trigger_id": trigger["trigger_id"],
                        "text":       trigger["text"],
                    },
                },
                current_app.config,
            )
        except Exception as exc:
            logger.warning(f"speech_summary_spoken event log failed (non-fatal): {exc}")

    return jsonify({
        "success": True,
        "data": {
            "announce":    True,
            "forced":      bool(trigger.get("forced")),
            "trigger_id":  trigger["trigger_id"],
            "text":        trigger["text"],
            "audio_b64":   tts["audio_b64"],
            "duration_ms": tts["duration_ms"],
            "snapshot":    trigger["snapshot"],
        },
    }), 200
