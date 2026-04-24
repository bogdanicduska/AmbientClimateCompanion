import base64
from typing import Dict, Any, Optional

from openai import OpenAI

from app.utils.logger import get_logger

logger = get_logger(__name__)

_client: Optional[OpenAI] = None


def _get_client(config) -> OpenAI:
    """Lazy singleton — avoids re-creating the OpenAI client on every request."""
    global _client
    if _client is None:
        api_key = config.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        _client = OpenAI(api_key=api_key)
    return _client


# Short, ambient-room-assistant voice templates.
# Keep under 2 sentences. Natural prose reads best in nova/shimmer voices.
TEMPLATES: Dict[str, str] = {
    "room_ready":       "The room is ready. Conditions are good for focus right now.",
    "room_recovery":    "Recovery conditions look solid tonight. Temperature and air are both in range.",
    "air_strain_low":   "Air strain is low. The room feels fresh.",
    "air_strain_high":  "Air strain is rising. Consider opening a window.",
    "dry_air":          "The room air is dry right now. Humidity is below 40 percent.",
    "rain_tomorrow":    "Rain is expected tomorrow morning. You may want to bring an umbrella.",
    "weather_alert":    "There is a storm warning for tomorrow. Plan accordingly.",
    "fallback":         "I did not catch that clearly. Try asking about temperature, humidity, or air quality.",
}


def resolve_text(text: Optional[str], template: Optional[str]) -> str:
    """Return the spoken text — template wins if both are provided."""
    if template and template in TEMPLATES:
        return TEMPLATES[template]
    if template and template not in TEMPLATES:
        raise ValueError(f"Unknown template '{template}'. Valid: {sorted(TEMPLATES.keys())}")
    if text:
        return str(text)
    raise ValueError("Either 'text' or a known 'template' must be provided.")


SUPPORTED_TTS_FORMATS = {"mp3", "wav", "opus", "aac", "flac", "pcm"}


def synthesize_speech(text: str, config, audio_format: str = "mp3") -> Dict[str, Any]:
    """Synthesize speech via OpenAI TTS. Returns base64 audio + estimated duration."""
    fmt = (audio_format or "mp3").lower()
    if fmt not in SUPPORTED_TTS_FORMATS:
        raise ValueError(f"Unsupported audio format '{audio_format}'. Supported: {sorted(SUPPORTED_TTS_FORMATS)}")

    client = _get_client(config)

    response = client.audio.speech.create(
        model=config.get("OPENAI_TTS_MODEL", "tts-1"),
        voice=config.get("OPENAI_TTS_VOICE", "nova"),
        input=text,
        response_format=fmt,
        speed=0.95,  # slightly slower → calmer, more ambient
    )

    audio_bytes = response.content
    audio_b64   = base64.b64encode(audio_bytes).decode("utf-8")

    # Rough estimate — OpenAI TTS averages ~160 wpm at 1.0x
    word_count  = max(1, len(text.split()))
    duration_ms = int(word_count / 160.0 * 60.0 * 1000.0 / 0.95)

    logger.info(f"TTS synthesized — fmt={fmt} words={word_count} duration~{duration_ms}ms bytes={len(audio_bytes)}")
    return {
        "audio_b64":   audio_b64,
        "audio_bytes": audio_bytes,
        "duration_ms": duration_ms,
        "text":        text,
        "format":      fmt,
    }
