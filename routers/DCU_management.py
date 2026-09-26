import sqlite3
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from services.state import connected_clients
from utils.utility_functions import require_permission, template_response

templates = Jinja2Templates(directory="templates")

router = APIRouter()


def _dcu_filters(request: Request, dcu_number: str = "", status: str = ""):
    q = (request.query_params.get("q") or dcu_number or "").strip()
    status = (request.query_params.get("status") or status or "").strip()
    network = (request.query_params.get("network") or "").strip()
    station = (request.query_params.get("station") or "").strip()
    return q, status, network, station


def _client_for(number: str):
    if number in connected_clients:
        return connected_clients[number]
    for key, client in connected_clients.items():
        if str(key) == number:
            return client
    return None


def _peer_address(client) -> str:
    if not client:
        return ""
    addr = client.get("addr")
    if isinstance(addr, (list, tuple)) and addr:
        host = str(addr[0])
        if len(addr) > 1 and addr[1]:
            return f"{host}:{addr[1]}"
        return host
    if isinstance(addr, str):
        return addr
    return ""


def _load_dcu_page(conn, q, status, network, station):
    all_rows = conn.execute(
        "SELECT * FROM registered_dcus ORDER BY dcu_number"
    ).fetchall()

    by_dcu = {}
    networks = set()
    stations = set()
    try:
        meter_rows = conn.execute(
            """
            SELECT DCU_number, meter_number, device_type, station
            FROM installed_meters
            WHERE DCU_number IS NOT NULL AND TRIM(DCU_number) != ''
            """
        ).fetchall()
    except sqlite3.Error:
        meter_rows = []

    for row in meter_rows:
        key = str(row["DCU_number"])
        bucket = by_dcu.setdefault(
            key, {"meters": [], "types": {}, "stations": set()}
        )
        bucket["meters"].append(str(row["meter_number"]))
        device = (row["device_type"] or "").strip()
        if device:
            bucket["types"][device] = bucket["types"].get(device, 0) + 1
            networks.add(device)
        place = (row["station"] or "").strip()
        if place:
            bucket["stations"].add(place)
            stations.add(place)

    last_map = {}
    try:
        for row in conn.execute(
            "SELECT dcu_number, ip_address, last_connection FROM unregistered_dcu"
        ):
            last_map[str(row["dcu_number"])] = {
                "ip": (row["ip_address"] or "").strip(),
                "last": (row["last_connection"] or "").strip(),
            }
    except sqlite3.Error:
        last_map = {}

    online_keys = {str(key) for key in connected_clients.keys()}
    records = []
    for row in all_rows:
        number = str(row["dcu_number"])
        info = by_dcu.get(number, {"meters": [], "types": {}, "stations": set()})
        meters = info["meters"]
        online_meters = sum(1 for meter in meters if meter in online_keys)
        types = info["types"]
        dominant = max(types, key=types.get) if types else ""
        client = _client_for(number)
        saved = last_map.get(number, {})
        ip = _peer_address(client) or saved.get("ip") or ""
        records.append(
            {
                "dcu_number": number,
                "com_address": row["com_address"] or "",
                "remarks": row["remarks"] or "",
                "status": row["status"] or "",
                "password": row["password"] or "",
                "meter_count": len(meters),
                "online_meters": online_meters,
                "meter_pct": int(round(online_meters / len(meters) * 100)) if meters else 0,
                "network": dominant,
                "station": ", ".join(sorted(info["stations"])),
                "ip": ip,
                "last_connection": saved.get("last") or "",
                "online": client is not None,
            }
        )

    filtered = records
    if q:
        needle = q.lower()
        filtered = [
            item
            for item in filtered
            if needle in item["dcu_number"].lower()
            or needle in item["com_address"].lower()
            or needle in (item["remarks"] or "").lower()
        ]
    if status:
        filtered = [
            item for item in filtered if item["status"].lower() == status.lower()
        ]
    if network:
        filtered = [
            item for item in filtered if network.lower() in item["network"].lower()
        ]
    if station:
        filtered = [
            item for item in filtered if station.lower() in item["station"].lower()
        ]

    total = len(records)
    online = sum(1 for item in records if item["online"])
    installed = sum(1 for item in records if item["status"].lower() == "installed")
    assigned = sum(item["meter_count"] for item in records)
    names = sorted(networks)

    return {
        "registered_dcus": filtered,
        "dcu_total": total,
        "dcu_online": online,
        "dcu_installed": installed,
        "dcu_assigned_meters": assigned,
        "dcu_avg_meters": (assigned / total) if total else 0,
        "network_count": len(names),
        "network_summary": " • ".join(names) if names else "тоолуур холбоогүй",
        "network_options": names,
        "station_options": sorted(stations),
        "q": q,
        "status": status,
        "network": network,
        "station": station,
        "dcu_number": q,
        "page_time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
    }


@router.get("/DCU-management", response_class=HTMLResponse)
async def dcu_management(
    request: Request,
    message: Optional[str] = None,
    user: dict = Depends(require_permission("Warehouse")),
):
    message = request.query_params.get("message")
    q, status, network, station = _dcu_filters(request)
    conn = get_db_connection()
    context = _load_dcu_page(conn, q, status, network, station)
    conn.close()
    context.update({"request": request, "message": message})
    return template_response(request, "DCU_management.html", context)


@router.post("/add-dcu")
async def add_dcu(
    request: Request,
    dcu_number: str = Form(...),
    comm_address: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO registered_dcus 
            (dcu_number, com_address, password, remarks, status)
            VALUES (?, ?, ?, ?, ?)
        """,
            (dcu_number, comm_address, password, remarks, status),
        )
        conn.commit()
        message = "✅ DCU added successfully."
    except sqlite3.IntegrityError:
        message = "⚠️ Same DCU NUMBER is already registered."
    finally:
        conn.close()
        

    return RedirectResponse(url=f"/DCU-management?message={message}", status_code=303)


@router.post("/edit-dcu")
async def edit_dcu(
    request: Request,
    original_dcu_number: str = Form(...),
    dcu_number: str = Form(...),
    comm_address: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE registered_dcus 
            SET dcu_number = ?,
                com_address = ?,
                password = ?, 
                remarks = ?,
                status = ? 
            WHERE dcu_number = ?
        """,
            (dcu_number, comm_address, password, remarks, status, original_dcu_number),
        )
        conn.commit()
        message = "✅ DCU edited successfully."
    except sqlite3.IntegrityError:
        message = "⚠️ Same DCU NUMBER is already registered."
    finally:
        conn.close()
    return RedirectResponse(url=f"/DCU-management?message={message}", status_code=303)


@router.post("/delete-dcu")
async def delete_dcu(dcu_number: str = Form(...)):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM registered_dcus WHERE 1=1"
    params: List[str] = []
    if dcu_number:
        query += " AND dcu_number LIKE ?"
        params.append(f"%{dcu_number}%")

    dcu = conn.execute(query, params).fetchone()

    if not dcu:
        message = "⚠️ DCU not found."
    else:
        # Check if there are any meters still installed on this DCU
        meter_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM installed_meters WHERE DCU_number = ?",
            (dcu_number,),
        ).fetchone()
        meter_count = meter_row["cnt"] if meter_row is not None else 0

        if meter_count > 0:
            message = (
                f"⚠️ Please uninstall all meters ({meter_count}) from this DCU before deleting it."
            )
        else:
            cursor.execute(
                "DELETE FROM registered_dcus WHERE dcu_number = ?", (dcu_number,)
            )
            conn.commit()
            message = "✅ DCU is successfully deleted."

    conn.close()
    return RedirectResponse(url=f"/DCU-management?message={message}", status_code=303)


@router.get("/search-dcu", response_class=HTMLResponse)
async def search_dcu(
    request: Request,
    dcu_number: str = "",
    status: str = "",
    user: dict = Depends(require_permission("Warehouse")),
):
    q, status, network, station = _dcu_filters(request, dcu_number, status)
    conn = get_db_connection()
    context = _load_dcu_page(conn, q, status, network, station)
    conn.close()
    context.update(
        {
            "request": request,
            "message": request.query_params.get("message"),
        }
    )
    return template_response(request, "DCU_management.html", context)