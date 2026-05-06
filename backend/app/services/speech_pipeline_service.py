from typing import Dict, Any, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Pre-synthesized fallback audio — cached on first use so failures are always fast.
_fallback_cache: Optional[Dict[str, Any]] = None


_FALLBACK_TEXT = (
    "I did not catch that clearly. Try asking about temperature, humidity, or air quality."
)


def _get_fallback(config) -> Dict[str, Any]:
    global _fallback_cache
    if _fallback_cache is None:
        from app.services.tts_service import synthesize_speech
        try:
            _fallback_cache = synthesize_speech(_FALLBACK_TEXT, config)
        except Exception as exc:
            logger.error(f"Fallback TTS synthesis failed: {exc}")
            # Return silent fallback — empty audio but still valid JSON response
            _fallback_cache = {"audio_b64": "", "duration_ms": 0, "text": _FALLBACK_TEXT}
    return _fallback_cache


def _fallback_response(config, transcript: str = "", confidence: float = 0.0, reason: str = "unclear") -> Dict[str, Any]:
    fb = _get_fallback(config)
    return {
        "transcript":    transcript,
        "confidence":    confidence,
        "intent":        reason,
        "answer":        _FALLBACK_TEXT,
        "data_snapshot": {},
        "audio_b64":     fb["audio_b64"],
        "duration_ms":   fb["duration_ms"],
    }


def run_speech_query(device_id: str, audio_b64: str, audio_format: str, config, output_format: str = "mp3") -> Dict[str, Any]:
    """End-to-end: audio in → transcript → answer → audio out."""
    from app.services.stt_service import transcribe_audio
    from app.services.agent_service import answer_question
    from app.services.tts_service import synthesize_speech

    # --- STT ---
    try:
        stt = transcribe_audio(audio_b64, audio_format, config)
    except Exception as exc:
        logger.error(f"Pipeline STT failed: {exc}")
        return _fallback_response(config, reason="stt_error")

    if not stt.get("transcript") or stt.get("confidence", 0.0) < 0.60:
        logger.info(f"Pipeline routed to fallback (confidence={stt.get('confidence')})")
        return _fallback_response(
            config,
            transcript=stt.get("transcript", ""),
            confidence=stt.get("confidence", 0.0),
            reason="unclear",
        )

    # --- ASK ---
    ask = answer_question(device_id, stt["transcript"], config)

    if ask["intent"] == "unknown":
        logger.info(f"Pipeline routed to fallback (unknown intent for {stt['transcript']!r})")
        return _fallback_response(
            config,
            transcript=stt["transcript"],
            confidence=stt["confidence"],
            reason="unknown",
        )

    # --- TTS ---
    try:
        tts = synthesize_speech(ask["answer"], config, audio_format=output_format)
    except Exception as exc:
        logger.error(f"Pipeline TTS failed: {exc}")
        # Return text-only answer if TTS breaks — still useful
        tts = {"audio_b64": "", "duration_ms": 0, "text": ask["answer"]}

    return {
        "transcript":    stt["transcript"],
        "confidence":    stt["confidence"],
        "intent":        ask["intent"],
        "answer":        ask["answer"],
        "data_snapshot": ask["data_snapshot"],
        "audio_b64":     tts["audio_b64"],
        "duration_ms":   tts["duration_ms"],
    }
