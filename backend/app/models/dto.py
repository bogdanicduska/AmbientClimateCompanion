from pydantic import BaseModel
from typing import Optional


class TelemetryPayload(BaseModel):
    """Data sent by the M5Stack device every 5 minutes."""
    device_id: str
    timestamp: Optional[str] = None   # ISO-8601 from device NTP; server UTC used if absent
    indoor_temp: float
    indoor_humidity: float
    air_quality: Optional[float] = None
    motion: Optional[bool] = None
    wifi_rssi: Optional[int] = None
    indoor_pressure: Optional[float] = None
    indoor_eco2: Optional[float] = None
