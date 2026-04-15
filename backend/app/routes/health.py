from flask import Blueprint, current_app, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    """Liveness check — Cloud Run pings this to verify the service is up."""
    return jsonify({
        "status": "ok",
        "service": current_app.config["APP_NAME"],
        "environment": current_app.config["ENV"],
    }), 200
