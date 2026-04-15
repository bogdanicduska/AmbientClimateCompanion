from datetime import datetime, timezone


def utc_now_str() -> str:
    """Return the current UTC time as a BigQuery-compatible string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
