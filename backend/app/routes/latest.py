from fastapi import APIRouter, HTTPException, Query

from app.services.bigquery_service import get_latest, get_history
from app.schemas.responses import WeatherRecord, HistoryResponse
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/latest", response_model=WeatherRecord)
def latest():
    """
    Return the most recent record from BigQuery.
    The M5Stack calls this on startup to pre-fill the screen
    even before the first new reading arrives.
    """
    record = get_latest()
    if record is None:
        raise HTTPException(status_code=404, detail="No records found in BigQuery yet")
    return record


@router.get("/history", response_model=HistoryResponse)
def history(days: int = Query(default=7, ge=1, le=30)):
    """
    Return all records from the last N days.
    Used by the speech layer to answer questions like
    'what was the temperature yesterday?'
    """
    records = get_history(days=days)
    return HistoryResponse(count=len(records), records=records)
