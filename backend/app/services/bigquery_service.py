from google.cloud import bigquery
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

from app.config import GCP_PROJECT_ID, BQ_TABLE_REF
from app.utils.logger import get_logger

logger = get_logger(__name__)

# BigQuery client — on Cloud Run this uses the service account automatically.
# Locally, set GOOGLE_APPLICATION_CREDENTIALS to your service account key JSON.
client = bigquery.Client(project=GCP_PROJECT_ID)


def insert_record(data: dict) -> bool:
    """Insert a single telemetry record into BigQuery."""

    def sql_val(v):
        """Format a Python value as a SQL literal."""
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, str):
            return f"'{v}'"
        return str(v)

    query = f"""
    INSERT INTO `{BQ_TABLE_REF}`
      (timestamp, indoor_temp, indoor_humidity, indoor_pressure,
       air_quality, motion, outdoor_temp, outdoor_humidity,
       outdoor_weather, outdoor_icon)
    VALUES (
      '{data["timestamp"]}',
      {sql_val(data.get("indoor_temp"))},
      {sql_val(data.get("indoor_humidity"))},
      {sql_val(data.get("indoor_pressure"))},
      {sql_val(data.get("air_quality"))},
      {sql_val(data.get("motion"))},
      {sql_val(data.get("outdoor_temp"))},
      {sql_val(data.get("outdoor_humidity"))},
      {sql_val(data.get("outdoor_weather"))},
      {sql_val(data.get("outdoor_icon"))}
    )
    """
    try:
        client.query(query).result()
        logger.info(f"Record inserted: {data['timestamp']}")
        return True
    except Exception as e:
        logger.error(f"BigQuery insert failed: {e}")
        return False


def get_latest() -> Optional[Dict]:
    """Return the most recent row — used by the device on startup."""
    query = f"""
    SELECT * FROM `{BQ_TABLE_REF}`
    ORDER BY timestamp DESC
    LIMIT 1
    """
    try:
        rows = list(client.query(query).result())
        if not rows:
            return None
        row = dict(rows[0])
        row["timestamp"] = str(row["timestamp"])
        return row
    except Exception as e:
        logger.error(f"BigQuery get_latest failed: {e}")
        return None


def get_history(days: int = 7) -> List[Dict]:
    """Return all records from the last N days — used by the speech layer."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    query = f"""
    SELECT * FROM `{BQ_TABLE_REF}`
    WHERE timestamp >= '{since}'
    ORDER BY timestamp DESC
    """
    try:
        rows = list(client.query(query).result())
        records = []
        for row in rows:
            r = dict(row)
            r["timestamp"] = str(r["timestamp"])
            records.append(r)
        return records
    except Exception as e:
        logger.error(f"BigQuery get_history failed: {e}")
        return []
