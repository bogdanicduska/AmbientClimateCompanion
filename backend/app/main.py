from fastapi import FastAPI

from app.routes import health, ingest, latest

app = FastAPI(
    title="AmbientClimateCompanion API",
    description="Receives sensor data from the M5Stack device and stores it in BigQuery.",
    version="1.0.0",
)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(latest.router)
