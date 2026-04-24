# AmbientClimateCompanion — WHOOP for Room

A room-performance system that continuously senses how supportive a space is for focus, calm, comfort, and recovery.

We treat the room like a living environment with performance states. Rather than displaying raw sensor values, the system derives four human-readable metrics that describe how the room *feels* right now.

> These metrics do not claim to measure human biology directly. They are environmental interpretation metrics based on indoor climate, air quality, occupancy, and weather context, designed to describe how supportive the space may feel for comfort, focus, calm, and recovery.

---

## Core Metrics

### 1. Room Readiness
Measures how supportive the room is for being present, focused, comfortable, and productive right now.

*"How ready is the room for work, study, or normal daytime use?"*

**Factors:** indoor temperature, humidity, TVOC/eCO2, recent occupancy strain  
**High** → room feels supportive and usable · **Low** → space feels less supportive or mildly stressful

---

### 2. Recovery Score
Measures how supportive the room is for calm, rest, decompression, and recovery-like conditions.

*"How good is this room for calming down, resting, or recovery?"*

**Factors:** milder temperature (18–22 C), non-dry humidity, lower TVOC, low recent strain  
**High** → restful and recovery-friendly · **Low** → room feels less restorative

---

### 3. Air Strain
Measures how stressed or burdened the room feels due to poor air conditions and environmental buildup.

*"How heavy or strained does the air feel right now?"*

**Factors:** TVOC, eCO2, heat combined with poor air, recent occupancy/motion  
**Low** → fresh / easy air · **High** → heavy, stale, strained environment

---

### 4. Room State
The room's current human-readable identity — a short label that summarises how the room feels at a glance.

*"What kind of room am I in right now?"*

| Label | Meaning |
|-------|---------|
| `Fresh` | Air feels light, usable, and supportive |
| `Calm` | Room feels stable, balanced, and quiet |
| `Dry` | Humidity is too low, comfort is reduced |
| `Heavy` | Air feels stale, burdened, or environmentally strained |
| `Social` | Recent motion/presence — room is active and in use |
| `Sleep-Friendly` | Room feels more suitable for evening calm or rest |
| `Restless` | Conditions are unbalanced but not yet Heavy |

---

---

## What has been built

### Device — M5Stack sensor (`device/`)
- M5Stack project (`main_project.m5f`) running UIFlow1 / MicroPython on M5Stack Core2
- Reads sensors every 60 s; sends telemetry to the backend every 5 minutes
- Captures: temperature, humidity, air quality (TVOC ppb), eCO2, atmospheric pressure, motion, Wi-Fi RSSI
- Fetches live outdoor weather and 3-day forecast from OpenWeatherMap directly on-device
- Authenticates with the backend using a shared device token (`Authorization: Bearer`)
- Sends structured event logs to the backend `/events` endpoint (boot, WiFi, cloud sync, alerts)

**Boot sequence**

1. Load flash state cache (`/flash/last_state.json`) — dashboard shows last known values instantly
2. Connect Wi-Fi — tries a priority-ordered list of networks (last successful network first)
3. Sync NTP — sets RTC with configurable timezone offset (`TZ_OFFSET = 2`)
4. Cloud sync — fetches `/latest` from backend; applies cloud data only if it is fresher than the local cache
5. Fetch outdoor weather + 3-day forecast from OpenWeatherMap
6. Enter main loop

**Offline resilience**

- Flash cache persists all sensor values, outdoor weather, and data source across reboots
- Silent WiFi reconnect every 60 s in the background without touching the screen
- Failed sensor reads preserve the last known value (non-destructive inner `except: pass`)
- State machine tracks `network_state`, `telemetry_state`, `weather_state`, `cloud_sync_state`

**Dashboard UI (320 × 240, dark background)**

```
┌────────────────────────────────────────┐
│  ● Thu 17 Apr   LIVE            14:32  │  header: dot, date, badge, time
├────────────────────────────────────────┤
│     23.4 °C          Sync failed       │  hero: outdoor temp, status strip
│  Partly cloudy               HUM 62%  │
├────────────────────────────────────────┤
│  TEMP    │   HUMID   │   PRESS         │  indoor strip
│  21.1°C  │   58 %    │   1013 hPa     │
├────────────────────────────────────────┤
│  [ GOOD ]   45 ppb         eCO2 412   │  AQ strip
├────────────────────────────────────────┤
│  Mon       │  Tue      │  Wed          │  3-day forecast
│  16/23°C   │  14/20°C  │  15/22°C     │
│  Clouds    │  Rain     │  Clear        │
└────────────────────────────────────────┘
```

- **Source badge** (header): `LIVE` / `CLOUD` / `CACHED` / `OFFLINE` / `SEND FAIL` / `WX OLD` — color-coded by severity
- **Status strip** (hero row, right side): priority-ordered room-state message — `Offline` › `Sync failed` › `Air strain` › `Dry air` › `Restless` › `Room synced` (15 s) › `Motion` (8 s) › `Weather fresh` (30 s) › `Fresh` / `Calm` / `Sleep-Friendly` / `Social`

**Alerts (sent as events to backend)**

- Humidity drops below 40 % → `humidity_alert` event (edge-triggered, resets when condition clears)
- TVOC ≥ 150 ppb → `air_quality_alert` event (edge-triggered)
- Motion detected → `motion_triggered` event (8 s cooldown before re-trigger)

**Hardware wiring (M5Stack Core2)**

| Sensor | Unit | Port |
|--------|------|------|
| ENV III (temp / humidity / pressure) | `unit.ENV3` | PORTC |
| PIR motion sensor | `unit.PIR` | PORTB |
| TVOC / eCO2 sensor | `unit.TVOC` | PORTA |

**Device screenshots**

| Dashboard | WiFi menu |
|-----------|-----------|
| ![Dashboard](docs/device_dashboard.jpeg) | ![WiFi menu](docs/device_wifi_menu.jpeg) |

### Backend — Flask REST API (`backend/`)
Python 3.11 / Flask application containerised with Docker, designed to run on Google Cloud Run.

**API endpoints**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/telemetry` | Receive sensor payload from M5Stack, enrich with outdoor weather, insert into BigQuery |
| `GET` | `/latest?device_id=` | Return the most recent record for a device |
| `GET` | `/history?device_id=&hours=` | Return records for the last N hours (default 24, max 168) |
| `POST` | `/events` | Receive structured device event logs (boot, WiFi, alerts, sync) |
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
