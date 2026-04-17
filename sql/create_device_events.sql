CREATE TABLE IF NOT EXISTS `cloud-lab-weather.ambient_climate.device_events` (
  device_id   STRING    NOT NULL,
  event_type  STRING    NOT NULL,
  timestamp   TIMESTAMP NOT NULL,
  details     STRING,
  logged_at   TIMESTAMP NOT NULL
)
PARTITION BY DATE(timestamp)
OPTIONS (
  description = "Device lifecycle and alert events from M5Stack"
);
