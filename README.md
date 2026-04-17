# AmbientClimateCompanion

An IoT system that collects indoor climate data from an M5Stack device, enriches it with live outdoor weather, stores it in Google BigQuery, and exposes it through a REST API.

---

## What has been built

### Device — M5Stack sensor (`device/`)
- M5Stack project (`main_project.m5f`) that reads indoor sensors every 5 minutes
- Captures: temperature, humidity, air quality, eCO2, atmospheric pressure, motion, Wi-Fi RSSI
- Authenticates with the backend using a shared device token
- Sends telemetry to the backend `/telemetry` endpoint over Wi-Fi

### Backend — Flask REST API (`backend/`)
Python 3.11 / Flask application containerised with Docker, designed to run on Google Cloud Run.

**API endpoints**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/telemetry` | Receive sensor payload from M5Stack, enrich with outdoor weather, insert into BigQuery |
| `GET` | `/latest?device_id=` | Return the most recent record for a device |
| `GET` | `/history?device_id=&hours=` | Return records for the last N hours (default 24, max 168) |
| `GET` | `/weather` | Return current outdoor weather from OpenWeatherMap |
| `GET` | `/health` | Liveness check used by Cloud Run |

**Services**
- `telemetry_service` — normalises the device payload, derives `air_quality_label` (Good / Moderate / Poor / Hazardous), fetches outdoor weather, and writes the enriched record to BigQuery
- `bigquery_service` — streaming inserts and parameterised queries against the `weather_records` table
- `weather_service` — fetches current outdoor weather from OpenWeatherMap and maps it into `outdoor_temp`, `outdoor_humidity`, `outdoor_weather`, `outdoor_icon`, `weather_status`
- `auth_service` — validates the shared device token on ingest requests

**Data stored per record**

Indoor: `device_id`, `timestamp`, `indoor_temp`, `indoor_humidity`, `air_quality`, `air_quality_label`, `motion`, `wifi_rssi`, `indoor_pressure`, `indoor_eco2`  
Outdoor (enriched at ingest): `outdoor_temp`, `outdoor_humidity`, `outdoor_weather`, `outdoor_icon`, `weather_status`  
Metadata: `ingested_at`, `sync_status`

**Infrastructure**
- Dockerfile — single-container image, runs with Gunicorn (1 worker, 8 threads) on port 8080
- GCP project: `cloud-lab-weather`, dataset: `ambient_climate`, table: `weather_records`
- Config driven by environment variables (`.env.example` provided)
- Logging via a shared logger utility

**Tests & scripts**
- Unit tests: `tests/test_health.py`, `tests/test_telemetry.py`
- Manual scripts: `scripts/send_fake_telemetry.py`, `scripts/test_history.py`, `scripts/test_latest.py`, `scripts/test_payloads.py`

### Dashboard (`dashboard/`)
Folder structure in place (`pages/`, `components/`, `assets/`) — frontend not yet implemented.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Device | M5Stack (UIFlow / MicroPython) |
| Backend | Python 3.11, Flask, Pydantic |
| Database | Google BigQuery |
| Outdoor weather | OpenWeatherMap API |
| Container | Docker, Gunicorn |
| Hosting | Google Cloud Run |

---

## Tagged versions

| Tag | State |
|-----|-------|
| `v2` | Stable — Flask backend fully functional with BigQuery and OpenWeatherMap integration |
