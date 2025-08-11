import sqlite3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
templates = Jinja2Templates(directory="templates")

router = APIRouter()
@router.get("/DCU-management", response_class=HTMLResponse)
async def dcu_management(request: Request, message: str = None):
    conn = get_db_connection()
    dcus = conn.execute("SELECT *FROM registered_dcus").fetchall() 
    conn.close() 
    return templates.TemplateResponse("DCU_management.html",{"request": request, "registered_dcus":dcus , "message": message})  
@router.post("/add-dcu") 
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
@router.post("/edit-dcu")
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
@router.post("/delete-dcu")  
async def delete_dcu( dcu_number : str = Form(...)):   
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registered_dcus WHERE dcu_number = ?", (dcu_number,)) 
    conn.commit()
    conn.close()
    message = f"✅ DCU is successfully deleted."  
    return RedirectResponse(url=f"/DCU-management?message={message}", status_code=303) 
@router.get("/search-dcu", response_class=HTMLResponse)
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