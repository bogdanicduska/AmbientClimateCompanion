from flask import Flask

from app.config import Config
from app.routes.health import health_bp
from app.routes.telemetry import telemetry_bp
from app.routes.latest import latest_bp
from app.routes.history import history_bp
from app.routes.weather import weather_bp
from app.routes.events import events_bp
from app.routes.forecast import forecast_bp
from app.routes.speech_ask import speech_ask_bp
from app.routes.speech_tts import speech_tts_bp
from app.routes.speech_stt import speech_stt_bp
from app.routes.speech_query import speech_query_bp
from app.routes.speech_proactive import speech_proactive_bp
from app.routes.speech_meditation import speech_meditation_bp
from app.routes.daily_summary import daily_summary_bp
from app.utils.logger import configure_logging


def _validate_config(cfg) -> None:
    """Fail fast at startup if critical config is missing."""
    missing = []
    if not cfg.get("OPENWEATHER_API_KEY"):
        missing.append("OPENWEATHER_API_KEY")
    if not cfg.get("DEVICE_AUTH_TOKEN") or cfg.get("DEVICE_AUTH_TOKEN") in ("changeme", "change_me_before_deploy"):
        missing.append("DEVICE_AUTH_TOKEN (still set to placeholder)")
    if not cfg.get("GCP_PROJECT_ID"):
        missing.append("GCP_PROJECT_ID")
    if missing:
        import warnings
        warnings.warn(
            f"Room Rhythm: missing or placeholder config values: {', '.join(missing)}. "
            "Some features may fail at runtime.",
            stacklevel=2,
        )


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    configure_logging(app)
    _validate_config(app.config)

    app.register_blueprint(health_bp)
    app.register_blueprint(telemetry_bp, url_prefix="/api/v1")
    app.register_blueprint(latest_bp, url_prefix="/api/v1")
    app.register_blueprint(history_bp, url_prefix="/api/v1")
    app.register_blueprint(weather_bp, url_prefix="/api/v1")
    app.register_blueprint(events_bp, url_prefix="/api/v1")
    app.register_blueprint(forecast_bp, url_prefix="/api/v1")
    app.register_blueprint(speech_ask_bp, url_prefix="/api/v1")
    app.register_blueprint(speech_tts_bp, url_prefix="/api/v1")
    app.register_blueprint(speech_stt_bp, url_prefix="/api/v1")
    app.register_blueprint(speech_query_bp, url_prefix="/api/v1")
    app.register_blueprint(speech_proactive_bp, url_prefix="/api/v1")
    app.register_blueprint(speech_meditation_bp, url_prefix="/api/v1")
    app.register_blueprint(daily_summary_bp, url_prefix="/api/v1")

    @app.route("/")
    def index():
        return {
            "service": app.config["APP_NAME"],
            "version": "0.1.0",
            "status": "running",
        }, 200

    return app
