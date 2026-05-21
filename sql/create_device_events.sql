-- ============================================================
-- Room Rhythm — device events table
-- Project : cloud-lab-weather
-- Dataset : ambient_climate
-- Table   : device_events
--
-- Stores device lifecycle events, alerts, and speech events.
-- Used by the proactive speech service for cooldown checks
-- and by the dashboard event timeline.
--
-- To create:
--   bq mk --table \
--     cloud-lab-weather:ambient_climate.device_events \
--     sql/create_device_events.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS `cloud-lab-weather.ambient_climate.device_events` (
  device_id   STRING    NOT NULL,   -- e.g. "m5stack-duska-home"
  event_type  STRING    NOT NULL,   -- see VALID_EVENT_TYPES in validators.py
  timestamp   TIMESTAMP NOT NULL,   -- when the event occurred
  details     STRING,               -- JSON string with event-specific context
  logged_at   TIMESTAMP NOT NULL    -- when the backend received this event
)
PARTITION BY DATE(timestamp)
CLUSTER BY device_id
OPTIONS (
  description = "Room Rhythm — device lifecycle and alert events from M5Stack"
);

-- Valid event_type values (kept in sync with backend/app/utils/validators.py):
--   wifi_connected, wifi_disconnected, wifi_failed
--   room_online, room_state_restored, cache_loaded, boot_recovered
--   room_synced, room_sync_failed
--   humidity_alert, air_quality_alert, motion_triggered
--   announcement_spoken, speech_query_received, speech_summary_spoken
