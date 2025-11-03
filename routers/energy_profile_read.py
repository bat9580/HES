import sqlite3
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.utility_functions import get_meters_by_line, require_permission, template_response
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
# @router.get("/energy-profile-read",response_class=HTMLResponse) 
# async def profile_read(request: Request, message: str=None,user: dict = Depends(require_permission("Data analysis"))): 
#     conn = get_db_connection()   
#     readings = conn.execute("SELECT *FROM energy_profile_readings").fetchall()
#     conn.close()
#     return template_response(request, "energy_profile_read.html", {"request": request, "readings":readings,"message":message})   
@router.get("/energy-profile-read", response_class=HTMLResponse)
async def profile_read(
    request: Request,
    page: int = 1,
    limit: int = 100,
    message: str = None,
    user: dict = Depends(require_permission("Data analysis"))
):
    offset = (page - 1) * limit
    conn = get_db_connection()

    # total count for pagination controls
    total_rows = conn.execute("SELECT COUNT(*) FROM energy_profile_readings").fetchone()[0]
    
    readings = conn.execute(
        "SELECT * FROM energy_profile_readings LIMIT ? OFFSET ?", 
        (limit, offset)
    ).fetchall()

    conn.close()

    total_pages = (total_rows + limit - 1) // limit  # round up

    return template_response(
        request,
        "energy_profile_read.html",
        {
            "request": request,
            "readings": readings,
            "page": page,
            "total_pages": total_pages,
            "message": message
        }
    )

@router.get("/search-energy-profile", response_class=HTMLResponse)
async def search_energy_load_profile(
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
    table_name = "energy_profile_readings" 
    if type == "Calculated":  
        table_name = "energy_profile_readings_calculated" 

    query = f"SELECT * FROM {table_name} WHERE 1=1"
    count_query = f"SELECT COUNT(*) FROM {table_name} WHERE 1=1"
    params = []
    count_params = []

    # ✅ Filter by line or meter number
    meter_numbers_line = get_meters_by_line(line)
    if meter_numbers_line:
        placeholders = ",".join("?" for _ in meter_numbers_line)
        query += f" AND meter_number IN ({placeholders})"
        count_query += f" AND meter_number IN ({placeholders})"
        params.extend(meter_numbers_line)
        count_params.extend(meter_numbers_line)
    elif meter_number:
        query += " AND meter_number LIKE ?"
        count_query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
        count_params.append(f"%{meter_number}%")

    # ✅ Filter by date
    if start_date and end_date:
        query += " AND timestamp BETWEEN ? AND ?"
        count_query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
        count_params.extend([start_date, end_date])

    # ✅ Get total rows first (for pagination UI)
    conn = get_db_connection()
    total_rows = conn.execute(count_query, count_params).fetchone()[0]

    # ✅ Add pagination (LIMIT & OFFSET)
    offset = (page - 1) * limit
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    readings = conn.execute(query, params).fetchall()
    conn.close()

    total_pages = (total_rows + limit - 1) // limit

    return template_response(
        request,
        "energy_profile_read.html",
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

