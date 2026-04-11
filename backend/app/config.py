import os
from dotenv import load_dotenv

load_dotenv()

# Google Cloud / BigQuery
GCP_PROJECT_ID    = os.getenv("GCP_PROJECT_ID", "cloud-lab-weather")
BIGQUERY_DATASET  = os.getenv("BIGQUERY_DATASET", "ambient_climate")
BIGQUERY_TABLE    = os.getenv("BIGQUERY_TABLE", "weather_records")
BQ_TABLE_REF      = f"{GCP_PROJECT_ID}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}"

# OpenWeatherMap
OPENWEATHER_API_KEY      = os.getenv("OPENWEATHER_API_KEY", "")
OPENWEATHER_CITY         = os.getenv("OPENWEATHER_CITY", "Lausanne")
OPENWEATHER_URL          = "https://api.openweathermap.org/data/2.5/weather"

# Simple shared API key — the M5Stack sends this with every request
API_KEY = os.getenv("API_KEY", "changeme")

# Server
PORT = int(os.getenv("PORT", 8080))
