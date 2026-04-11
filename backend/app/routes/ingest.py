from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import API_KEY
from app.schemas.telemetry import TelemetryPayload
from app.schemas.responses import IngestResponse
from app.services.bigquery_service import insert_record
from app.services.telemetry_service import fetch_outdoor_weather
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/ingest", response_model=IngestResponse)
def ingest(payload: TelemetryPayload):
    """
    Receive sensor data from the M5Stack device and store it in BigQuery.
    The backend enriches the record with outdoor weather from OpenWeatherMap.
    """
    # --- Authentication ---
    if payload.api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # --- Timestamp: use device time if provided, else server UTC ---
    timestamp = payload.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # --- Enrich with outdoor weather ---
    outdoor = fetch_outdoor_weather()

    record = {
        "timestamp":        timestamp,
        "indoor_temp":      payload.indoor_temp,
        "indoor_humidity":  payload.indoor_humidity,
        "indoor_pressure":  payload.indoor_pressure,
        "air_quality":      payload.air_quality,
        "motion":           payload.motion,
        "indoor_eco2":      payload.indoor_eco2,
        **outdoor,
    }

    success = insert_record(record)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to write to BigQuery")

    logger.info(f"Ingested — temp={payload.indoor_temp}°C, humidity={payload.indoor_humidity}%")
    return IngestResponse(status="ok", message="Data stored successfully")
