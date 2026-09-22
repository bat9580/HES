from fastapi import APIRouter, Request
import requests
import base64
import json 
BASE_URL = "http://localhost:8090/api/devices" 
API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJjaGlycHN0YWNrIiwiaXNzIjoiY2hpcnBzdGFjayIsInN1YiI6ImRhMzk5YmZmLWQ5NGUtNDY0Yy1iMDkwLTUyZjdlYmE3OTEzMiIsInR5cCI6ImtleSJ9.YjjM49visHBcPLY38W3ZgZKNOk-jRtsfHUtCIUllzhM"  
API_KEY1 = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJjaGlycHN0YWNrIiwiaXNzIjoiY2hpcnBzdGFjayIsInN1YiI6ImVmYzU5ZWUxLTcyYTAtNDU4Zi1hYjZlLWViZTdiN2NlOTczOCIsInR5cCI6ImtleSJ9.ZFAojYJ66Qb9UJAFmnQhc8HAtx6uuW_JNXCcqdgwDfY"
router = APIRouter(prefix="/api", tags=["Lorawan"])
CHIRPSTACK_URL = "http://chirpstack:8080"
DEV_EUI = "a840411da187e659" 
incoming_responses = {} 

@router.post("/chirpstack/uplink")
async def chirpstack_events(request: Request):
    print("🔄 ChirpStack events received") 
    
    # 1. Get the JSON body
    payload = await request.json()
    
    # 2. Extract DevEUI (Check if your JSON uses 'devEui' or 'dev_eui')
    device_info = payload.get('deviceInfo', {})
    dev_eui = device_info.get('devEui') or device_info.get('dev_eui')
    
    # 3. Extract the actual payload data
    raw_data = payload.get("data")
    
    if dev_eui and raw_data:
        # Decode Base64 and save to your shared dictionary
        decoded_hex = base64.b64decode(raw_data).hex().upper()
        incoming_responses[dev_eui] = decoded_hex
        print(f"✅ Saved response for {dev_eui}: {decoded_hex}")
    
    return {"status": "success"}, 200


def send_downlink(dev_eui, payload_hex, f_port=1):
    # Construct the URL dynamically using the dev_eui variable
    url = f"{BASE_URL}/{dev_eui}/queue"
    
    # Prepare data
    byte_data = bytes.fromhex(payload_hex)
    base64_data = base64.b64encode(byte_data).decode('utf-8')

    payload = {
        "queueItem": {
            "confirmed": False,
            "fPort": f_port,
            "data": base64_data
        }
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}", 
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        print(f"Success: Message queued for Device {dev_eui}")
    else:
        print(f"Failed for {dev_eui}: {response.text}")

# Now you can call it for different devices easily:

# print(r.status_code, r.text)
# @router.post("/chirpstack/uplink")
# async def chirpstack_events(request: Request):
#     print("🔄 ChirpStack events received") 
#     event = request.query_params.get("event")
#     payload = await request.json()

#     print("📥 ChirpStack event:", event)
#     print(payload)

#     return {"status": "ok"}




