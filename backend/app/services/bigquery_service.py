from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from google.cloud import bigquery

from app.utils.logger import get_logger

logger = get_logger(__name__)

_COLUMNS = """
    device_id, timestamp, indoor_temp, indoor_humidity,
    air_quality, air_quality_label, motion, wifi_rssi,
    indoor_pressure, indoor_eco2,
    outdoor_temp, outdoor_humidity, outdoor_weather, outdoor_icon,
    weather_status, ingested_at, sync_status
"""


def get_bigquery_client() -> bigquery.Client:
    """Create and return a BigQuery client."""
    return bigquery.Client()


def _table_ref(config) -> str:
    return f"{config['GCP_PROJECT_ID']}.{config['BIGQUERY_DATASET']}.{config['BIGQUERY_TABLE']}"


def _row_to_dict(r) -> Dict[str, Any]:
    return {
        "device_id":         r.device_id,
        "timestamp":         r.timestamp.isoformat() if r.timestamp else None,
        "indoor_temp":       r.indoor_temp,
        "indoor_humidity":   r.indoor_humidity,
        "air_quality":       r.air_quality,
        "air_quality_label": r.air_quality_label,
        "motion":            r.motion,
        "wifi_rssi":         r.wifi_rssi,
        "indoor_pressure":   r.indoor_pressure,
        "indoor_eco2":       r.indoor_eco2,
        "outdoor_temp":      r.outdoor_temp,
        "outdoor_humidity":  r.outdoor_humidity,
        "outdoor_weather":   r.outdoor_weather,
        "outdoor_icon":      r.outdoor_icon,
        "weather_status":    r.weather_status,
        "ingested_at":       r.ingested_at.isoformat() if r.ingested_at else None,
        "sync_status":       r.sync_status,
    }


def insert_telemetry_row(row: Dict[str, Any], config) -> None:
    """
    Insert a single telemetry record into BigQuery using the streaming insert API.
    Raises RuntimeError with a meaningful message on failure.
    """
    client = get_bigquery_client()
    table = _table_ref(config)
    errors = client.insert_rows_json(table, [row])

    if errors:
        raise RuntimeError(f"BigQuery insert failed for table {table}: {errors}")

    logger.info(f"Record inserted: {row.get('timestamp')} — device: {row.get('device_id')}")


def _events_table_ref(config) -> str:
    return f"{config['GCP_PROJECT_ID']}.{config['BIGQUERY_DATASET']}.device_events"


def insert_event_row(row: Dict[str, Any], config) -> None:
    client = get_bigquery_client()
    table = _events_table_ref(config)
    errors = client.insert_rows_json(table, [row])

    if errors:
        raise RuntimeError(f"BigQuery event insert failed for table {table}: {errors}")

    logger.info(f"Event inserted: {row.get('event_type')} — device: {row.get('device_id')}")


def get_latest_reading(device_id: str, config) -> Optional[Dict]:
    """Return the most recent row for a given device, ordered by measurement timestamp."""
    client = get_bigquery_client()

    query = f"""
    SELECT {_COLUMNS}
    FROM `{_table_ref(config)}`
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
        return _row_to_dict(rows[0]) if rows else None
    except Exception as e:
        logger.error(f"BigQuery get_latest_reading failed: {e}")
        raise


def get_history(device_id: str, config, hours: int = 24) -> List[Dict]:
    """
    Return records for a device from the last N hours sorted ascending by timestamp.
    Default window is 24 hours.
    """
    client = get_bigquery_client()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    query = f"""
    SELECT {_COLUMNS}
    FROM `{_table_ref(config)}`
    WHERE device_id = @device_id
      AND timestamp >= @since
    ORDER BY timestamp ASC
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("device_id", "STRING", device_id),
            bigquery.ScalarQueryParameter("since", "TIMESTAMP", since),
        ]
    )

    try:
        rows = list(client.query(query, job_config=job_config).result())
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f"BigQuery get_history failed: {e}")
        raise


def get_history_window(device_id: str, config, start_iso: str, end_iso: str) -> List[Dict]:
    """Return records for a device between two explicit UTC timestamps, ascending."""
    client = get_bigquery_client()

    query = f"""
    SELECT {_COLUMNS}
    FROM `{_table_ref(config)}`
    WHERE device_id = @device_id
      AND timestamp >= @start
      AND timestamp <= @end
    ORDER BY timestamp ASC
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("device_id", "STRING", device_id),
            bigquery.ScalarQueryParameter("start", "TIMESTAMP", start_iso),
            bigquery.ScalarQueryParameter("end", "TIMESTAMP", end_iso),
        ]
    )

    try:
        rows = list(client.query(query, job_config=job_config).result())
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f"BigQuery get_history_window failed: {e}")
        raise


def get_recent_speech_events(device_id: str, event_type: str, config, hours: int) -> List[Dict]:
    """Return recent device_events rows for cooldown checks in the proactive service."""
    client = get_bigquery_client()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    query = f"""
    SELECT event_type, timestamp, details
    FROM `{_events_table_ref(config)}`
    WHERE device_id = @device_id
      AND event_type = @event_type
      AND timestamp >= @since
    ORDER BY timestamp DESC
    LIMIT 10
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("device_id", "STRING", device_id),
            bigquery.ScalarQueryParameter("event_type", "STRING", event_type),
            bigquery.ScalarQueryParameter("since", "TIMESTAMP", since),
        ]
    )

    try:
        rows = list(client.query(query, job_config=job_config).result())
        return [{"event_type": r.event_type, "timestamp": r.timestamp.isoformat(), "details": r.details} for r in rows]
    except Exception as e:
        logger.error(f"BigQuery get_recent_speech_events failed: {e}")
        raise
