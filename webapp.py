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
)
from api_endpoints import meters_api, readings_api, dcu_api, system_api, meter_installation_api, auth_api
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
import utils.frames as frames 
import utils.utility_functions as utility_functions
from starlette.middleware.sessions import SessionMiddleware  
from utils.parameters import meter_parameters 
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
    addr = writer.get_extra_info('peername')
    print(f"✅ Connected: {addr}") 
    access_time = 0
    data = await reader.read(1024)
    print(f"📥 From DCU {addr}: {data.hex()}")
    print(len(data)) 
    # if is_expected_frame(data):  

    if utility_functions.is_heartbeat_frame(data): #  daraa ni zasah  
        meter_number = int(data[-8:].decode('utf-8', errors='ignore').strip()) 
    if utility_functions.is_heartbeat_frame_DCU(data):
        try:
            DCU_number = await utility_functions.get_DCU_number(reader, writer)
            print(f"DCU number: {DCU_number}") 
        except (ConnectionError, ValueError, asyncio.TimeoutError) as e:
            print(f"❌ Failed to get DCU number: {e}")
            writer.close()
            await writer.wait_closed()
            return 
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
    elif DCU_number and utility_functions.is_DCU_installed(DCU_number):
        utility_functions.add_DCU_to_connected_clients(DCU_number,addr, access_time,reader,writer) 
        connected_clients[DCU_number]['pause_event'].set()
    else:
        print(f"this  Meter or DCU {meter_number} or {DCU_number} is not installed")  
        writer.close()
        await writer.wait_closed()   
        return
        
    response_queue = connected_clients[meter_number]['response_queue'] 
    keep_connection_queue = connected_clients[meter_number]['keep_connection_queue']  
    reply = data[0:2] + data[4:6] + data[2:4] + data[6:8] + b'\xDA' + data[9:10] + b'\x00\x00' + data[12:]
    writer.write(reply) 
    print("sent reply ")

    try:
        current_date_str = datetime.now().strftime("%m_%d")  # start date
        daily_log_dir = os.path.join(LOG_DIR, current_date_str)
        os.makedirs(daily_log_dir, exist_ok=True)  # create folder once at start  

        while True:
            try: 
                now = datetime.now()
                timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
                data = await asyncio.wait_for(reader.read(1024), timeout=600.0) 

                # check date rollover
                date_str = now.strftime("%m_%d") 
                if date_str != current_date_str:
                    current_date_str = date_str
                    daily_log_dir = os.path.join(LOG_DIR, current_date_str)
                    os.makedirs(daily_log_dir, exist_ok=True) 

                log_file_path = os.path.join(daily_log_dir, f"{meter_number}.log") 

                if not data:
                    # 👇 create empty log file anyway if it doesn't exist yet
                    open(log_file_path, "a").close()
                    break 

                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 📥[meter_reader] From meter {meter_number}: {data.hex()}") 
                with open(log_file_path, "a", encoding="utf-8") as f:
                    f.write(f"{timestamp} | from METER:  {data.hex()}\n")   

                if utility_functions.is_heartbeat_frame(data):  
                    await keep_connection_queue.put(data)     
                else: 
                    await response_queue.put(data) 

            except asyncio.TimeoutError:
                print(f"⏰ Timeout: No data received from meter {meter_number} in 10 minutes")
                break 

    finally:
        print(f"❌ Disconnected: {addr}") 
        try:
            if meter_number in connected_clients:   # ? 

                client = connected_clients[meter_number]
                await utility_functions.clear_tasks(client)
                utility_functions.clear_scheduled_jobs(meter_number)
                writer.close()
                await writer.wait_closed()
                del connected_clients[meter_number]
                print(f"🗑️ Removed meter {meter_number} from connected_clients")

        except Exception as e:
            print(f"⚠️ Cleanup error for meter {meter_number}: {e}")
        



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

# REST API Endpoints
app.include_router(auth_api.router)  # Authentication endpoints
app.include_router(meters_api.router)
app.include_router(readings_api.router)
app.include_router(dcu_api.router)
app.include_router(system_api.router)
app.include_router(meter_installation_api.router)  # Legacy endpoint 
app.include_router(dashboard_api.router)
 
 

 


    
 





    
    
    
    
