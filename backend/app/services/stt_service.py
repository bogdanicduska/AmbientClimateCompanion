import base64
import io
import math
from typing import Dict, Any, Optional

from openai import OpenAI

from app.utils.logger import get_logger

logger = get_logger(__name__)

_client: Optional[OpenAI] = None


def _get_client(config) -> OpenAI:
    global _client
    if _client is None:
        api_key = config.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        _client = OpenAI(api_key=api_key)
    return _client


# Domain vocabulary — bias Whisper toward room-intelligence terms via the prompt param.
_DOMAIN_PROMPT = (
    "Questions about room temperature, humidity, air quality, air strain, "
    "recovery, readiness, TVOC, CO2, room state, yesterday, last night, "
    "tomorrow, rain, and umbrella."
)

# Whisper accepts many formats natively; we just need a sensible filename suffix.
_EXT_MAP = {
    "wav":  "wav",
    "raw":  "wav",
    "webm": "webm",
    "mp3":  "mp3",
}


def _pseudo_confidence(segments) -> float:
    """
    Whisper does not return a single confidence score. We derive one from
    avg_logprob per segment. avg_logprob of 0 ≈ perfect, -1.0 ≈ poor.
    Mapping: confidence = clamp(1 + avg_logprob/2, 0..1), weighted by segment length.
    Also penalise with no_speech_prob.
    """
    if not segments:
        return 0.0

    total_len = 0.0
    weighted  = 0.0
    max_nsp   = 0.0
    for seg in segments:
        # Handle both dict-style and attr-style responses
        get = (lambda k, default=0.0: seg.get(k, default)) if isinstance(seg, dict) else (lambda k, default=0.0: getattr(seg, k, default))
        lp      = float(get("avg_logprob", -5.0))
        nsp     = float(get("no_speech_prob", 0.0))
        start   = float(get("start", 0.0))
        end     = float(get("end", start + 0.5))
        length  = max(0.1, end - start)

        seg_conf = max(0.0, min(1.0, 1.0 + lp / 2.0))
        weighted += seg_conf * length
        total_len += length
        if nsp > max_nsp:
            max_nsp = nsp

    base = weighted / total_len if total_len else 0.0
    # If Whisper strongly suspects no speech, tank the confidence
    return round(max(0.0, min(1.0, base * (1.0 - max_nsp))), 3)


def transcribe_audio(audio_b64: str, audio_format: str, config) -> Dict[str, Any]:
    """Decode base64 audio and transcribe via OpenAI Whisper."""
    client = _get_client(config)

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception as exc:
        raise ValueError(f"Invalid base64 audio: {exc}")

    ext = _EXT_MAP.get(audio_format.lower(), "wav")
    buf = io.BytesIO(audio_bytes)
    buf.name = f"audio.{ext}"  # Whisper uses the filename suffix to guess format

    response = client.audio.transcriptions.create(
        model=config.get("OPENAI_STT_MODEL", "whisper-1"),
        file=buf,
        response_format="verbose_json",
        language=config.get("OPENAI_STT_LANGUAGE", "en"),
        prompt=_DOMAIN_PROMPT,
        temperature=0.0,
    )

    transcript = (getattr(response, "text", "") or "").strip()
    segments   = getattr(response, "segments", None) or []
    confidence = _pseudo_confidence(segments)

    logger.info(f"STT transcript={transcript!r} confidence={confidence}")
    return {"transcript": transcript, "confidence": confidence}
