from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from google.cloud import bigquery

from app.utils.logger import get_logger

logger = get_logger(__name__)


def get_bigquery_client() -> bigquery.Client:
    """Create and return a BigQuery client."""
    return bigquery.Client()


def _table_ref(config) -> str:
    return f"{config['GCP_PROJECT_ID']}.{config['BIGQUERY_DATASET']}.{config['BIGQUERY_TABLE']}"


def insert_indoor_reading(row: Dict[str, Any], config) -> None:
    """
    Insert a single telemetry record into BigQuery using the streaming insert API.
    Raises RuntimeError on failure so the route layer can return a 500.
    """
    client = get_bigquery_client()
    errors = client.insert_rows_json(_table_ref(config), [row])

    if errors:
        raise RuntimeError(f"BigQuery insert failed: {errors}")

    logger.info(f"Record inserted: {row.get('timestamp')}")


def get_latest_reading(device_id: str, config) -> Optional[Dict]:
    """Return the most recent row for a given device."""
    client = get_bigquery_client()
    table = _table_ref(config)

    query = f"""
    SELECT
        device_id, timestamp, indoor_temp, indoor_humidity,
        air_quality, motion, wifi_rssi, indoor_pressure, indoor_eco2,
        outdoor_temp, outdoor_humidity, outdoor_weather, outdoor_icon,
        ingested_at
    FROM `{table}`
    WHERE device_id = @device_id
    ORDER BY timestamp DESC
    LIMIT 1
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("device_id", "STRING", device_id)
        ]
    )

    try:
        rows = list(client.query(query, job_config=job_config).result())
        if not rows:
            return None
        row = rows[0]
        return {
            "device_id":       row.device_id,
            "timestamp":       row.timestamp.isoformat() if row.timestamp else None,
            "indoor_temp":     row.indoor_temp,
            "indoor_humidity": row.indoor_humidity,
            "air_quality":     row.air_quality,
            "motion":          row.motion,
            "wifi_rssi":       row.wifi_rssi,
            "indoor_pressure": row.indoor_pressure,
            "indoor_eco2":     row.indoor_eco2,
            "outdoor_temp":    row.outdoor_temp,
            "outdoor_humidity":row.outdoor_humidity,
            "outdoor_weather": row.outdoor_weather,
            "outdoor_icon":    row.outdoor_icon,
            "ingested_at":     row.ingested_at.isoformat() if row.ingested_at else None,
        }
    except Exception as e:
        logger.error(f"BigQuery get_latest_reading failed: {e}")
        raise


def get_history(device_id: str, config, days: int = 7) -> List[Dict]:
    """Return all records for a device from the last N days."""
    client = get_bigquery_client()
    table = _table_ref(config)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    query = f"""
    SELECT
        device_id, timestamp, indoor_temp, indoor_humidity,
        air_quality, motion, wifi_rssi, indoor_pressure, indoor_eco2,
        outdoor_temp, outdoor_humidity, outdoor_weather, outdoor_icon,
        ingested_at
    FROM `{table}`
    WHERE device_id = @device_id
      AND timestamp >= @since
    ORDER BY timestamp DESC
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("device_id", "STRING", device_id),
            bigquery.ScalarQueryParameter("since", "TIMESTAMP", since),
        ]
    )

    try:
        rows = list(client.query(query, job_config=job_config).result())
        return [
            {
                "device_id":       r.device_id,
                "timestamp":       r.timestamp.isoformat() if r.timestamp else None,
                "indoor_temp":     r.indoor_temp,
                "indoor_humidity": r.indoor_humidity,
                "air_quality":     r.air_quality,
                "motion":          r.motion,
                "wifi_rssi":       r.wifi_rssi,
                "indoor_pressure": r.indoor_pressure,
                "indoor_eco2":     r.indoor_eco2,
                "outdoor_temp":    r.outdoor_temp,
                "outdoor_humidity":r.outdoor_humidity,
                "outdoor_weather": r.outdoor_weather,
                "outdoor_icon":    r.outdoor_icon,
                "ingested_at":     r.ingested_at.isoformat() if r.ingested_at else None,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"BigQuery get_history failed: {e}")
        raise
