import sqlite3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
templates = Jinja2Templates(directory="templates")

router = APIRouter()

@router.get("/meter-management", response_class=HTMLResponse)
async def meter_management(request:Request, message: str = None): 
    message = request.query_params.get("message") 
    conn = get_db_connection()
    registered_meters = conn.execute("SELECT *FROM registered_meters ").fetchall()
    conn.close() 
    return templates.TemplateResponse("meter_management.html", {"request": request, "message": message, "registered_meters": registered_meters})
@router.post("/add-meter")
async def add_meter(
    request: Request,
    meter_number: str = Form(...),
    comm_address: str = Form(...), 
    device_type: str = Form(...), 
    type: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...)
):   
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO registered_meters 
            (meter_number, com_address, password, device_type, type, remarks, status)
            VALUES (?, ?, ?, ?, ?, ?, ?) 
        """, (meter_number, comm_address, password, device_type, type, remarks, status))
        conn.commit()
        message = "✅ Meter added successfully."
    except sqlite3.IntegrityError:
        message = "⚠️ Same METER NUMBER is already registered."
    finally:
        conn.close()

    return RedirectResponse(url=f"/meter-management?message={message}", status_code=303)
@router.post("/edit-meter")
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
@router.post("/delete-meter") 
async def delete_meter( meter_number : str = Form(...)):   
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM registered_meters WHERE 1=1"  
    params = [] 
    if meter_number: 
        query+= " AND meter_number LIKE ?"   
        params.append(f"%{meter_number}%")  

    meter = conn.execute(query, params).fetchone()  
    if meter["status"]  == "installed": 
        message = f"⚠️ please dismantle the METER first." 
    else:
          
        cursor.execute("DELETE FROM registered_meters WHERE meter_number = ?", (meter_number,)) 
        conn.commit()
        message = f"✅ METER is successfully deleted."   

    conn.close()
    return RedirectResponse(url=f"/meter-management?message={message}", status_code=303) 

@router.get("/search-meter", response_class=HTMLResponse)
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

