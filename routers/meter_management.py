import sqlite3
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from services.state import connected_clients
from utils.utility_functions import require_permission, template_response
templates = Jinja2Templates(directory="templates")

router = APIRouter()

_DEVICE_CHOICES = [
    "GPRS Meter",
    "PLC Meter",
    "Lorawan Meter",
    "RS485 with EDAT",
    "RS485 with ESP32",
]
_TYPE_CHOICES = ["DDSY283", "DTSD545S", "DTSD546", "DDSD285_2018", "DDSD285-2018", "C2000"]


def _meter_filters(request: Request, meter_number: str = "", device_type: str = ""):
    q = (request.query_params.get("q") or meter_number or "").strip()
    status = (request.query_params.get("status") or "").strip()
    device_type = (request.query_params.get("device_type") or device_type or "").strip()
    meter_type = (request.query_params.get("type") or "").strip()
    return q, status, device_type, meter_type


def _load_meter_page(conn, q, status, device_type, meter_type):
    query = "SELECT * FROM registered_meters WHERE 1=1"
    params = []
    if q:
        query += " AND (meter_number LIKE ? OR com_address LIKE ? OR IFNULL(remarks,'') LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    if status:
        query += " AND lower(status) = lower(?)"
        params.append(status)
    if device_type:
        query += " AND device_type LIKE ?"
        params.append(f"%{device_type}%")
    if meter_type:
        query += " AND type LIKE ?"
        params.append(f"%{meter_type}%")
    query += " ORDER BY meter_number"
    registered_meters = conn.execute(query, params).fetchall()

    all_rows = conn.execute("SELECT meter_number, status FROM registered_meters").fetchall()
    online_numbers = {str(key) for key in connected_clients.keys()}
    total = len(all_rows)
    online = sum(1 for row in all_rows if str(row["meter_number"]) in online_numbers)
    installed = sum(1 for row in all_rows if (row["status"] or "").lower() == "installed")

    readings = {}
    try:
        latest = conn.execute(
            """
            SELECT e.meter_number, e.timestamp, e.import_total_active_energy
            FROM energy_profile_readings e
            INNER JOIN (
                SELECT meter_number, MAX(timestamp) AS ts
                FROM energy_profile_readings
                GROUP BY meter_number
            ) x ON x.meter_number = e.meter_number AND x.ts = e.timestamp
            """
        ).fetchall()
        for row in latest:
            readings[str(row["meter_number"])] = {
                "timestamp": row["timestamp"],
                "kwh": row["import_total_active_energy"],
            }
    except sqlite3.Error:
        readings = {}

    device_options = list(_DEVICE_CHOICES)
    type_options = list(_TYPE_CHOICES)
    for row in conn.execute(
        "SELECT DISTINCT device_type, type FROM registered_meters"
    ).fetchall():
        if row["device_type"] and row["device_type"] not in device_options:
            device_options.append(row["device_type"])
        if row["type"] and row["type"] not in type_options:
            type_options.append(row["type"])

    return {
        "registered_meters": registered_meters,
        "meter_total": total,
        "meter_online": online,
        "meter_offline": max(total - online, 0),
        "meter_installed": installed,
        "online_numbers": sorted(online_numbers),
        "readings": readings,
        "device_options": device_options,
        "type_options": type_options,
        "q": q,
        "status": status,
        "device_type": device_type,
        "meter_type": meter_type,
    }


@router.get("/meter-management", response_class=HTMLResponse)
async def meter_management(request:Request, message: str = None,user: dict = Depends(require_permission("Warehouse"))):  
    message = request.query_params.get("message")
    q, status, device_type, meter_type = _meter_filters(request)
    conn = get_db_connection()
    context = _load_meter_page(conn, q, status, device_type, meter_type)
    conn.close()
    context.update({"request": request, "message": message})
    return template_response(request, "meter_management.html", context)
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
                remarks = ?
            WHERE meter_number = ? 
        """, (meter_number, comm_address, device_type, type, password, remarks,original_meter_number)) 
        conn.commit()
        message = f"✅ Meter edited successfully." 
    except sqlite3.IntegrityError: 
        message = f"⚠️ same METER NUMBER is already registered."  
    finally: 
        conn.close() 
    return RedirectResponse(url=f"/meter-management?message={message}", status_code=303) 
@router.post("/delete-meter")
async def delete_meter(meter_number: str = Form(...)):
    conn = get_db_connection()
    cursor = conn.cursor()

    meter = conn.execute(
        "SELECT * FROM registered_meters WHERE meter_number = ?",
        (meter_number,),
    ).fetchone()

    if not meter:
        conn.close()
        message = "⚠️ Meter not found."
        return RedirectResponse(url=f"/meter-management?message={message}", status_code=303)

    was_installed = (meter["status"] or "").lower() == "installed"
    installed_row = conn.execute(
        "SELECT 1 FROM installed_meters WHERE meter_number = ?",
        (meter_number,),
    ).fetchone()

    try:
        if was_installed or installed_row:
            cursor.execute(
                "DELETE FROM installed_meters WHERE meter_number = ?",
                (meter_number,),
            )
            was_installed = True

        cursor.execute(
            "DELETE FROM registered_meters WHERE meter_number = ?",
            (meter_number,),
        )
        conn.commit()

        if was_installed:
            message = "✅ Meter was dismantled and deleted successfully."
        else:
            message = "✅ METER is successfully deleted."
    except Exception as e:
        conn.rollback()
        message = f"⚠️ Failed to delete meter: {e}"
    finally:
        conn.close()

    return RedirectResponse(url=f"/meter-management?message={message}", status_code=303)

@router.get("/search-meter", response_class=HTMLResponse)
async def search_meter(request:Request, meter_number: str = "", device_type: str = "",user: dict = Depends(require_permission("Warehouse"))):
    q, status, device_type, meter_type = _meter_filters(request, meter_number, device_type)
    conn = get_db_connection()
    context = _load_meter_page(conn, q, status, device_type, meter_type)
    conn.close()
    context.update({"request": request, "message": request.query_params.get("message")})
    return template_response(request, "meter_management.html", context)

