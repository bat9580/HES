import sqlite3
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.parameters import obis_to_column
from utils.utility_functions import get_meters_by_line, require_permission, template_response 
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/data-read",response_class=HTMLResponse) 
async def Unregistered_device(request: Request, message: str=None,user: dict = Depends(require_permission("Data analysis"))):  
    conn = get_db_connection()   
    unregistered = conn.execute("SELECT *FROM unregistered_dcu").fetchall() 
    print(unregistered)    
    conn.close()
    return template_response(request, "data_read.html", {"request": request, "Unregistered":unregistered,"message":message})
@router.get("/search-one-reading", response_class=HTMLResponse)
async def search_energy_load_profile(
    request: Request,
    meter_number: str = "", 
    obis_code: str = "1.8.0",
    type: str = "Original",              
    start_date: str = None,
    end_date: str = None,
    line: str= "",  
    user: dict = Depends(require_permission("Data analysis")) 
):  
  
    print(type) 
    mapping = obis_to_column.get(obis_code) 
    if not mapping:
        raise ValueError(f"Unknown OBIS code: {obis_code}")
    
    table_name, column_name = mapping
    
    meter_numbers_line = get_meters_by_line(line)  
    if type == "Calculated":
        if table_name == "energy_profile_readings":
            table_name = "energy_profile_readings_calculated" 
        elif table_name == "instantaneous_profile_readings":
            table_name = "instantaneous_profile_readings_calculated" 

    query = f"""
        SELECT meter_number, timestamp, {column_name} 
        FROM {table_name}
        WHERE 1 = 1
    """
    params = []  
 
    if meter_numbers_line:  
        placeholders = ",".join("?" for _ in meter_numbers_line)
        query += f" AND meter_number IN ({placeholders})"
        params.extend(meter_numbers_line)
    else: 
        if meter_number: 
            print(meter_number) 
            query += " AND meter_number LIKE ?" 
            params.append(f"%{meter_number}%")     
    if start_date and end_date:
        query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    

    

    conn = get_db_connection()
    readings = conn.execute(query, params).fetchall()
    conn.close()
    print(readings) 
    



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
            "column" : column_name 
        }
    ) 


