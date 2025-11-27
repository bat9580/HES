import sqlite3
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.utility_functions import require_permission, template_response

templates = Jinja2Templates(directory="templates")

router = APIRouter()


def _safe_fetch_all(conn: sqlite3.Connection, query: str) -> List[sqlite3.Row]:
    try:
        return conn.execute(query).fetchall()
    except sqlite3.OperationalError:
        return []


@router.get("/meter-download", response_class=HTMLResponse)
async def meter_download(
    request: Request,
    zone: str = Query("", alias="zone"),
    power_grid: str = Query("", alias="power_grid"),
    dcu_number: str = Query("", alias="dcu_number"),
    meter_number: str = Query("", alias="meter_number"),
    user: dict = Depends(require_permission("Archive")),
):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    zones = [row[0] for row in _safe_fetch_all(conn, "SELECT DISTINCT Zone FROM installed_meters WHERE Zone IS NOT NULL AND Zone != '' ORDER BY Zone")]  # type: ignore[arg-type]
    power_grids = [row[0] for row in _safe_fetch_all(conn, "SELECT DISTINCT station FROM installed_meters WHERE station IS NOT NULL AND station != '' ORDER BY station")]  # type: ignore[arg-type]

    dcu_rows = _safe_fetch_all(
        conn,
        "SELECT dcu_number, status FROM registered_dcus ORDER BY dcu_number",
    )

    dcu_list: List[Dict[str, Optional[str]]] = [
        {
            "number": row["dcu_number"],
            "status": (row["status"] or "").lower(),
            "active": False,
        }
        for row in dcu_rows
    ]

    selected_dcu = dcu_number or (dcu_list[0]["number"] if dcu_list else "")
    for dcu in dcu_list:
        if dcu["number"] == selected_dcu:
            dcu["active"] = True

    meters_query = "SELECT meter_number, com_address, device_type, type, status FROM installed_meters WHERE 1=1"
    params: List[str] = []

    if meter_number:
        meters_query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    if selected_dcu:
        meters_query += " AND (DCU_number = ? OR ? = '')"
        params.extend([selected_dcu, selected_dcu])
    if zone:
        meters_query += " AND (Zone LIKE ?)"
        params.append(f"%{zone}%")
    if power_grid:
        meters_query += " AND (station LIKE ?)"
        params.append(f"%{power_grid}%")

    meter_rows_raw = []
    try:
        meter_rows_raw = conn.execute(meters_query, params).fetchall()
    except sqlite3.OperationalError:
        meter_rows_raw = []

    conn.close()

    meter_rows = [
        {
            "point_no": idx + 1,
            "comm_address": row["com_address"],
            "meter_number": row["meter_number"],
            "meter_type": row["type"] or row["device_type"],
            "downloaded": (row["status"] or "").lower() == "installed",
            "online": (row["status"] or "").lower() == "installed",
            "result": row["status"],
        }
        for idx, row in enumerate(meter_rows_raw)
    ]

    summary = {
        "dcu_number": selected_dcu or None,
        "total_meter_count": len(meter_rows),
        "downloaded_meter_count": sum(1 for row in meter_rows if row["downloaded"]),
        "online_meter_count": sum(1 for row in meter_rows if row["online"]),
        "latency": "—",
        "last_sync": "—",
    }

    filters = {
        "zone": zone,
        "power_grid": power_grid,
        "dcu_number": dcu_number,
        "meter_number": meter_number,
    }

    context = {
        "request": request,
        "filters": filters,
        "zones": zones,
        "power_grids": power_grids,
        "dcu_numbers": [dcu["number"] for dcu in dcu_list],
        "dcu_list": dcu_list,
        "summary": summary,
        "meter_rows": meter_rows,
    }

    return template_response(request, "meter_download.html", context)


