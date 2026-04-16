from flask import Blueprint, current_app, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    """Liveness check — Cloud Run pings this to verify the service is up."""
    config = current_app.config
    return jsonify({
        "status":              "ok",
        "service":             config["APP_NAME"],
        "environment":         config["ENV"],
        "bigquery_configured": bool(config.get("GCP_PROJECT_ID") and config.get("BIGQUERY_DATASET") and config.get("BIGQUERY_TABLE")),
        "weather_configured":  bool(config.get("OPENWEATHER_API_KEY")),
    }), 200
