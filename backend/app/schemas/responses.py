from pydantic import BaseModel
from typing import Optional, List


class IngestResponse(BaseModel):
    status: str
    message: str


class WeatherRecord(BaseModel):
    timestamp: Optional[str] = None
    indoor_temp: Optional[float] = None
    indoor_humidity: Optional[float] = None
    indoor_pressure: Optional[float] = None
    air_quality: Optional[float] = None
    motion: Optional[bool] = None
    outdoor_temp: Optional[float] = None
    outdoor_humidity: Optional[float] = None
    outdoor_weather: Optional[str] = None
    outdoor_icon: Optional[str] = None


class HistoryResponse(BaseModel):
    count: int
    records: List[WeatherRecord]
