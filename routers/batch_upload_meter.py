import sqlite3
import json 
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional 

from services.database import get_db_connection
from utils.utility_functions import template_response
templates = Jinja2Templates(directory="templates")

router = APIRouter()
@router.get("/batch-upload-meter",response_class=HTMLResponse)
async def batch_upload(request: Request, message: str=None):
    return template_response(request, "batch_upload.html", {"request": request,"message":message}) 



@router.get("/result") 
async def result(request: Request):
    return template_response(request, "batch_upload_result.html", 
    {
        "request": request,
        "add_success": 0,
        "update_success": 0,
        "failed": 0,
        "total": 0,
        "meters": [], 
        "dcus": []
    })
    

@router.get("/step2", name="next_step")
async def step2(request: Request):
    return template_response(request, "batch_upload_result.html")  

@router.get("/step1", name="previous_step")
async def step1(request: Request):
    return template_response(request, "batch_upload.html")   
@router.post("/next_step") 
async def next_step(request: Request):
    data = await request.json()
    meters = data.get("meters", [] ) 

    conn = get_db_connection()
    installed = conn.execute("SELECT * FROM installed_meters").fetchall() 
    installed_set = {row["meter_number"] for row in installed} 

    # separate into found / not found
    found = [m for m in meters if str(m) in installed_set]
    not_found = [m for m in meters if str(m) not in installed_set] 
    return JSONResponse({
        "total_uploaded": len(meters), 
        "already_installed": found,
        "new_meters": not_found
    }) 
@router.post("/install_meters")
async def install_meters(request: Request):
    data = await request.json() 
    meters = data.get("meters",[])
    meters = json.loads(meters)   
    meters = meters[1:] 
    status = 'installed' 
    conn = get_db_connection() 
    cursor = conn.cursor()  
    print(meters)  
    try: 
        for meter in meters:
            try:      
                cursor.execute("""  
                    INSERT INTO installed_meters  
                    (meter_number, com_address,password, device_type, type,status, remarks,line,CT_ratio,VT_ratio) 
                    VALUES (?,?,?,?,?,?,?,?,?,?) 
                """, (meter[0], meter[1], meter[7], meter[2], meter[8],status, meter[5],meter[6],meter[3], meter[4]))  
                cursor.execute("""
                    INSERT INTO registered_meters 
                    (meter_number, com_address, password, device_type, type, remarks, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?) 
                """, (meter[0], meter[1], meter[7], meter[2], meter[8], meter[5], status))  
                conn.commit() 
            except sqlite3.IntegrityError:  
                    cursor.execute("""
                        UPDATE installed_meters
                        SET com_address = ?,
                            password = ?,
                            device_type = ?,
                            type = ?,
                            status = ?,
                            remarks = ?,
                            line = ?,
                            CT_ratio = ?,
                            VT_ratio = ?
                        WHERE meter_number = ?
                    """, (meter[1], meter[7], meter[2], meter[8], status, meter[5], meter[6], meter[3], meter[4], meter[0]))

                    # Update registered_meters if already exists
                    cursor.execute("""
                        UPDATE registered_meters
                        SET com_address = ?,
                            password = ?,
                            device_type = ?,
                            type = ?,
                            remarks = ?,
                            status = ?
                        WHERE meter_number = ?
                    """, (meter[1], meter[7], meter[2], meter[8], meter[5], status, meter[0]))  
        message = f"✅ Meter installed successfully." 
        success = True
    except: 
        message = f"⚠️ Meter installation failed." 
        success = False    
    finally:   
        conn.close()
    return JSONResponse({
        "success": success, 
        "message": message,
    })  
 
