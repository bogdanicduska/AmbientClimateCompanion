import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # App
    APP_NAME = os.getenv("APP_NAME", "AmbientClimateCompanion API")
    ENV      = os.getenv("APP_ENV", "development")
    DEBUG    = os.getenv("APP_DEBUG", "false").lower() == "true"

    # Google Cloud / BigQuery
    GCP_PROJECT_ID   = os.getenv("GCP_PROJECT_ID", "cloud-lab-weather")
    BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "ambient_climate")
    BIGQUERY_TABLE   = os.getenv("BIGQUERY_TABLE", "weather_records")

    @classmethod
    def bq_table_ref(cls) -> str:
        return f"{cls.GCP_PROJECT_ID}.{cls.BIGQUERY_DATASET}.{cls.BIGQUERY_TABLE}"

    # OpenWeatherMap
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
    OPENWEATHER_CITY    = os.getenv("OPENWEATHER_CITY", "Lausanne")
    OPENWEATHER_URL     = "https://api.openweathermap.org/data/2.5/weather"

    # Shared secret between the M5Stack device and this backend
    DEVICE_AUTH_TOKEN = os.getenv("DEVICE_AUTH_TOKEN", "changeme")

    # Google credentials (local dev only — on Cloud Run the service account is injected automatically)
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    # Server
    PORT = int(os.getenv("PORT", 8080))
