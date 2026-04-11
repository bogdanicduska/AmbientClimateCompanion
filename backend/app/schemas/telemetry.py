from pydantic import BaseModel
from typing import Optional


class TelemetryPayload(BaseModel):
    """Data sent by the M5Stack device every 5 minutes."""
    api_key: str
    indoor_temp: float
    indoor_humidity: float
    indoor_pressure: Optional[float] = None
    air_quality: Optional[float] = None
    motion: Optional[bool] = None
    indoor_eco2: Optional[float] = None
    # ISO timestamp from device NTP, e.g. "2026-04-10T14:32:00"
    # If not provided, the server uses its own UTC time.
    timestamp: Optional[str] = None
