from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime, timedelta
from services.database import get_db_connection
from utils.utility_functions import get_meters_by_line

router = APIRouter(prefix="/api", tags=["Readings"])


# Energy Profile Readings
@router.get("/readings/energy-profile")
async def get_energy_profile_readings(
    meter_number: Optional[str] = Query(None, description="Filter by meter number"),
    line: Optional[str] = Query(None, description="Filter by line"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD HH:MM:SS)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD HH:MM:SS)"),
    calculated: Optional[bool] = Query(False, description="Use calculated values"),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get energy profile readings"""
    table_name = "energy_profile_readings_calculated" if calculated else "energy_profile_readings"
    
    conn = get_db_connection()
    query = f"SELECT * FROM {table_name} WHERE 1=1"
    params = []
    
    # Filter by line or meter number
    meter_numbers_line = get_meters_by_line(line) if line else []
    if meter_numbers_line:
        placeholders = ",".join("?" for _ in meter_numbers_line)
        query += f" AND meter_number IN ({placeholders})"
        params.extend(meter_numbers_line)
    elif meter_number:
        query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    
    # Date filter
    if start_date and end_date:
        query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    # Get total count
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    # Pagination
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    readings = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "table": table_name,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": readings
    }


@router.get("/readings/energy-profile/{meter_number}")
async def get_energy_profile_by_meter(
    meter_number: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    calculated: Optional[bool] = Query(False),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get energy profile readings for a specific meter"""
    table_name = "energy_profile_readings_calculated" if calculated else "energy_profile_readings"
    
    conn = get_db_connection()
    query = f"SELECT * FROM {table_name} WHERE meter_number = ?"
    params = [meter_number]
    
    if start_date and end_date:
        query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    readings = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "meter_number": meter_number,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": readings
    }


# Instantaneous Profile Readings
@router.get("/readings/instantaneous")
async def get_instantaneous_readings(
    meter_number: Optional[str] = Query(None),
    line: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    calculated: Optional[bool] = Query(False),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get instantaneous profile readings"""
    table_name = "instantaneous_profile_readings_calculated" if calculated else "instantaneous_profile_readings"
    
    conn = get_db_connection()
    query = f"SELECT * FROM {table_name} WHERE 1=1"
    params = []
    
    # Filter by line or meter number
    meter_numbers_line = get_meters_by_line(line) if line else []
    if meter_numbers_line:
        placeholders = ",".join("?" for _ in meter_numbers_line)
        query += f" AND meter_number IN ({placeholders})"
        params.extend(meter_numbers_line)
    elif meter_number:
        query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    
    if start_date and end_date:
        query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    readings = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "table": table_name,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": readings
    }


@router.get("/readings/instantaneous/{meter_number}")
async def get_instantaneous_by_meter(
    meter_number: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    calculated: Optional[bool] = Query(False),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get instantaneous profile readings for a specific meter"""
    table_name = "instantaneous_profile_readings_calculated" if calculated else "instantaneous_profile_readings"
    
    conn = get_db_connection()
    query = f"SELECT * FROM {table_name} WHERE meter_number = ?"
    params = [meter_number]
    
    if start_date and end_date:
        query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    readings = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "meter_number": meter_number,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": readings
    }


# Regular Task Readings
@router.get("/readings/regular")
async def get_regular_readings(
    meter_number: Optional[str] = Query(None),
    line: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get regular task readings"""
    conn = get_db_connection()
    query = "SELECT * FROM regular_task_readings WHERE 1=1"
    params = []
    
    # Filter by line or meter number
    meter_numbers_line = get_meters_by_line(line) if line else []
    if meter_numbers_line:
        placeholders = ",".join("?" for _ in meter_numbers_line)
        query += f" AND meter_number IN ({placeholders})"
        params.extend(meter_numbers_line)
    elif meter_number:
        query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    
    if start_date and end_date:
        query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    readings = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": readings
    }


@router.get("/readings/regular/{meter_number}")
async def get_regular_by_meter(
    meter_number: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get regular task readings for a specific meter"""
    conn = get_db_connection()
    query = "SELECT * FROM regular_task_readings WHERE meter_number = ?"
    params = [meter_number]
    
    if start_date and end_date:
        query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    readings = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "meter_number": meter_number,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": readings
    }


# Latest Readings
@router.get("/readings/{meter_number}/latest")
async def get_latest_reading(meter_number: str):
    """Get the latest reading from any table for a meter"""
    conn = get_db_connection()
    
    # Try each table and get the most recent
    tables = [
        "regular_task_readings",
        "instantaneous_profile_readings",
        "energy_profile_readings"
    ]
    
    latest_reading = None
    latest_timestamp = None
    latest_table = None
    
    for table in tables:
        row = conn.execute(
            f"SELECT *, '{table}' as source_table FROM {table} WHERE meter_number = ? ORDER BY timestamp DESC LIMIT 1",
            (meter_number,)
        ).fetchone()
        
        if row:
            timestamp = datetime.fromisoformat(row['timestamp'])
            if latest_timestamp is None or timestamp > latest_timestamp:
                latest_timestamp = timestamp
                latest_reading = dict(row)
                latest_table = table
    
    conn.close()
    
    if not latest_reading:
        raise HTTPException(status_code=404, detail=f"No readings found for meter {meter_number}")
    
    return {
        "status": "success",
        "meter_number": meter_number,
        "source_table": latest_table,
        "data": latest_reading
    }


# Reading Statistics
@router.get("/readings/{meter_number}/statistics")
async def get_meter_statistics(
    meter_number: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    calculated: Optional[bool] = Query(False)
):
    """Get statistics for a meter"""
    conn = get_db_connection()
    
    # Default to last 24 hours if no date range
    if not start_date or not end_date:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(hours=24)
        start_date = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_date = end_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    stats = {}
    
    # Energy profile stats
    energy_table = "energy_profile_readings_calculated" if calculated else "energy_profile_readings"
    energy_query = f"""
        SELECT 
            COUNT(*) as count,
            MIN(timestamp) as first_reading,
            MAX(timestamp) as last_reading,
            AVG(import_total_active_energy) as avg_import_active_energy
        FROM {energy_table}
        WHERE meter_number = ? AND timestamp BETWEEN ? AND ?
    """
    energy_stats = conn.execute(energy_query, (meter_number, start_date, end_date)).fetchone()
    stats["energy_profile"] = dict(energy_stats) if energy_stats[0] > 0 else None
    
    # Instantaneous stats
    inst_table = "instantaneous_profile_readings_calculated" if calculated else "instantaneous_profile_readings"
    inst_query = f"""
        SELECT 
            COUNT(*) as count,
            MIN(timestamp) as first_reading,
            MAX(timestamp) as last_reading,
            AVG(total_active_power) as avg_active_power,
            AVG(voltage_A) as avg_voltage_a,
            AVG(voltage_B) as avg_voltage_b,
            AVG(voltage_C) as avg_voltage_c
        FROM {inst_table}
        WHERE meter_number = ? AND timestamp BETWEEN ? AND ?
    """
    inst_stats = conn.execute(inst_query, (meter_number, start_date, end_date)).fetchone()
    stats["instantaneous"] = dict(inst_stats) if inst_stats[0] > 0 else None
    
    # Regular task stats
    regular_query = """
        SELECT 
            COUNT(*) as count,
            MIN(timestamp) as first_reading,
            MAX(timestamp) as last_reading,
            AVG(total_active_power) as avg_active_power
        FROM regular_task_readings
        WHERE meter_number = ? AND timestamp BETWEEN ? AND ?
    """
    regular_stats = conn.execute(regular_query, (meter_number, start_date, end_date)).fetchone()
    stats["regular"] = dict(regular_stats) if regular_stats[0] > 0 else None
    
    conn.close()
    
    return {
        "status": "success",
        "meter_number": meter_number,
        "date_range": {
            "start": start_date,
            "end": end_date
        },
        "statistics": stats
    }

