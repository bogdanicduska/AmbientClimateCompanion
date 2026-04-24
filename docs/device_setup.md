# Device Setup — M5Stack Core2

## Runtime

| Property | Value |
|----------|-------|
| Firmware | UIFlow1 v1.15.2 |
| Language | MicroPython |
| Device ID | `m5stack-duska-home` (hardcoded in `main_project.m5f`) |

## Hardware Wiring

| Sensor | Unit | Port |
|--------|------|------|
| ENV III (temperature / humidity / pressure) | `unit.ENV3` | PORTC |
| PIR motion sensor | `unit.PIR` | PORTB |
| TVOC / eCO2 sensor | `unit.TVOC` | PORTA |

## Flash Storage

| File | Purpose |
|------|---------|
| `/flash/last_wifi.txt` | SSID of last successful Wi-Fi connection (tried first on next boot) |
| `/flash/last_state.json` | Full room state snapshot: sensors, outdoor weather, room metrics |

## Boot Sequence

1. Load `/flash/last_state.json` — dashboard shows last known room state instantly
2. Compute room metrics from cached sensor values
3. Show Wi-Fi menu — press **A** or **C** to connect
4. NTP sync — sets RTC with `TZ_OFFSET = 2` (CEST)
5. Cloud sync — fetches `/latest` from backend; applies only if fresher than cache
6. Fetch outdoor weather + 3-day forecast from OpenWeatherMap
7. Enter main loop (sensor read every 60 s, telemetry every 300 s)

## Wi-Fi Networks (priority order)

Stored in `WIFI_NETWORKS` list in the device file. Last successful SSID is saved to flash and tried first on the next boot.

## Key Config Constants

| Constant | Default | Meaning |
|----------|---------|---------|
| `SEND_EVERY` | 300 s | Telemetry interval |
| `WEATHER_EVERY` | 1800 s | Outdoor weather refresh interval |
| `WIFI_RETRY_EVERY` | 60 s | Silent reconnect attempt interval |
| `TZ_OFFSET` | 2 | Timezone offset applied at NTP sync |
| `HUMIDITY_LOW_THRESHOLD` | 40 % | Triggers "Dry" room state |
| `AQ_POOR_THRESHOLD` | 150 ppb | Triggers "Heavy" room state |
| `AQ_HAZARD_THRESHOLD` | 200 ppb | Triggers HAZARDOUS AQ chip |

## Room Performance Metrics

Computed by `compute_room_metrics()` after every sensor read and after cache load.

| Metric | Type | Description |
|--------|------|-------------|
| `room_readiness` | 0–100 | How ready the room is for focus and presence |
| `recovery_score` | 0–100 | How supportive the room is for rest and calm |
| `air_strain` | 0–100 | How stale or strained the air is |
| `room_state` | label | `Fresh` / `Calm` / `Dry` / `Heavy` / `Social` / `Sleep-Friendly` / `Restless` |
