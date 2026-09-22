import sqlite3
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List 

from services.database import get_db_connection
from utils.utility_functions import require_permission, template_response
templates = Jinja2Templates(directory="templates")

router = APIRouter()
@router.get("/meter-installation",response_class=HTMLResponse)
async def meter_installation(request: Request, message: str=None, user: dict = Depends(require_permission("Archive"))): 
    status = "installed"   
    conn = get_db_connection()   
    installed_meters = conn.execute("SELECT *FROM installed_meters").fetchall()     
    conn.close
    return template_response(request,"meter_installation.html", {"request": request, "installed_meters":installed_meters,"message":message}) 
@router.post('/install-meter')
async def install_meter(
    request: Request,
    meter_number: str = Form(...),
    comm_address: str = Form(...),
    meter_type: str = Form(...),
    modem_type: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    CT_ratio: Optional[int] = Form(None),
    VT_ratio: Optional[int] = Form(None),
    line: str = Form(None),
    dcu_number: Optional[str] = Form(None),
):
    status = 'installed'
    conn = get_db_connection() 
    cursor = conn.cursor() 
    # Set default value of 1 if CT_ratio is None, empty, or 0
    if CT_ratio is None or CT_ratio == '' or CT_ratio == 0:
        CT_ratio = 1
    else:
        try:
            CT_ratio = int(CT_ratio)
        except (ValueError, TypeError):
            CT_ratio = 1
    # Set default value of 1 if VT_ratio is None, empty, or 0
    if VT_ratio is None or VT_ratio == '' or VT_ratio == 0:
        VT_ratio = 1
    else:
        try:
            VT_ratio = int(VT_ratio)
        except (ValueError, TypeError):
            VT_ratio = 1 
     
    meter_type_normalized = meter_type.strip().lower()
    is_plc_meter = "plc" in meter_type_normalized
    dcu_value = dcu_number.strip() if dcu_number else None

    if is_plc_meter and not dcu_value:
        conn.close()
        return RedirectResponse(
            url="/meter-installation?message=⚠️ DCU number is required for PLC meters.",
            status_code=303,
        )

    try:
        cursor.execute(
            """
            INSERT INTO installed_meters
            (meter_number, com_address, password, device_type, type, status, remarks, line, CT_ratio, VT_ratio, DCU_number)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                meter_number,
                comm_address,
                password,
                meter_type,
                modem_type,
                status,
                remarks,
                line,
                CT_ratio,
                VT_ratio,
                dcu_value,
            ),
        )
        cursor.execute("""
            UPDATE registered_meters
            SET status = ?
            WHERE meter_number = ?
        """, (status, meter_number)) 
        conn.commit()
        message = f"✅ Meter installed successfully."  
    except sqlite3.IntegrityError: 
        message = f"⚠️ same METER NUMBER is already registered." 
    finally:
        conn.close()
     
    return RedirectResponse(url=f"/meter-installation?message={message}", status_code = 303)
@router.post("/edit-meter-installation")
async def add_meter(
    request: Request,
    original_meter_number: str = Form(...), 
    meter_number: str = Form(...),
    comm_address: str = Form(...), 
    device_type: str = Form(...), 
    type: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    CT_ratio: str = Form(None),   
    VT_ratio: str = Form(None),  
    line: str = Form(...)):  
    
    conn = get_db_connection() 
    cursor = conn.cursor() 
    # Set default value of 1 if VT_ratio is None, empty string, whitespace, or 0
    if VT_ratio is None or (isinstance(VT_ratio, str) and not VT_ratio.strip()) or VT_ratio == 0:
        VT_ratio = 1
    else:
        try:
            VT_ratio = int(VT_ratio)
            if VT_ratio == 0:
                VT_ratio = 1
        except (ValueError, TypeError):
            VT_ratio = 1
    # Set default value of 1 if CT_ratio is None, empty string, whitespace, or 0
    if CT_ratio is None or (isinstance(CT_ratio, str) and not CT_ratio.strip()) or CT_ratio == 0:
        CT_ratio = 1
    else:
        try:
            CT_ratio = int(CT_ratio)
            if CT_ratio == 0:
                CT_ratio = 1
        except (ValueError, TypeError):
            CT_ratio = 1 
    
    try: 
        cursor.execute("""
            UPDATE installed_meters 
            SET meter_number = ?, 
                com_address = ?,
                device_type = ?,
                type = ?, 
                password = ?, 
                remarks = ?,
                line = ?,
                CT_ratio = ?, 
                VT_ratio = ?
            WHERE meter_number = ? 
        """, (meter_number, comm_address, device_type, type, password, remarks,line,CT_ratio, VT_ratio,original_meter_number)) 
        conn.commit()
        message = f"✅ Meter edited successfully." 
    except sqlite3.IntegrityError: 
        message = f"⚠️ same METER NUMBER is already registered."  
    finally: 
        conn.close() 
    return RedirectResponse(url=f"/meter-installation?message={message}", status_code=303) 

@router.post('/uninstall-meter')
async def uninstall_meter(meter_number: str = Form(...)): 
    print(meter_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM installed_meters WHERE meter_number = ?", (meter_number,)) 
    cursor.execute("""
            UPDATE registered_meters
            SET status = ?
            WHERE meter_number = ?
        """, ('Archived', meter_number)) 
    conn.commit()
    conn.close()
    message = f"✅ METER is successfully dismantled."     
    return RedirectResponse(url=f"/meter-installation?message={message}", status_code=303)
@router.get("/search-meter-installation", response_class=HTMLResponse)
async def search_meter_installation(request:Request, meter_number: str = "", DCU: str = "",Zone: str = "", station: str = "", user: dict = Depends(require_permission("Archive"))):  
    query = "SELECT * FROM installed_meters WHERE 1=1"  
    params = []
    if meter_number: 
        query+= " AND meter_number LIKE ?"   
        params.append(f"%{meter_number}%") 
    if DCU:  
        query += " AND DCU_number LIKE ?"  
        params.append(f"%{DCU}%") 
    if station:  
        query += " AND station LIKE ?"  
        params.append(f"%{station}%") 
    if Zone:  
        query += " AND  Zone LIKE ?"  
        params.append(f"%{ Zone }%")
    conn = get_db_connection()
    searched_meters = conn.execute(query, params).fetchall() 
    conn.close() 
    
 
    return template_response(request,"meter_installation.html",{   
        "request": request, 
        "installed_meters": searched_meters,
        "meter_number": meter_number,
        "Zone" : Zone, 
        "station": station, 
        "DCU": DCU, 
    })
@router.get("/get-installed-meters")
async def get_installed_meters():
    conn = get_db_connection()
    meters = conn.execute("SELECT meter_number FROM installed_meters").fetchall()
    meter_numbers = [meter['meter_number'] for meter in meters]
    conn.close()
    return JSONResponse(meter_numbers) 
@router.get("/get-zone")
async def get_zone():
    zones = ["даланзадгад","цагаанхад"]
    return JSONResponse(zones)  
@router.get("/get-station")
async def get_station():
    stations = ["TP-13","TP-18"] 
    return JSONResponse(stations)
@router.get("/get-installed-dcu")
async def get_dcu():
    conn = get_db_connection()
    try:
        # Return all registered DCUs (we can filter by status later if needed)
        # This ensures the dropdown works and shows available DCUs
        all_dcus = conn.execute(
            "SELECT dcu_number FROM registered_dcus WHERE dcu_number IS NOT NULL AND dcu_number != '' ORDER BY dcu_number"
        ).fetchall()
        dcu_numbers = [dcu['dcu_number'] for dcu in all_dcus]
    except Exception as e:
        # Log error and return empty list
        print(f"Error fetching DCUs: {e}")
        import traceback
        traceback.print_exc()
        dcu_numbers = []
    finally:
        conn.close()
    return JSONResponse(dcu_numbers)     
@router.get("/get-archived-meter")
async def get_archived_meter(device_type: str = ""):
    status = "Archived"
    conn = get_db_connection()
    query = "SELECT meter_number FROM registered_meters WHERE status = ?"
    params: List[str] = [status]
    if device_type:
        query += " AND device_type = ?"
        params.append(device_type.strip())

    archived_meters = conn.execute(query, params).fetchall()
    meter_numbers = [meter["meter_number"] for meter in archived_meters]
    conn.close()
    return JSONResponse(meter_numbers)

@router.get("/get-meter-details/{meter_number}")
async def get_meter_details(meter_number: str):
    conn = get_db_connection()
    query = """
        SELECT meter_number, device_type, com_address, type, status, remarks, password
        FROM registered_meters
        WHERE meter_number = ?
    """
    meter = conn.execute(query, (meter_number,)).fetchone()
    conn.close() 

    if meter:
        return JSONResponse(dict(meter))
    else:
        return JSONResponse({"error": "Meter not found"}, status_code=404) 

