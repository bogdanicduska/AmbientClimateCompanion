-- ============================================================
-- Room Rhythm — main telemetry table
-- Project : cloud-lab-weather
-- Dataset : ambient_climate
-- Table   : weather_records
--
-- This table stores every reading sent by an M5Stack device.
-- Each row is one sensor snapshot enriched with outdoor weather
-- at ingestion time.  Partitioned by DATE(timestamp) for cost-
-- efficient time-window queries (history, daily-summary, replay).
--
-- To create:
--   bq mk --table \
--     cloud-lab-weather:ambient_climate.weather_records \
--     sql/create_room_telemetry.sql
--
-- Or run directly in the BigQuery console / Cloud Shell.
-- ============================================================

CREATE TABLE IF NOT EXISTS `cloud-lab-weather.ambient_climate.weather_records` (

  -- ── Identity ────────────────────────────────────────────────────────────
  device_id         STRING    NOT NULL,   -- e.g. "m5stack-duska-home"
  timestamp         TIMESTAMP NOT NULL,   -- measurement time (device-provided or ingest time)
  ingested_at       TIMESTAMP NOT NULL,   -- when the backend received this row

  -- ── Indoor environment ──────────────────────────────────────────────────
  indoor_temp       FLOAT64,              -- °C
  indoor_humidity   FLOAT64,              -- %
  indoor_pressure   FLOAT64,              -- hPa (optional — ENV3 unit)
  indoor_eco2       FLOAT64,              -- ppm  (eCO2 from TVOC unit)
  air_quality       FLOAT64,              -- ppb  (TVOC raw reading)
  air_quality_label STRING,               -- "Good" | "Moderate" | "Poor" | "Hazardous"
  motion            BOOL,                 -- PIR sensor state
  wifi_rssi         INT64,                -- dBm, negative; null if not sent

  -- ── Outdoor / weather ───────────────────────────────────────────────────
  outdoor_temp      FLOAT64,              -- °C from OpenWeatherMap
  outdoor_humidity  FLOAT64,              -- %
  outdoor_weather   STRING,               -- description, e.g. "clear sky"
  outdoor_icon      STRING,               -- OWM icon code, e.g. "01d"
  weather_status    STRING,               -- "live" | "unavailable"

  -- ── Sync metadata ───────────────────────────────────────────────────────
  sync_status       STRING                -- "ok" on successful ingest

)
PARTITION BY DATE(timestamp)
CLUSTER BY device_id
OPTIONS (
  description = "Room Rhythm — per-device sensor snapshots with outdoor weather enrichment",
  partition_expiration_days = 730   -- 2-year retention; adjust for your project
);


-- ============================================================
-- Useful queries
-- ============================================================

-- Latest reading per device:
-- SELECT * FROM `cloud-lab-weather.ambient_climate.weather_records`
-- WHERE device_id = 'm5stack-duska-home'
-- ORDER BY timestamp DESC LIMIT 1;

-- History window (last 24 h):
-- SELECT * FROM `cloud-lab-weather.ambient_climate.weather_records`
-- WHERE device_id = 'm5stack-duska-home'
--   AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
-- ORDER BY timestamp ASC;

-- Daily summary base (one calendar day):
-- SELECT * FROM `cloud-lab-weather.ambient_climate.weather_records`
-- WHERE device_id = 'm5stack-duska-home'
--   AND DATE(timestamp) = '2026-05-21'
-- ORDER BY timestamp ASC;
