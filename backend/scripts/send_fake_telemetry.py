import requests
import random
from datetime import datetime, timezone

BASE_URL = "http://127.0.0.1:8080"

payload = {
    "device_id":       "core2-livingroom",
    "timestamp":       datetime.now(timezone.utc).isoformat(),
    "indoor_temp":     round(random.uniform(20.0, 25.0), 1),
    "indoor_humidity": round(random.uniform(35.0, 55.0), 1),
    "air_quality":     round(random.uniform(80.0, 180.0), 1),
    "motion":          random.choice([True, False]),
    "wifi_rssi":       random.randint(-75, -45),
}

print("Sending payload:")
for k, v in payload.items():
    print(f"  {k}: {v}")

response = requests.post(f"{BASE_URL}/api/v1/telemetry", json=payload)
print(f"\nStatus: {response.status_code}")
print(f"Response: {response.json()}")
