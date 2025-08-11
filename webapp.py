from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from routers import dashboard, energy_profile_read,data_read, meter_management, DCU_management, read_DCU_parameter, unregistered_device, meter_installation, read_meter_parameter, system_task, ondemand_reading, line_management
from services.state import connected_clients,scheduler
from services.database import init_db, get_db_connection
import os 
import sys 
from pathlib import Path 

from fastapi.requests import Request
import asyncio
import utils.frames as frames 
import utils.utility_functions as utility_functions 
from utils.parameters import meter_parameters 
app = FastAPI()
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

# Set templates directory
templates = Jinja2Templates(directory=template_path)


init_db()

 
    
    



async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"✅ Connected: {addr}") 
    access_time = 0
    data = await reader.read(1024)
    print(f"📥 From DCU {addr}: {data.hex()}")
    
    # if is_expected_frame(data):  

    if utility_functions.is_heartbeat_frame(data): #  daraa ni zasah  
        meter_number = int(data[-8:].decode('utf-8', errors='ignore').strip())
        print()
    else: 
        print(f"unexpected frame, closing connection: {data}")  
        writer.close()
        await writer.wait_closed()
        return
    
    
    

    # if meter_number in connected_clients: 
    #     print("meter number is in connected clients") 
    #     connected_clients[meter_number]['access_time'] = access_time 
    # else: 
    if utility_functions.is_meter_installed(meter_number):
        utility_functions.add_meter_to_connected_clients(meter_number,addr, access_time,reader,writer) 
        utility_functions.creat_meter_task(meter_number)
        connected_clients[meter_number]['pause_event'].set()
    else:
        print(f"this  Meter {meter_number} is not installed")  
        writer.close()
        await writer.wait_closed()   
        return
        
    response_queue = connected_clients[meter_number]['response_queue'] 
    keep_connection_queue = connected_clients[meter_number]['keep_connection_queue']  
    reply = data[0:2] + data[4:6] + data[2:4] + data[6:8] + b'\xDA' + data[9:10] + b'\x00\x00' + data[12:]
    writer.write(reply) 
    print("sent reply ")

    try:
        while True:
            
            # data = await reader.read(1024)
            # 10 minut huleegeed  
            try: 
                data = await asyncio.wait_for(reader.read(1024), timeout=600.0) 

                if not data:
                    break 
                print(f"📥[meter_reader] From meter {meter_number}: {data.hex()}") 
                if utility_functions.is_heartbeat_frame(data):  
                    await keep_connection_queue.put(data)     
                else: 
                    await response_queue.put(data) 
            except asyncio.TimeoutError:
                print(f"⏰ Timeout: No data received from meter {meter_number} in 10 seconds")
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
    
    tcp_server = await asyncio.start_server(handle_client, '0.0.0.0', 7777)
    print("🚀 TCP Server listening on 7777...")
    tcp_server_task = asyncio.create_task(tcp_server.serve_forever()) 




@app.on_event("startup") 
async def start_tcp_server_background():
    await start_tcp_server()
    scheduler.start()

app.include_router(meter_management.router)
app.include_router(DCU_management.router) 
app.include_router(read_DCU_parameter.router)
app.include_router(unregistered_device.router)
app.include_router(meter_installation.router) 
app.include_router(read_meter_parameter.router) 
app.include_router(system_task.router)
app.include_router(dashboard.router)
app.include_router(data_read.router)
app.include_router(energy_profile_read.router) 
app.include_router(ondemand_reading.router)  
app.include_router(line_management.router)  

 


    
 





    
    
    
    
