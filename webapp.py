from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from routers import (
    dashboard,
    energy_profile_read,
    data_read,
    meter_management,
    DCU_management,
    read_DCU_parameter,
    unregistered_device,
    meter_installation,
    read_meter_parameter,
    system_task,
    ondemand_reading,
    line_management,
    login,
    instant_profile_read,
    batch_upload_meter,
    user_management,
    role_management,
    meter_download,
    relay_control,
)
from api_endpoints import meters_api, readings_api, dcu_api, system_api, meter_installation_api, auth_api, Lorawan_api
from api_endpoints import dashboard_api
from services.state import connected_clients,scheduler
from fastapi import status
from services.database import init_db, get_db_connection
import os 
import sys 
import json 
from pathlib import Path 
from fastapi.requests import Request
import asyncio
from utils import DCU_functions, Mictostar_EDAT_utility_functions, esp32_gateway
import utils.frames as frames 
import utils.utility_functions as utility_functions
from starlette.middleware.sessions import SessionMiddleware  
from utils.parameters import meter_parameters 
from utils.DCU_meter_reader_functions import extract_and_save_profile_data 
from fastapi.middleware.cors import CORSMiddleware 

CONFIG_FILE = "config.json" 
LOG_DIR = "meter_logs"  
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="mysecret",max_age=120 * 60) # session lifetime = 120 minutes
# for apis 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow any origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Config file '{CONFIG_FILE}' not found.")
    with open(CONFIG_FILE, "r") as f:
        return json.load(f) 

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False):
        # If the application is run as a bundle, the PyInstaller bootloader
        # extends the sys module by a flag frozen=True and sets the app 
        # path into variable _MEIPASS
        base_path = sys._MEIPASS
        print("stores in MEIPASS")
    else:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Set up templates and static paths
template_path = resource_path("templates")
static_path = resource_path("static")

# Mount static files
app.mount("/static", StaticFiles(directory=static_path), name="static")
# app.mount("/static", StaticFiles(directory="static"), name="static") 

# Set templates directory
templates = Jinja2Templates(directory=template_path)

@app.exception_handler(HTTPException)
async def permission_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_303_SEE_OTHER and exc.detail == "redirect_login":
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    # fallback for other HTTPException
    raise exc 





init_db()

 
    




async def handle_client(reader, writer):
    meter_number = None 
    DCU_number = None
    EDAT_dev_addr = None
    esp_id = None
    reply = None
    addr = writer.get_extra_info('peername')
    print(f"✅ Connected: {addr}") 
    access_time = 0
    data = await reader.read(1024)
    print(f"📥 From DCU {addr}: {data.hex()}")
    print(len(data)) 
    # if is_expected_frame(data):  

    if esp32_gateway.is_esp_hello(data):
        esp_id = esp32_gateway.esp_device_id(data)
        print(f"ESP32 id: {esp_id}")
    elif utility_functions.is_heartbeat_frame(data): #  daraa ni zasah  
        meter_number = int(data[-8:].decode('utf-8', errors='ignore').strip()) 
    elif utility_functions.is_heartbeat_frame_DCU(data):
        try:
            DCU_number = await utility_functions.get_DCU_number(reader, writer)
            print(f"DCU number: {DCU_number}") 
        except (ConnectionError, ValueError, asyncio.TimeoutError) as e:
            print(f"❌ Failed to get DCU number: {e}")
            writer.close()
            await writer.wait_closed()
            return 
    elif Mictostar_EDAT_utility_functions.is_heartbeat_frame_EDAT(data): 
        EDAT_dev_addr = Mictostar_EDAT_utility_functions.get_EDAT_dev_ID(data)
        print(f"EDAT DEV id: {EDAT_dev_addr}") 
    else: 
        print(f"unexpected frame, closing connection: {data}")  
        writer.close()
        await writer.wait_closed()
        return
    
    
    

    # if meter_number in connected_clients: 
    #     print("meter number is in connected clients") 
    #     connected_clients[meter_number]['access_time'] = access_time 
    # else: 
    if meter_number and utility_functions.is_meter_installed(meter_number):
        utility_functions.add_meter_to_connected_clients(meter_number,addr, access_time,reader,writer) 
        utility_functions.creat_meter_task(meter_number)
        connected_clients[meter_number]['pause_event'].set() 
        device_number = meter_number 
        reply = data[0:2] + data[4:6] + data[2:4] + data[6:8] + b'\xDA' + data[9:10] + b'\x00\x00' + data[12:]

    elif DCU_number and utility_functions.is_DCU_installed(DCU_number):
        utility_functions.add_DCU_to_connected_clients(DCU_number,addr, access_time,reader,writer)
        DCU_functions.creat_dcu_task(DCU_number) 
        connected_clients[DCU_number]['pause_event'].set() 
        device_number = DCU_number  
        reply = bytes.fromhex('0001001000010000')    
    elif EDAT_dev_addr and Mictostar_EDAT_utility_functions.is_EDAT_installed(EDAT_dev_addr): 
        utility_functions.add_DCU_to_connected_clients(EDAT_dev_addr,addr, access_time,reader,writer)
        Mictostar_EDAT_utility_functions.creat_edat_task(EDAT_dev_addr)
        connected_clients[EDAT_dev_addr]['pause_event'].set() 
        device_number = EDAT_dev_addr 
    elif esp_id and esp32_gateway.is_esp_installed(esp_id):
        await esp32_gateway.drop_previous_connection(esp_id)
        utility_functions.add_DCU_to_connected_clients(esp_id, addr, access_time, reader, writer)
        esp32_gateway.creat_esp_task(esp_id)
        if b"\n" in data:
            connected_clients[esp_id]["esp_rx_buf"] = data.split(b"\n", 1)[1]
        connected_clients[esp_id]['pause_event'].set()
        device_number = esp_id
        reply = b"OK\n"
    else:
        print(f"this  Meter or DCU {meter_number} or {DCU_number} or ESP {esp_id} is not installed")  
        writer.close()
        await writer.wait_closed()   
        return
        
    response_queue = connected_clients[device_number]['response_queue'] 
    keep_connection_queue = connected_clients[device_number]['keep_connection_queue']  
    # reply = data[0:2] + data[4:6] + data[2:4] + data[6:8] + b'\xDA' + data[9:10] + b'\x00\x00' + data[12:]
    if reply: 
        writer.write(reply) 
        if esp_id:
            await writer.drain()
        print("sent reply ")

    try:
        current_date_str = datetime.now().strftime("%m_%d")  # start date
        daily_log_dir = os.path.join(LOG_DIR, current_date_str)
        os.makedirs(daily_log_dir, exist_ok=True)  # create folder once at start  

        while True:
            try: 
                now = datetime.now()
                timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
                data = await asyncio.wait_for(reader.read(2048), timeout=600.0) 

                # check date rollover
                date_str = now.strftime("%m_%d") 
                if date_str != current_date_str:
                    current_date_str = date_str
                    daily_log_dir = os.path.join(LOG_DIR, current_date_str)
                    os.makedirs(daily_log_dir, exist_ok=True) 

                log_key = esp_id if esp_id else meter_number
                log_file_path = os.path.join(daily_log_dir, f"{log_key}.log") 

                if not data:
                    # 👇 create empty log file anyway if it doesn't exist yet
                    open(log_file_path, "a").close()
                    break 

                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 📥[meter_reader] From meter {meter_number} or DCU {DCU_number} or ESP {esp_id}: {data.hex()}") 
                with open(log_file_path, "a", encoding="utf-8") as f:
                    f.write(f"{timestamp} | from METER:  {data.hex()}\n")   

                if esp_id and device_number in connected_clients:
                    pending = connected_clients[device_number].get("esp_rx_buf", b"") + data
                    lines, leftover = esp32_gateway.split_lines(pending)
                    connected_clients[device_number]["esp_rx_buf"] = leftover
                    for line in lines:
                        if esp32_gateway.is_hello_line(line):
                            await keep_connection_queue.put(line)
                        else:
                            print("ESP32 response line")
                            await response_queue.put(line)
                elif utility_functions.is_heartbeat_frame(data): 
                    await keep_connection_queue.put(data)   
                elif utility_functions.is_heartbeat_frame_DCU(data): 
                    await keep_connection_queue.put(data)  
                elif utility_functions.is_profile_frame_DCU(data): 
                    extract_and_save_profile_data(data)  # pyright: ignore[reportUndefinedVariable]
                    print("profile frame")  
                else: 
                    print("regular response frame") 
                    await response_queue.put(data) 

            except asyncio.TimeoutError:
                print(f"⏰ Timeout: No data received from meter or DCU {meter_number} or {DCU_number} in 10 minutes")
                break 

    finally:
        print(f"❌ Disconnected: {addr}") 
        try:
            if device_number in connected_clients and connected_clients[device_number].get("writer") is writer:

                client = connected_clients[device_number]
                if meter_number:
                    await utility_functions.clear_tasks(client)
                    utility_functions.clear_scheduled_jobs(device_number)
                elif esp_id:
                    await utility_functions.clear_tasks(client)
                    utility_functions.clear_scheduled_jobs(device_number)
                writer.close()
                await writer.wait_closed()
                del connected_clients[device_number] 
                print(f"🗑️ Removed meter {device_number} from connected_clients")

        except Exception as e:
            print(f"⚠️ Cleanup error for meter {device_number}: {e}")
        



tcp_server = None  # Will hold the server object
tcp_server_task = None 


async def start_tcp_server():
    global tcp_server
    global tcp_server_task
    config = load_config() 
    ip_address = config.get("ip_address", "0.0.0.0")
    port = config.get("port", 7777) 
    tcp_server = await asyncio.start_server(handle_client, ip_address, port) 
    print(f"🚀 TCP Server listening on {ip_address}:{port}...")
    tcp_server_task = asyncio.create_task(tcp_server.serve_forever()) 




@app.on_event("startup") 
async def start_tcp_server_background():
    await start_tcp_server()
    scheduler.start()

# Web UI Routers
app.include_router(meter_management.router)
app.include_router(DCU_management.router) 
app.include_router(read_DCU_parameter.router)
app.include_router(unregistered_device.router)
app.include_router(meter_installation.router) 
app.include_router(read_meter_parameter.router) 
app.include_router(system_task.router)
app.include_router(dashboard.router)
app.include_router(meter_download.router)
app.include_router(data_read.router)
app.include_router(energy_profile_read.router) 
app.include_router(ondemand_reading.router)  
app.include_router(line_management.router)  
app.include_router(login.router)   
app.include_router(instant_profile_read.router)  
app.include_router(batch_upload_meter.router)  
app.include_router(user_management.router) 
app.include_router(role_management.router)
app.include_router(relay_control.router)

# REST API Endpoints
app.include_router(auth_api.router)  # Authentication endpoints
app.include_router(meters_api.router)
app.include_router(readings_api.router)
app.include_router(dcu_api.router)
app.include_router(system_api.router)
app.include_router(meter_installation_api.router)  # Legacy endpoint 
app.include_router(dashboard_api.router)
app.include_router(Lorawan_api.router)
 

 


    
 





    
    
    
    
