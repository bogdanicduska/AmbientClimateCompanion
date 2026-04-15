from flask import Flask

from app.config import Config
from app.routes.health import health_bp
from app.routes.telemetry import telemetry_bp
from app.routes.latest import latest_bp
from app.utils.logger import configure_logging


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    configure_logging(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(telemetry_bp, url_prefix="/api/v1")
    app.register_blueprint(latest_bp, url_prefix="/api/v1")

    @app.route("/")
    def index():
        return {
            "service": app.config["APP_NAME"],
            "version": "0.1.0",
            "status": "running",
        }, 200

    return app
