import sqlite3
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.utility_functions import get_meters_by_line, require_permission, template_response
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/instant-profile-read", response_class=HTMLResponse)
async def instant_profile_read(
    request: Request,
    message: str = None,
    page: int = 1,
    limit: int = 100,
    user: dict = Depends(require_permission("Data analysis"))
):
    table_name = "instantaneous_profile_readings"
    offset = (page - 1) * limit

    conn = get_db_connection()
    total_rows = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    readings = conn.execute(
        f"SELECT * FROM {table_name} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    conn.close()

    total_pages = (total_rows + limit - 1) // limit

    return template_response(
        request,
        "instant_profile_read.html",
        {
            "request": request,
            "readings": readings,
            "message": message,
            "page": page,
            "total_pages": total_pages,
        }
    )
@router.get("/search-instant-profile", response_class=HTMLResponse)
async def search_instant_profile(
    request: Request,
    meter_number: str = "",
    type: str = "Original",
    start_date: str = None,
    end_date: str = None,
    line: str = "",
    page: int = 1,
    limit: int = 100,
    user: dict = Depends(require_permission("Data analysis"))
):
    table_name = "instantaneous_profile_readings"
    if type == "Calculated":
        table_name = "instantaneous_profile_readings_calculated"

    base_query = f"FROM {table_name} WHERE 1=1"
    filter_params = []

    # ✅ Line or meter number filter
    
    if line:  
        meter_numbers_line = get_meters_by_line(line)
        placeholders = ",".join("?" for _ in meter_numbers_line)
        base_query += f" AND meter_number IN ({placeholders})"
        filter_params.extend(meter_numbers_line)
    elif meter_number:
        base_query += " AND meter_number LIKE ?"
        filter_params.append(f"%{meter_number}%")

    # ✅ Date filter
    if start_date and end_date:
        base_query += " AND timestamp BETWEEN ? AND ?"
        filter_params.extend([start_date, end_date])

    # ✅ Count total
    conn = get_db_connection()
    total_rows = conn.execute(f"SELECT COUNT(*) {base_query}", filter_params).fetchone()[0]

    # ✅ Paginated data
    offset = (page - 1) * limit
    readings = conn.execute(
        f"SELECT * {base_query} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (*filter_params, limit, offset)
    ).fetchall()
    conn.close()

    total_pages = (total_rows + limit - 1) // limit

    return template_response(
        request,
        "instant_profile_read.html",
        {
            "request": request,
            "readings": readings,
            "meter_number": meter_number,
            "selected_type": type,
            "start_date": start_date,
            "end_date": end_date,
            "line": line,
            "page": page,
            "total_pages": total_pages,
        }
    )