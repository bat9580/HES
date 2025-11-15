from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from services.database import get_db_connection

router = APIRouter(prefix="/api", tags=["DCU"])


# Pydantic models
class DCUCreateRequest(BaseModel):
    dcu_number: str
    com_address: str
    password: str
    remarks: Optional[str] = None
    status: Optional[str] = "Archived"
    ip_address: Optional[str] = None


class DCUUpdateRequest(BaseModel):
    com_address: Optional[str] = None
    password: Optional[str] = None
    remarks: Optional[str] = None
    status: Optional[str] = None
    ip_address: Optional[str] = None


# Registered DCUs Endpoints
@router.get("/dcus/registered")
async def get_registered_dcus(
    dcu_number: Optional[str] = Query(None, description="Filter by DCU number (partial match)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get list of registered DCUs"""
    conn = get_db_connection()
    
    query = "SELECT * FROM registered_dcus WHERE 1=1"
    params = []
    
    if dcu_number:
        query += " AND dcu_number LIKE ?"
        params.append(f"%{dcu_number}%")
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    # Get total count
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    # Get paginated results
    query += " ORDER BY dcu_number LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    dcus = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": dcus
    }


@router.get("/dcus/registered/{dcu_number}")
async def get_registered_dcu(dcu_number: str):
    """Get details of a specific registered DCU"""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM registered_dcus WHERE dcu_number = ?",
        (dcu_number,)
    ).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="DCU not found")
    
    return {
        "status": "success",
        "data": dict(row)
    }


@router.post("/dcus/registered")
async def create_registered_dcu(dcu: DCUCreateRequest):
    """Register a new DCU"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO registered_dcus 
            (dcu_number, com_address, password, remarks, status, ip_address)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            dcu.dcu_number, dcu.com_address, dcu.password,
            dcu.remarks, dcu.status, dcu.ip_address
        ))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": "DCU registered successfully",
            "dcu_number": dcu.dcu_number
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error registering DCU: {str(e)}")


@router.put("/dcus/registered/{dcu_number}")
async def update_registered_dcu(dcu_number: str, dcu_update: DCUUpdateRequest):
    """Update a registered DCU"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if DCU exists
    existing = conn.execute(
        "SELECT 1 FROM registered_dcus WHERE dcu_number = ?",
        (dcu_number,)
    ).fetchone()
    
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="DCU not found")
    
    # Build dynamic update query
    updates = []
    params = []
    
    for field, value in dcu_update.model_dump(exclude_unset=True).items():
        if value is not None:
            updates.append(f"{field} = ?")
            params.append(value)
    
    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")
    
    params.append(dcu_number)
    query = f"UPDATE registered_dcus SET {', '.join(updates)} WHERE dcu_number = ?"
    
    try:
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": "DCU updated successfully",
            "dcu_number": dcu_number
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error updating DCU: {str(e)}")


@router.delete("/dcus/registered/{dcu_number}")
async def delete_registered_dcu(dcu_number: str):
    """Delete a registered DCU"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if DCU exists
    existing = conn.execute(
        "SELECT 1 FROM registered_dcus WHERE dcu_number = ?",
        (dcu_number,)
    ).fetchone()
    
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="DCU not found")
    
    try:
        cursor.execute("DELETE FROM registered_dcus WHERE dcu_number = ?", (dcu_number,))
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": "DCU deleted successfully",
            "dcu_number": dcu_number
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error deleting DCU: {str(e)}")


# Unregistered DCUs Endpoints
@router.get("/dcus/unregistered")
async def get_unregistered_dcus(
    dcu_number: Optional[str] = Query(None),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get list of unregistered DCUs"""
    conn = get_db_connection()
    
    query = "SELECT * FROM unregistered_dcu WHERE 1=1"
    params = []
    
    if dcu_number:
        query += " AND dcu_number LIKE ?"
        params.append(f"%{dcu_number}%")
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY last_connection DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    dcus = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": dcus
    }


@router.get("/dcus/{dcu_number}/meters")
async def get_dcu_meters(dcu_number: str):
    """Get all meters associated with a DCU"""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM installed_meters WHERE DCU_number = ?",
        (dcu_number,)
    ).fetchall()
    conn.close()
    
    meters = [dict(row) for row in rows]
    
    return {
        "status": "success",
        "dcu_number": dcu_number,
        "meter_count": len(meters),
        "data": meters
    }

