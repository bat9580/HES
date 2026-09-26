import sqlite3
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List 

from services.database import get_db_connection
from services.state import connected_clients
from utils.utility_functions import require_permission, template_response
templates = Jinja2Templates(directory="templates")

router = APIRouter()


def _install_filters(request: Request, meter_number: str = "", DCU: str = "", Zone: str = "", station: str = ""):
    q = (request.query_params.get("q") or meter_number or "").strip()
    zone = (request.query_params.get("zone") or request.query_params.get("Zone") or Zone or "").strip()
    station = (request.query_params.get("station") or station or "").strip()
    dcu = (request.query_params.get("dcu") or request.query_params.get("DCU") or DCU or "").strip()
    return q, zone, station, dcu


def _text(value) -> str:
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value).strip())


def _load_installations(conn, q, zone, station, dcu):
    rows = conn.execute(
        "SELECT * FROM installed_meters ORDER BY meter_number"
    ).fetchall()
    records = []
    for row in rows:
        ct = row["CT_ratio"] if row["CT_ratio"] not in (None, "") else 1
        vt = row["VT_ratio"] if row["VT_ratio"] not in (None, "") else 1
        try:
            ct_num = int(ct)
        except (TypeError, ValueError):
            ct_num = 1
        try:
            vt_num = int(vt)
        except (TypeError, ValueError):
            vt_num = 1
        records.append(
            {
                "meter_number": _text(row["meter_number"]),
                "com_address": _text(row["com_address"]),
                "password": row["password"] or "",
                "device_type": _text(row["device_type"]),
                "type": _text(row["type"]),
                "remarks": _text(row["remarks"]),
                "status": _text(row["status"]),
                "line": _text(row["line"]),
                "CT_ratio": ct_num,
                "VT_ratio": vt_num,
                "DCU_number": _text(row["DCU_number"]),
                "Zone": _text(row["Zone"]),
                "station": _text(row["station"]),
                "task": row["task"] or "",
            }
        )

    online_keys = {str(key) for key in connected_clients.keys()}
    total = len(records)
    transformer = sum(1 for item in records if item["CT_ratio"] != 1 or item["VT_ratio"] != 1)
    lines = {item["line"] for item in records if item["line"]}
    dcus = {item["DCU_number"] for item in records if item["DCU_number"]}
    stations = {item["station"] for item in records if item["station"]}
    zones = {item["Zone"] for item in records if item["Zone"]}
    try:
        registered = conn.execute("SELECT COUNT(*) AS c FROM registered_meters").fetchone()["c"]
    except sqlite3.Error:
        registered = total

    dcu_options = set(dcus)
    try:
        for row in conn.execute(
            "SELECT dcu_number FROM registered_dcus WHERE dcu_number IS NOT NULL AND dcu_number != ''"
        ):
            dcu_options.add(str(row["dcu_number"]))
    except sqlite3.Error:
        pass

    filtered = records
    if q:
        needle = q.lower()
        filtered = [
            item
            for item in filtered
            if needle in item["meter_number"].lower()
            or needle in item["com_address"].lower()
            or needle in item["remarks"].lower()
        ]
    if zone:
        filtered = [item for item in filtered if zone.lower() in item["Zone"].lower()]
    if station:
        filtered = [item for item in filtered if station.lower() in item["station"].lower()]
    if dcu:
        filtered = [item for item in filtered if dcu.lower() in item["DCU_number"].lower()]

    return {
        "installed_meters": filtered,
        "install_total": total,
        "install_shown": len(filtered),
        "registered_total": registered,
        "transformer_count": transformer,
        "direct_count": total - transformer,
        "line_count": len(lines),
        "station_count": len(stations),
        "dcu_count": len(dcus),
        "online_count": sum(1 for item in records if item["meter_number"] in online_keys),
        "zone_options": sorted(zones),
        "station_options": sorted(stations),
        "dcu_options": sorted(dcu_options),
        "q": q,
        "zone": zone,
        "station": station,
        "dcu": dcu,
        "meter_number": q,
        "Zone": zone,
        "DCU": dcu,
        "page_time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
    }


@router.get("/meter-installation", response_class=HTMLResponse)
async def meter_installation(
    request: Request,
    message: str = None,
    user: dict = Depends(require_permission("Archive")),
):
    q, zone, station, dcu = _install_filters(request)
    conn = get_db_connection()
    context = _load_installations(conn, q, zone, station, dcu)
    conn.close()
    context.update(
        {
            "request": request,
            "message": request.query_params.get("message") or message,
        }
    )
    return template_response(request, "meter_installation.html", context) 
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
    needs_esp32 = "esp32" in meter_type_normalized or modem_type.strip().lower() == "ddsd285_2018"
    if needs_esp32 and not dcu_value:
        conn.close()
        return RedirectResponse(
            url="/meter-installation?message=⚠️ ESP32 device address is required for DDSD285_2018.",
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
async def search_meter_installation(
    request: Request,
    meter_number: str = "",
    DCU: str = "",
    Zone: str = "",
    station: str = "",
    user: dict = Depends(require_permission("Archive")),
):
    q, zone, station, dcu = _install_filters(request, meter_number, DCU, Zone, station)
    conn = get_db_connection()
    context = _load_installations(conn, q, zone, station, dcu)
    conn.close()
    context.update(
        {
            "request": request,
            "message": request.query_params.get("message"),
        }
    )
    return template_response(request, "meter_installation.html", context)
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

