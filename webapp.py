from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi import Form, Request   
from fastapi.responses import RedirectResponse 
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import asyncio
import sqlite3 
import datetime
import frames

app = FastAPI()
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registered_dcus(
            dcu_number TEXT PRIMARY KEY,
            ip_address TEXT,
            password TEXT
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

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    ip_address = addr[0]
    print(f"✅ Connected: {addr}")
    

    access_time = 0
    try:
        while True:
            data = await reader.read(1024)
            if not data:
                break
            print(f"📥 From DCU {addr}: {data.hex()}") 
            access_time += 1  
            writer.write(bytes.fromhex(frames.DCU_ACK))  
            print(f"🆔 From server: {frames.DCU_ACK}")

            if access_time == 1:  # First connection
                writer.write(bytes.fromhex(frames.AARQ))  
                print(f"🆔 From server: {frames.AARQ}")    

                data = await reader.read(1024)  
                print(f"📥 From DCU: {data.hex()}")   

                writer.write(bytes.fromhex(frames.GET_DCU_NAME)) 
                print(f"🆔 From server: {frames.GET_DCU_NAME}") 

                data = await reader.read(1024)  
                print(f"📥 From DCU: {data.hex()}") 

                DCU_number = data[14:32].decode('utf-8', errors='ignore').strip()
                print(f"DCU number = : {DCU_number}")

                # Update connected_clients and database
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                connected_clients[DCU_number] = {
                    'ip_address': ip_address, 
                    'first_connection': now, 
                    'last_connection': now,    
                    'access_time': access_time 
                }

                # Store DCU connection in the database
                conn = get_db_connection()
                cursor = conn.cursor()  
                cursor.execute("""
                    INSERT OR REPLACE INTO unregistered_dcu
                    (dcu_number, ip_address, first_connection, last_connection, access_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    DCU_number,
                    ip_address,
                    connected_clients[DCU_number]['first_connection'],
                    connected_clients[DCU_number]['last_connection'],
                    access_time
                )) 
                conn.commit() 
                conn.close()

            else:  # Update existing DCU connection
                for dcu, info in connected_clients.items():
                    if info['ip_address'] == ip_address:
                        info['last_connection'] = str(datetime.datetime.now())
                        info['access_time'] += 1  # Increment access time on each packet exchange

                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE unregistered_dcu
                            SET last_connection = ?, access_time = ?
                            WHERE dcu_number = ?
                        """, (
                            info['last_connection'],
                            info['access_time'],
                            dcu
                        ))
                        conn.commit()
                        conn.close()
                        break

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

@app.get("/", response_class=HTMLResponse)  
async def home(request: Request, message: str = None): 
    return templates.TemplateResponse("home.html", {"request": request, "message": message})   

@app.get("/search", response_class=HTMLResponse)  
async def search(request: Request, dcu_number: str = None, date: str = None):
    query = "SELECT * FROM unregistered_dcu WHERE 1=1" 
    params = [] 
    if dcu_number: 
        query+= " AND DCU_number LIKE ?" 
        params.append(f"%{dcu_number}%") 
    
    if date: 
        query += " AND (first_connection LIKE ? OR last_connection LIKE ?)" 
        params.append(f"{date}%") 
        params.append(f"{date}%") 
    conn = get_db_connection() 
    clients = conn.execute(query, params).fetchall() 
    conn.close() 

    return templates.TemplateResponse("unregistered.html",{ 
        "request": request, 
        "clients": clients
    }) 
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
@app.get("/unregistered-dcus",response_class=HTMLResponse) 
async def Unregistered_device(request: Request, message: str=None): 
    conn = get_db_connection()  
    unregistered = conn.execute("SELECT *FROM unregistered_dcu").fetchall()    
    conn.close()
    return templates.TemplateResponse("unregistered.html", {"request": request, "Unregistered":unregistered,"message":message})   
@app.get("/read_parameter", response_class=HTMLResponse) 
async def read_DCU_parameter(request: Request, message: str=None): 
    conn = get_db_connection() 
    registered = conn.execute("SELECT *FROM registered_dcus").fetchall() 
    conn.close()
    return templates.TemplateResponse("read_parameter.html", {"request": request,"registered": registered}) 
@app.post("/deregister-dcu") 
async def deregister_dcu(dcu_number: str = Form(...)): 
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registered_dcus WHERE dcu_number = ?", (dcu_number,)) 
    conn.commit() 
    conn.close()
    return RedirectResponse(url = "/registered?message=DCU+{}+deregistered".format(dcu_number), status_code=303) 

