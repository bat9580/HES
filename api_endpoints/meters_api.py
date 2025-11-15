from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from services.database import get_db_connection
from services.state import connected_clients

router = APIRouter(prefix="/api", tags=["Meters"])


# Pydantic models for request/response
class MeterInstallRequest(BaseModel):
    meter_number: str
    com_address: str
    password: str
    device_type: str
    type: str
    remarks: Optional[str] = None
    DCU_number: Optional[str] = None
    Zone: Optional[str] = None
    station: Optional[str] = None
    POWER_grid: Optional[str] = None
    task: Optional[str] = None
    line: Optional[str] = None
    CT_ratio: Optional[int] = 1
    VT_ratio: Optional[int] = 1


class MeterUpdateRequest(BaseModel):
    com_address: Optional[str] = None
    password: Optional[str] = None
    device_type: Optional[str] = None
    type: Optional[str] = None
    remarks: Optional[str] = None
    DCU_number: Optional[str] = None
    Zone: Optional[str] = None
    station: Optional[str] = None
    POWER_grid: Optional[str] = None
    task: Optional[str] = None
    line: Optional[str] = None
    CT_ratio: Optional[int] = None
    VT_ratio: Optional[int] = None
    status: Optional[str] = None


# Installed Meters Endpoints
@router.get("/meters/installed")
async def get_installed_meters(
    meter_number: Optional[str] = Query(None, description="Filter by meter number (partial match)"),
    line: Optional[str] = Query(None, description="Filter by line"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get list of installed meters with optional filters"""
    conn = get_db_connection()
    
    query = "SELECT * FROM installed_meters WHERE 1=1"
    params = []
    
    if meter_number:
        query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    
    if line:
        query += " AND line = ?"
        params.append(line)
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    # Get total count
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    # Get paginated results
    query += " ORDER BY meter_number LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    meters = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": meters
    }


@router.get("/meters/installed/{meter_number}")
async def get_installed_meter(meter_number: str):
    """Get details of a specific installed meter"""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM installed_meters WHERE meter_number = ?",
        (meter_number,)
    ).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Meter not found")
    
    return {
        "status": "success",
        "data": dict(row)
    }


@router.post("/meters/installed")
async def create_installed_meter(meter: MeterInstallRequest):
    """Install a new meter"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO installed_meters 
            (meter_number, com_address, password, device_type, type, status, remarks,
             DCU_number, Zone, station, POWER_grid, task, line, CT_ratio, VT_ratio)
            VALUES (?, ?, ?, ?, ?, 'installed', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meter.meter_number, meter.com_address, meter.password,
            meter.device_type, meter.type, meter.remarks,
            meter.DCU_number, meter.Zone, meter.station,
            meter.POWER_grid, meter.task, meter.line,
            meter.CT_ratio, meter.VT_ratio
        ))
        
        # Update registered_meters status if exists
        cursor.execute("""
            UPDATE registered_meters
            SET status = 'installed'
            WHERE meter_number = ?
        """, (meter.meter_number,))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": "Meter installed successfully",
            "meter_number": meter.meter_number
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error installing meter: {str(e)}")


@router.put("/meters/installed/{meter_number}")
async def update_installed_meter(meter_number: str, meter_update: MeterUpdateRequest):
    """Update an installed meter"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if meter exists
    existing = conn.execute(
        "SELECT 1 FROM installed_meters WHERE meter_number = ?",
        (meter_number,)
    ).fetchone()
    
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Meter not found")
    
    # Build dynamic update query
    updates = []
    params = []
    
    for field, value in meter_update.model_dump(exclude_unset=True).items():
        if value is not None:
            updates.append(f"{field} = ?")
            params.append(value)
    
    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")
    
    params.append(meter_number)
    query = f"UPDATE installed_meters SET {', '.join(updates)} WHERE meter_number = ?"
    
    try:
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": "Meter updated successfully",
            "meter_number": meter_number
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error updating meter: {str(e)}")


@router.delete("/meters/installed/{meter_number}")
async def delete_installed_meter(meter_number: str):
    """Delete (uninstall) a meter"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if meter exists
    existing = conn.execute(
        "SELECT 1 FROM installed_meters WHERE meter_number = ?",
        (meter_number,)
    ).fetchone()
    
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Meter not found")
    
    try:
        cursor.execute("DELETE FROM installed_meters WHERE meter_number = ?", (meter_number,))
        
        # Update registered_meters status if exists
        cursor.execute("""
            UPDATE registered_meters
            SET status = 'registered'
            WHERE meter_number = ?
        """, (meter_number,))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": "Meter uninstalled successfully",
            "meter_number": meter_number
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error uninstalling meter: {str(e)}")


# Registered Meters Endpoints
@router.get("/meters/registered")
async def get_registered_meters(
    meter_number: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get list of registered meters"""
    conn = get_db_connection()
    
    query = "SELECT * FROM registered_meters WHERE 1=1"
    params = []
    
    if meter_number:
        query += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY meter_number LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    meters = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": meters
    }


# Meter Connection Status
@router.get("/meters/{meter_number}/status")
async def get_meter_status(meter_number: str):
    """Get connection status of a meter"""
    is_connected = str(meter_number) in connected_clients
    
    status_info = {
        "meter_number": meter_number,
        "connected": is_connected
    }
    
    if is_connected:
        client = connected_clients[str(meter_number)]
        status_info.update({
            "address": str(client.get('addr', '')),
            "access_time": client.get('access_time', 0)
        })
    
    # Get meter info from database
    conn = get_db_connection()
    meter_info = conn.execute(
        "SELECT * FROM installed_meters WHERE meter_number = ?",
        (meter_number,)
    ).fetchone()
    conn.close()
    
    if meter_info:
        status_info["meter_info"] = dict(meter_info)
    
    return {
        "status": "success",
        "data": status_info
    }


@router.get("/meters/connected")
async def get_connected_meters():
    """Get list of currently connected meters"""
    connected = []
    for meter_number, client_info in connected_clients.items():
        connected.append({
            "meter_number": meter_number,
            "address": str(client_info.get('addr', '')),
            "access_time": client_info.get('access_time', 0)
        })
    
    return {
        "status": "success",
        "count": len(connected),
        "data": connected
    }

