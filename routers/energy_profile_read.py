import sqlite3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/energy-profile-read",response_class=HTMLResponse) 
async def profile_read(request: Request, message: str=None): 
    conn = get_db_connection()   
    readings = conn.execute("SELECT *FROM energy_profile_readings").fetchall()
    print(readings)     
    conn.close()
    return templates.TemplateResponse("energy_profile_read.html", {"request": request, "readings":readings,"message":message})   

@router.get("/search-energy-profile", response_class=HTMLResponse)
async def search_energy_load_profile(
    request: Request,
    meter_number: str = "",
    type: str = "Original",  
    start_date: str = None,
    end_date: str = None, 
):
    table_name = "energy_profile_readings" 
    print(meter_number) 
    print(type)  
    print("Start Date:", start_date)  # Debug: Check if values are received
    print("End Date:", end_date)
    if type == "Calculated":  
         table_name = "energy_profile_readings_calculated" 


    query = f"""
    SELECT * FROM  {table_name} 
    WHERE 1=1
    """
    params = []
    
    # Filter by meter number (LIKE search)
    if meter_number:
        query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    # Filter by date range (if both dates provided)
    if start_date and end_date:
        query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    # Execute the query
    conn = get_db_connection()
    readings = conn.execute(query, params).fetchall()
    conn.close()
    
    return templates.TemplateResponse(
        "energy_profile_read.html",
        {
            "request": request,
            "readings": readings,
            "meter_number": meter_number,
            "selected_type": type, 
            "start_date": start_date,
            "end_date": end_date,
        }
    )
