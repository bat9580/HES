# routers/dashboard.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from services.state import connected_clients 

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def home():
    return RedirectResponse(url="/Dashboard")  

@router.get("/Dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, message: str = None):
    message = request.query_params.get("message")
    conn = get_db_connection()
    installed_meters = conn.execute("SELECT * FROM installed_meters").fetchall()
    total_installations_count = conn.execute("SELECT COUNT(*) FROM installed_meters").fetchone()[0] 
    conn.close()
    return templates.TemplateResponse(
        "dashboard.html", 
        {
            "request": request,
            "message": message,
            "registered_meters": installed_meters, 
            "total_installations": total_installations_count,  
            "total_online_meter": len(connected_clients),
            "online_rate":  len(connected_clients)/total_installations_count * 100
        }
    )


@router.get("/active-power-last6h", response_class=HTMLResponse) 
async def getActivePowerdata(request: Request,
                    line: str = "", 
                    start: str = "", 
                    end: str = ""  
                    ):
    column_name = "total_active_power"  
    table_name = "regular_task_readings"  
    
    query = f"""
        SELECT meter_number, timestamp, {column_name}  
        FROM {table_name} 
        WHERE 1 = 1
    """
    params = [] 
    meters = get_meter_by_line(line) 
    meter_data = {}
    all_timestamps_sets = []  

    for meter in meters:  
        if meter:  
            query += " AND meter_number LIKE ?"
            params.append(f"%{meter}%")  
        if start and end:
            query += " AND timestamp BETWEEN ? AND ?"
            params.extend([start, end]) 
        
        conn = get_db_connection()
        readings = conn.execute(query, params).fetchall() 
        conn.close()
        readings_dict = {round_to_minute(datetime.fromisoformat(r['timestamp'])): r[f'{column_name}'] for r in readings} 
 
        meter_data[meter] = readings_dict 
        all_timestamps_sets.append(set(readings_dict.keys())) 

    # Step 3: Find common timestamps
    common_timestamps = set.intersection(*all_timestamps_sets) 


    total_load = []
    for ts in sorted(common_timestamps):
        total_value = sum(meter_data[m][ts] for m in meters) 
        total_load.append({
            "timestamp": ts.isoformat(),
            "value": total_value
        })
    return JSONResponse(total_load) 




 
@router.get("/hourly-consumption-last24h", response_class=HTMLResponse) 
async def getConsumptionData24(request: Request,
                    line: str = "", 
                    start: str = "", 
                    end: str = ""  
                    ):
    column_name = "import_total_active_energy"  
    table_name = "energy_profile_readings_calculated"  
    
    query = f"""
        SELECT meter_number, timestamp, {column_name}  
        FROM {table_name} 
        WHERE 1 = 1
    """
    params = [] 
    meters = get_meter_by_line(line) 
    meter_data = {}
    all_timestamps_sets = [] 

    for meter in meters:  
        if meter:  
            query += " AND meter_number LIKE ?"
            params.append(f"%{meter}%")  
        if start and end:
            query += " AND timestamp BETWEEN ? AND ?"
            params.extend([start, end]) 
        
        conn = get_db_connection()
        readings = conn.execute(query, params).fetchall() 
        conn.close()
        readings_dict = {round_to_hour(datetime.fromisoformat(r['timestamp'])): r[f'{column_name}'] for r in readings} 
 
        meter_data[meter] = readings_dict 
        all_timestamps_sets.append(set(readings_dict.keys())) 

    # Step 3: Find common timestamps
    common_timestamps = set.intersection(*all_timestamps_sets) 
    sorted_hours = sorted(common_timestamps) 
    meter_hourly_values = {} 
    for meter in meters:
        readings = meter_data[meter]
        # Filter readings only for common timestamps
        filtered = {ts: readings[ts] for ts in sorted_hours if ts in readings}
        # Sorted list of (ts, value)
        meter_hourly_values[meter] = sorted(filtered.items())  



    hourly_consumptions = []  
    for i in range(1, len(sorted_hours)):
        ts_prev = sorted_hours[i - 1]
        ts_curr = sorted_hours[i]

        total_diff = 0
        # Sum differences across all meters
        for meter in meters:
            prev_value = dict(meter_hourly_values[meter]).get(ts_prev)
            curr_value = dict(meter_hourly_values[meter]).get(ts_curr)

            # Ensure both readings exist
            if prev_value is not None and curr_value is not None:
                diff = curr_value - prev_value
                # You might want to ignore negative diffs or treat as zero if your meter resets
                total_diff += max(diff, 0)

        hourly_consumptions.append({
            "timestamp": ts_curr.isoformat(),
            "value": total_diff
        })
    return JSONResponse(hourly_consumptions) 


@router.get("/daily-consumption-last30d", response_class=HTMLResponse)
async def getConsumptionData30(
    request: Request,
    line: str = "", 
    start: str = "", 
    end: str = ""
):
    column_name = "import_total_active_energy"  
    table_name = "energy_profile_readings_calculated"   
    print(start) 
    print(end) 
    # If no date range is provided, default to last 30 days
    if not start or not end:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=30)
        start = start_dt.strftime("%Y-%m-%d 00:00:00")
        end = end_dt.strftime("%Y-%m-%d 23:59:59")
    
    query = f"""
        SELECT meter_number, timestamp, {column_name}  
        FROM {table_name} 
        WHERE 1 = 1
    """
    params = [] 
    meters = get_meter_by_line(line) 
    meter_data = {}
    all_timestamps_sets = [] 

    for meter in meters:  
        if meter:  
            query += " AND meter_number LIKE ?"
            params.append(f"%{meter}%")  
        if start and end:
            query += " AND timestamp BETWEEN ? AND ?"
            params.extend([start, end]) 
        
        conn = get_db_connection()
        readings = conn.execute(query, params).fetchall() 
        conn.close()

        # Round timestamps to **day**
        readings_dict = {datetime.fromisoformat(r['timestamp']).replace(hour=0, minute=0, second=0, microsecond=0): 
                         r[f'{column_name}'] for r in readings} 
        print(readings_dict) 
 
        meter_data[meter] = readings_dict 
        all_timestamps_sets.append(set(readings_dict.keys())) 

    # Find common days
    common_days = set.intersection(*all_timestamps_sets) 
    sorted_days = sorted(common_days) 

    meter_daily_values = {} 
    for meter in meters:
        readings = meter_data[meter]
        filtered = {ts: readings[ts] for ts in sorted_days if ts in readings}
        meter_daily_values[meter] = sorted(filtered.items())  

    # Calculate daily consumption
    daily_consumptions = []  
    for i in range(1, len(sorted_days)):
        day_prev = sorted_days[i - 1]
        day_curr = sorted_days[i]

        total_diff = 0
        for meter in meters:
            prev_value = dict(meter_daily_values[meter]).get(day_prev)
            curr_value = dict(meter_daily_values[meter]).get(day_curr)
            if prev_value is not None and curr_value is not None:
                diff = curr_value - prev_value
                total_diff += max(diff, 0)

        daily_consumptions.append({
            "timestamp": day_curr.strftime("%Y-%m-%d"),
            "value": total_diff
        })

    return JSONResponse(daily_consumptions)




def get_meter_by_line(
    line: str = "" 
    ):
    query = "SELECT meter_number FROM installed_meters WHERE 1=1"  
    params = []
    
    if line is not None:   
        query+= " AND line LIKE ?"   
        params.append(f"%{line}%")  
    conn = get_db_connection()
    meters = [row[0] for row in conn.execute(query, params).fetchall()] 
    print(meters) 
    conn.close() 
    return meters


def round_to_minute(ts):  # oirhon minut luu shiljuuleh 
    """Round timestamp to the nearest minute."""
    return ts.replace(second=0, microsecond=0)  
def round_to_hour(dt):    # oirhon tsag ruu horvuuleh  
    return dt.replace(minute=0, second=0, microsecond=0)  