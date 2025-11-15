import sqlite3
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.parameters import obis_to_column
from utils.utility_functions import get_meters_by_line, require_permission, template_response 
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/data-read", response_class=HTMLResponse)
async def data_read(
    request: Request,
    page: int = 1,
    limit: int = 100,
    message: str = None,
    user: dict = Depends(require_permission("Data analysis"))
):
    conn = get_db_connection()
    unregistered = conn.execute("SELECT * FROM unregistered_dcu").fetchall()
    default_obis = "1.8.0"  # your column name for 1.8.0
    mapping = obis_to_column.get(default_obis) 
    table_name, column_name = mapping
    offset = max(page - 1, 0) * limit

    total_rows = conn.execute(
        f"SELECT COUNT(*) FROM {table_name}" 
    ).fetchone()[0]

    readings = conn.execute(
        f"""
        SELECT meter_number, timestamp, {column_name}
        FROM {table_name}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset)
    ).fetchall()
    print(readings) 
    conn.close()
    total_pages = (total_rows + limit - 1) // limit if limit else 1

    # Render template
    return template_response(
        request,
        "data_read.html",
        {
            "request": request,
            "message": message,
            "readings": readings,
            "meter_number": "",
            "selected_obis_code": "1.8.0",
            "selected_type": "Original",
            "start_date": "",
            "end_date": "",
            "line": "",
            "page": page,
            "column": column_name,
            "limit": limit,
            "total_pages": total_pages,
            "total_rows": total_rows,
        }
    )
@router.get("/search-one-reading", response_class=HTMLResponse)
async def search_energy_load_profile(
    request: Request,
    meter_number: str = "", 
    obis_code: str = "1.8.0",
    type: str = "Original",              
    start_date: str = None,
    end_date: str = None,
    line: str= "",  
    page: int = 1,
    limit: int = 100,
    user: dict = Depends(require_permission("Data analysis")) 
):  
  
    print(type)
    mapping = obis_to_column.get(obis_code) 
    if not mapping:
        raise ValueError(f"Unknown OBIS code: {obis_code}")
    
    table_name, column_name = mapping
    
     
    if type == "Calculated":
        if table_name == "energy_profile_readings":
            table_name = "energy_profile_readings_calculated" 
        elif table_name == "instantaneous_profile_readings":
            table_name = "instantaneous_profile_readings_calculated" 
    elif type == "Original":
        table_name == "energy_profile_readings"
        table_name == "instantaneous_profile_readings"
    print(table_name)

    base_query = f"FROM {table_name} WHERE 1 = 1"
    filter_params = []

    meter_numbers_line = []
    if line:
        meter_numbers_line = get_meters_by_line(line)
        if not meter_numbers_line:
            return template_response(
                request,
                "data_read.html",
                {
                    "request": request, 
                    "readings": readings, 
                    "meter_number": meter_number, 
                    "selected_obis_code": obis_code, 
                    "selected_type": type,   
                    "start_date": start_date,  
                    "end_date": end_date, 
                    "column" : column_name,
                    "page": page,
                    "total_pages": total_pages,
                    "limit": limit,
                    "total_rows": total_rows,
                }
            )

    if meter_numbers_line:
        placeholders = ",".join("?" for _ in meter_numbers_line)
        base_query += f" AND meter_number IN ({placeholders})"
        filter_params.extend(meter_numbers_line)
    elif meter_number:
        print(meter_number) 
        base_query += " AND meter_number LIKE ?" 
        filter_params.append(f"%{meter_number}%")     

    if start_date and end_date:
        base_query += " AND timestamp BETWEEN ? AND ?"
        filter_params.extend([start_date, end_date])

    count_query = f"SELECT COUNT(*) {base_query}"
    conn = get_db_connection()
    total_rows = conn.execute(count_query, filter_params).fetchone()[0]

    offset = max(page - 1, 0) * limit
    data_query = f"SELECT meter_number, timestamp, {column_name} {base_query} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    readings = conn.execute(data_query, (*filter_params, limit, offset)).fetchall()
    conn.close()

    total_pages = (total_rows + limit - 1) // limit if limit else 1

    return template_response(
        request,
        "data_read.html",
        {
            "request": request, 
            "readings": readings, 
            "meter_number": meter_number, 
            "selected_obis_code": obis_code, 
            "selected_type": type,   
            "start_date": start_date,  
            "end_date": end_date, 
            "column" : column_name,
            "page": page,
            "total_pages": total_pages,
            "limit": limit,
            "total_rows": total_rows,
        }
    ) 


