from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi import Form, Request   
from fastapi.responses import RedirectResponse 
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from datetime import datetime 
 
from fastapi.requests import Request
import asyncio
import sqlite3 
import frames

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATABASE = "connection.db"
# Create database table if not exists
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unregistered_dcu (
            dcu_number TEXT PRIMARY KEY,
            ip_address TEXT,
            first_connection TEXT,
            last_connection TEXT,
            access_time INTEGER
        )
    """)
    # cursor.execute("DROP TABLE IF EXISTS registered_dcus") 
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registered_dcus(
            dcu_number TEXT PRIMARY KEY,
            com_address TEXT,
            remarks TEXT,
            status TEXT       
            ip_address TEXT,
            password TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registered_meters( 
            meter_number TEXT PRIMARY KEY,
            com_address TEXT,
            password TEXT,
            device_type TEXT, 
            type TEXT,
            remarks TEXT,
            status TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS installed_meters( 
            meter_number TEXT PRIMARY KEY,
            com_address TEXT,
            password TEXT,
            device_type TEXT, 
            type TEXT, 
            remarks TEXT,
            status TEXT,
            DCU_number TEXT, 
            Zone TEXT, 
            POWER_grid TEXT  
        )
    """)
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Get database connection
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

connected_clients = {}
pending_requests = {} 

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"✅ Connected: {addr}") 
    access_time = 0

    try:
        while True:
            data = await reader.read(1024)
            if not data:
                break
            print(f"📥 From DCU {addr}: {data.hex()}") 
            access_time += 1  

            if access_time < 2:  # First connection:  gets DCU name tries 5 times  
                writer.write(bytes.fromhex(frames.AARQ))  
                await writer.drain() 
                print(f"🆔 From server: {frames.AARQ}")    

                data = await reader.read(1024)  
                print(f"📥 From DCU: {data.hex()}")   

                writer.write(bytes.fromhex(frames.GET_DCU_NAME))
                await writer.drain()  
                print(f"🆔 From server: {frames.GET_DCU_NAME}") 

                data = await reader.read(1024)  
                print(f"📥 From DCU: {data.hex()}") 

                DCU_number = data[22:30].decode('utf-8', errors='ignore').strip()
                print(f"DCU number = : {DCU_number}") 

                # Update connected_clients and database  


                # check if the the dcu is registered
                conn = get_db_connection() 
                cursor = conn.cursor() 
                result = cursor.execute("SELECT 1 FROM registered_dcus WHERE dcu_number = ?", (DCU_number,))    
                result = result.fetchone() 
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S') 
                if result is None: 
                    print("adding unregistered dcus") 
                    cursor.execute("""
                    INSERT OR REPLACE INTO unregistered_dcu (dcu_number, ip_address,first_connection,last_connection,access_time)    
                    VALUES (?,?,?,?,?)
                    """, (DCU_number, addr[0], current_time, current_time,access_time))
                    conn.commit()
                    conn.close()  
                  
                connected_clients[DCU_number] = {
                    'addr' : addr,  
                    'access_time': access_time,
                    'queue': asyncio.Queue() 
                } 
                
                
            try: 
                message = connected_clients[DCU_number]['queue'].get_nowait()
                writer.write(bytes.fromhex(frames.AARQ)) 
                await writer.drain()  
                print(f"read command")      
                print(f"🆔 From server: {frames.AARQ}")     
                  
                data = await reader.read(1024)  
                print(f"📥 From DCU: {data.hex()}")     
                writer.write(message) 
                await writer.drain() 
                print(f"📥 From DCU: {message}")  
                data = await reader.read(1024)   
                if DCU_number in pending_requests: 
                    pending_requests[DCU_number].set_result(data) 
                    del pending_requests[DCU_number]
            except asyncio.QueueEmpty:
                writer.write(bytes.fromhex(frames.DCU_ACK))
                await writer.drain() 
                print(f"🆔 From server: {frames.DCU_ACK}")    
            connected_clients[DCU_number]['access_time'] = access_time 
            conn = get_db_connection() 
            cursor = conn.cursor() 
            cursor.execute("""
            UPDATE unregistered_dcu
            SET last_connection = ?, access_time = access_time + 1
            WHERE dcu_number = ?
            """, (current_time, DCU_number)) 
            conn.commit()
            conn.close()
             
            
 
          
    finally:
        print(f"❌ Disconnected: {addr}")
        writer.close()
        await writer.wait_closed()

# Use the existing event loop to start the server
async def start_tcp_server():
    server = await asyncio.start_server(handle_client, '0.0.0.0', 7777)
    print("🚀 TCP Server listening on 7777...")
    async with server:
        await server.serve_forever()

@app.on_event("startup") 
async def start_tcp_server_background():
    # This will create and run the TCP server in the existing event loop
    asyncio.create_task(start_tcp_server())

# home page -------------------------------

@app.get("/", response_class=HTMLResponse)  
async def home(request: Request, message: str = None): 
    return templates.TemplateResponse("home1.html", {"request": request, "message": message})   


 
@app.post("/register_dcu") 
async def register_dcu(
    request: Request, 
    dcu_number: str = Form(...), 
    ip_address: str = Form(...), 
    password: str = Form(...) 
):
    conn = get_db_connection() 
    cursor = conn.cursor() 
    try: 
        cursor.execute("""
            INSERT OR REPLACE INTO registered_dcus (dcu_number, ip_address, password) 
            VALUES (?,?,?) 
        """, (dcu_number, ip_address, password))
        conn.commit()  
        message = f"✅ DCU {dcu_number} registered successfully." 
    except sqlite3.IntegrityError: 
        message = f"⚠️ DCU {dcu_number} is already registered." 
    finally: 
        conn.close() 
                   
    return RedirectResponse(url=f"/?message={message}", status_code=303)    
                   
@app.get("/registered-dcus", response_class=HTMLResponse) 
async def registered_dcu(request: Request, message: str = None):
    conn = get_db_connection() 
    registered = conn.execute("SELECT *FROM registered_dcus").fetchall() 
    conn.close()
    return templates.TemplateResponse("registered.html", {"request":request, "registered": registered, "message":message}) 


# Meter  management ------------------------------------------------------------
@app.get("/meter-management", response_class=HTMLResponse)
async def meter_management(request:Request, message: str = None): 
    message = request.query_params.get("message") 
    conn = get_db_connection()
    registered_meters = conn.execute("SELECT *FROM registered_meters ").fetchall()
    conn.close() 
    return templates.TemplateResponse("meter_management.html", {"request": request, "message": message, "registered_meters": registered_meters})  
@app.post("/add-meter") 
async def add_meter(
    request: Request,
    meter_number: str = Form(...),
    comm_address: str = Form(...), 
    device_type: str = Form(...), 
    type: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...)):   
    
    conn = get_db_connection() 
    cursor = conn.cursor()
    try: 

        cursor.execute("""
            INSERT INTO registered_meters 
            (meter_number, com_address,password, device_type, type, remarks,status)
            VALUES (?,?,?,?,?,?,?) 
        """, (meter_number, comm_address, password, device_type, type, remarks,status))
        conn.commit()
        message = f"✅ Meter added successfully." 
    except sqlite3.IntegrityError: 
        message = f"⚠️ same METER NUMBER is already registered."
    finally:
        conn.close()
     
    return RedirectResponse(url=f"/meter-management?message={message}", status_code = 303)  
@app.post("/edit-meter")
async def add_meter(
    request: Request,
    original_meter_number: str = Form(...), 
    meter_number: str = Form(...),
    comm_address: str = Form(...), 
    device_type: str = Form(...), 
    type: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...)): 
    
    conn = get_db_connection() 
    cursor = conn.cursor() 
    try: 
        cursor.execute("""
            UPDATE registered_meters 
            SET meter_number = ?,
                com_address = ?,
                device_type = ?,
                type = ?, 
                password = ?, 
                remarks = ?,
                status = ? 
            WHERE meter_number = ? 
        """, (meter_number, comm_address, device_type, type, password, remarks,status,original_meter_number)) 
        conn.commit()
        message = f"✅ Meter edited successfully." 
    except sqlite3.IntegrityError: 
        message = f"⚠️ same METER NUMBER is already registered."  
    finally: 
        conn.close() 
    return RedirectResponse(url=f"/meter-management?message={message}", status_code=303) 
@app.post("/delete-meter") 
async def delete_meter( meter_number : str = Form(...)):   
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registered_meters WHERE meter_number = ?", (meter_number,)) 
    conn.commit()
    conn.close()
    message = f"✅ METER is successfully deleted."  
    return RedirectResponse(url=f"/meter-management?message={message}", status_code=303) 
@app.get("/search-meter", response_class=HTMLResponse)
async def search_meter(request:Request, meter_number: str = "", device_type: str = ""):  
    query = "SELECT * FROM registered_meters WHERE 1=1"  
    params = [] 
    if meter_number: 
        query+= " AND meter_number LIKE ?"   
        params.append(f"%{meter_number}%") 
    
    if device_type:  
        query += " AND device_type LIKE ?"  
        params.append(f"%{device_type}%") 
    conn = get_db_connection()  
    searched_meters = conn.execute(query, params).fetchall() 
    # searched_meters = conn.execute("SELECT *FROM registered_meters ").fetchall()
    conn.close() 
    print(device_type) 
 
    return templates.TemplateResponse("meter_management.html",{  
        "request": request, 
        "registered_meters": searched_meters,
        "meter_number": meter_number
    })
# DCU  management ------------------------------------------------------------
      
@app.get("/DCU-management", response_class=HTMLResponse)
async def dcu_management(request: Request, message: str = None):
    conn = get_db_connection()
    dcus = conn.execute("SELECT *FROM registered_dcus").fetchall() 
    return templates.TemplateResponse("DCU_management.html",{"request": request, "registered_dcus":dcus , "message": message})  
@app.post("/add-dcu") 
async def add_meter(
    request: Request,
    dcu_number: str = Form(...),
    comm_address: str = Form(...), 
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...)): 
    
    conn = get_db_connection() 
    cursor = conn.cursor()
    try: 

        cursor.execute("""
            INSERT INTO registered_dcus 
            (dcu_number, com_address,password,remarks,status)
            VALUES (?,?,?,?,?) 
        """, (dcu_number, comm_address, password,remarks,status))
        conn.commit()
        message = f"✅ DCU added successfully." 
    except sqlite3.IntegrityError: 
        message = f"⚠️ same DCU NUMBER is already registered." 
    finally:
        conn.close()
     
    return RedirectResponse(url=f"/DCU-management?message={message}", status_code = 303)  

@app.post("/edit-dcu")
async def add_dcu(
    request: Request,
    original_dcu_number: str = Form(...), 
    dcu_number: str = Form(...),
    comm_address: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...)): 

    conn = get_db_connection() 
    cursor = conn.cursor() 
    try: 
        cursor.execute("""
            UPDATE registered_dcus 
            SET dcu_number = ?,
                com_address = ?,
                password = ?, 
                remarks = ?,
                status = ? 
            WHERE dcu_number = ? 
        """, (dcu_number, comm_address, password, remarks,status,original_dcu_number)) 
        conn.commit()
        message = f"✅ DCU edited successfully." 
    except sqlite3.IntegrityError: 
        message = f"⚠️ same DCU NUMBER is already registered."  
    finally: 
        conn.close() 
    return RedirectResponse(url=f"/DCU-management?message={message}", status_code=303) 
@app.post("/delete-dcu")  
async def delete_dcu( dcu_number : str = Form(...)):   
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registered_dcus WHERE dcu_number = ?", (dcu_number,)) 
    conn.commit()
    conn.close()
    message = f"✅ DCU is successfully deleted."  
    return RedirectResponse(url=f"/DCU-management?message={message}", status_code=303) 

@app.get("/search-dcu", response_class=HTMLResponse)
async def search_dcu(request:Request, dcu_number: str = ""):   
    query = "SELECT * FROM registered_dcus WHERE 1=1"  
    params = [] 
    if dcu_number: 
        query+= " AND dcu_number LIKE ?"   
        params.append(f"%{dcu_number}%") 
    
    conn = get_db_connection()  
    searched_dcus = conn.execute(query, params).fetchall() 
    conn.close() 
 
    return templates.TemplateResponse("DCU_management.html",{  
        "request": request, 
        "registered_dcus": searched_dcus,
        "dcu_number": dcu_number
    }) 

# Read DCU parameter ----------------------------------  


@app.get("/read_parameter", response_class=HTMLResponse) 
async def read_DCU_parameter(request: Request, message: str=None): 
    conn = get_db_connection() 
    registered_dcu = conn.execute("SELECT *FROM registered_dcus").fetchall()   
    conn.close()
    return templates.TemplateResponse("read_parameter.html", {"request": request,"registered_dcus": registered_dcu,"connected_clients": connected_clients})  
@app.get("/search-dcu-1", response_class=HTMLResponse)
async def search_dcu(request:Request, dcu_number: str = ""):   
    query = "SELECT * FROM registered_dcus WHERE 1=1"  
    params = [] 
    query+= " AND dcu_number LIKE ?"   
    params.append(f"%{dcu_number}%") 
    
    conn = get_db_connection()  
    searched_dcus = conn.execute(query, params).fetchall() 
    conn.close()  
 
    return templates.TemplateResponse("read_parameter.html",{  
        "request": request, 
        "registered_dcus": searched_dcus,
        "dcu_number": dcu_number 
    }) 
@app.post("/read-dcu-parameter")
async def read_DCU_parameter(request: Request):
    data = await request.json()
    selected_dcus = data.get("selected_dcus")
    selected_parameters = data.get("selected_parameters")

    results = []

    for dcu in selected_dcus:
        if dcu not in connected_clients:
            results.append({
                "dcu_number": dcu,
                "result": "Error: DCU is offline"
            })
            continue

        response_future = asyncio.Future()
        pending_requests[dcu] = response_future

        # You can tailor what frame to send based on selected_parameters if needed
        await connected_clients[dcu]['queue'].put(bytes.fromhex(frames.GET_DCU_NAME))

        try:
            response_data = await asyncio.wait_for(response_future, timeout=20)
            response_data = response_data[22:30].decode('utf-8', errors='ignore').strip()  
            results.append({
                "dcu_number": dcu,
                "result": response_data
            })

        except asyncio.TimeoutError:
            results.append({
                "dcu_number": dcu,
                "result": "Error: Timed out waiting for DCU response"
            })

    return JSONResponse(content=results)

# Unregistered DCU ------------------------------------------

@app.get("/unregistered-device",response_class=HTMLResponse) 
async def Unregistered_device(request: Request, message: str=None): 
    conn = get_db_connection()   
    unregistered = conn.execute("SELECT *FROM unregistered_dcu").fetchall()   
    print(unregistered)    
    conn.close()
    return templates.TemplateResponse("unregistered.html", {"request": request, "Unregistered":unregistered,"message":message})   

@app.get("/search-unregistered-dcu", response_class=HTMLResponse)
async def search_dcu(request:Request, dcu_number: str = ""):  
      
    query = "SELECT * FROM unregistered_dcu WHERE 1=1"  
    params = [] 
    query+= " AND dcu_number LIKE ?"   
    params.append(f"%{dcu_number}%") 
    
    conn = get_db_connection()  
    searched_dcus = conn.execute(query, params).fetchall() 
    print(searched_dcus) 
    conn.close() 
 
    return templates.TemplateResponse("unregistered.html",{   
        "request": request, 
        "Unregistered": searched_dcus, 
        "dcu_number": dcu_number 
    })  
@app.post("/clear-unregistered-dcu")
async def clear_selected_dcu(request:Request):
    data = await request.json()
    selected_dcus = data.get("selected_dcus")
    conn = get_db_connection()
    cursor = conn.cursor()
     
    for dcu in selected_dcus:
        cursor.execute("DELETE FROM unregistered_dcu WHERE dcu_number = ?", (dcu,))  
    conn.commit()
    conn.close() 
    message = f"✅ DCU is successfully deleted."  
    return RedirectResponse(url=f"/unregistered-device?message={message}", status_code=303) 

@app.post("/install-unregistered-dcu") 
async def add_dcu(
    request: Request,
    dcu_number: str = Form(...),
    comm_address: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...)): 

    conn = get_db_connection() 
    cursor = conn.cursor() 
    try: 
        cursor.execute("""
            INSERT INTO registered_dcus
            (dcu_number, com_address,password,remarks,status)
            VALUES (?,?,?,?,?)  
        """, (dcu_number, comm_address, password,remarks,status))  
        cursor.execute("DELETE FROM unregistered_dcu WHERE dcu_number = ?", (dcu_number,)) 
        conn.commit() 
        message = f"✅ DCU added successfully."    
        
    except sqlite3.IntegrityError: 
        message = f"⚠️ same DCU NUMBER is already registered."  
    finally: 
        conn.close() 
    return RedirectResponse(url=f"/unregistered-device?message={message}", status_code=303)   


@app.get("/meter-installation",response_class=HTMLResponse)
async def meter_installation(request: Request, message: str=None):
    conn = get_db_connection()   
    installed_meters = conn.execute("SELECT *FROM installed_meters").fetchall()        
    conn.close()
    return templates.TemplateResponse("meter_installation.html", {"request": request, "installed_meters":installed_meters,"message":message}) 
    
    


     



    
 





    
    
    
    
