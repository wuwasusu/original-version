import requests
import json

API_KEY = "e73d7f36-2b30-4ba1-acd7-5e0be1cac390"  # 替换为实际分配的密钥
URL = "http://192.168.1.101:5000/sensor_heartbeat"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

data = {
    "sensor_id":["sensor_001","sensor_002"],
}

response = requests.post(URL, headers=headers, data=json.dumps(data))
print(response.json())