import requests
from dotenv import load_dotenv
import os

load_dotenv()

BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8080")
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "core2-livingroom")
HOURS = 24

response = requests.get(
    f"{BASE_URL}/api/v1/history",
    params={"device_id": DEVICE_ID, "hours": HOURS},
)

print(f"GET /api/v1/history?device_id={DEVICE_ID}&hours={HOURS}")
print(f"Status: {response.status_code}")

data = response.json()
if data.get("success"):
    print(f"\nReturned {data['count']} records:")
    for row in data["data"]:
        print(f"  {row['timestamp']} | temp={row['indoor_temp']}°C | humidity={row['indoor_humidity']}% | air={row['air_quality']} ({row.get('air_quality_label')}) | weather={row.get('outdoor_weather')} ({row.get('weather_status')})")
else:
    print(f"Error: {data.get('message')}")
