import sqlite3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/unregistered-device",response_class=HTMLResponse) 
async def Unregistered_device(request: Request, message: str=None): 
    conn = get_db_connection()   
    unregistered = conn.execute("SELECT *FROM unregistered_dcu").fetchall()   
    print(unregistered)    
    conn.close()
    return templates.TemplateResponse("unregistered.html", {"request": request, "Unregistered":unregistered,"message":message})   
@router.get("/search-unregistered-dcu", response_class=HTMLResponse)
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
@router.post("/clear-unregistered-dcu")
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
@router.post("/install-unregistered-dcu") 
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

@router.post("/register_dcu") 
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
                   