import requests
from dotenv import load_dotenv
import os

load_dotenv()

BASE_URL = "http://127.0.0.1:8080"
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "core2-livingroom")

response = requests.get(f"{BASE_URL}/api/v1/latest", params={"device_id": DEVICE_ID})

print(f"GET /api/v1/latest?device_id={DEVICE_ID}")
print(f"Status: {response.status_code}")

data = response.json()
if data.get("success"):
    row = data["data"]
    print(f"\nLatest reading:")
    for k, v in row.items():
        print(f"  {k}: {v}")
else:
    print(f"Error: {data.get('message')}")
