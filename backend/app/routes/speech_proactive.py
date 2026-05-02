import base64

from flask import Blueprint, Response, jsonify, request, current_app

from app.services.events_service import store_device_event
from app.services.pending_audio_service import dequeue as dequeue_audio
from app.services.proactive_service import evaluate_proactive
from app.services.tts_service import synthesize_speech
from app.utils.logger import get_logger

speech_proactive_bp = Blueprint("speech_proactive", __name__)
logger = get_logger(__name__)


def _raw_response(audio_bytes: bytes, *, source: str, trigger_id: str, text: str) -> Response:
    """Return WAV bytes with metadata in headers — for the M5Stack which can't
    afford to decode base64 in JSON (heap pressure on a ~110KB device)."""
    return Response(
        audio_bytes,
        status=200,
        mimetype="audio/wav",
        headers={
            "X-Source":     source,
            "X-Trigger-Id": trigger_id,
            "X-Text":       text[:200],
        },
    )


@speech_proactive_bp.get("/speech/proactive")
def proactive():
    """Return one pending audio item for the device.

    Order of precedence:
      1. Pending ASK answers (queued by /speech/ask).
      2. Proactive triggers (weather/umbrella/etc) — same logic as before, with cooldowns.

    Modes:
      ?raw=1     → binary WAV body, metadata in X-* headers, 204 if nothing.
      (default)  → JSON body with audio_b64 (legacy clients).
      ?dry_run=1 → evaluate triggers but don't synthesize/log cooldown.
      ?force=ID  → bypass condition + cooldown (skips the queue too).
    """
    device_id = request.args.get("device_id")
    if not device_id:
        return jsonify({"success": False, "message": "device_id is required"}), 400

    raw     = request.args.get("raw", "0") in ("1", "true", "yes")
    dry_run = request.args.get("dry_run", "0") in ("1", "true", "yes")
    force   = request.args.get("force")

    # 1. Pending ASK answer queue — direct user questions take priority over
    #    proactive triggers. Skipped on force/dry_run so demos still work.
    if not force and not dry_run:
        pending = dequeue_audio(device_id)
        if pending:
            logger.info(f"Proactive draining ASK answer for device={device_id} trigger={pending.get('trigger_id')}")
            audio_bytes = pending.get("audio_bytes") or b""
            text        = pending.get("text") or ""
            trigger_id  = pending.get("trigger_id") or "ask_unknown"
            source      = pending.get("source") or "ask"
            if raw:
                return _raw_response(audio_bytes, source=source, trigger_id=trigger_id, text=text)
            return jsonify({
                "success": True,
                "data": {
                    "announce":   True,
                    "source":     source,
                    "trigger_id": trigger_id,
                    "text":       text,
                    "audio_b64":  base64.b64encode(audio_bytes).decode("utf-8"),
                },
            }), 200

    # 2. Proactive trigger evaluation
    try:
        trigger = evaluate_proactive(device_id, current_app.config, force_trigger=force)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        current_app.logger.exception(f"Proactive evaluation failed for {device_id}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

    if not trigger:
        if raw:
            return ("", 204)
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

    # Synthesize the spoken audio. Use WAV for raw mode (device plays WAV),
    # default mp3 for the JSON path to preserve legacy client behavior.
    try:
        audio_format = "wav" if raw else "mp3"
        tts = synthesize_speech(trigger["text"], current_app.config, audio_format=audio_format)
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

    if raw:
        return _raw_response(
            tts["audio_bytes"],
            source="proactive",
            trigger_id=trigger["trigger_id"],
            text=trigger["text"],
        )

    return jsonify({
        "success": True,
        "data": {
            "announce":    True,
            "forced":      bool(trigger.get("forced")),
            "source":      "proactive",
            "trigger_id":  trigger["trigger_id"],
            "text":        trigger["text"],
            "audio_b64":   tts["audio_b64"],
            "duration_ms": tts["duration_ms"],
            "snapshot":    trigger["snapshot"],
        },
    }), 200
