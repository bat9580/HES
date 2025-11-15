# This file is kept for backward compatibility
# New API endpoints are in meters_api.py, readings_api.py, dcu_api.py, and system_api.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from services.database import get_db_connection

router = APIRouter(prefix="/api", tags=["Legacy"])


@router.get("/meter-installation")
async def get_installed_meters_api(): 
    """Legacy endpoint - use /api/meters/installed instead"""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM installed_meters").fetchall()
    conn.close()

    meters = [dict(row) for row in rows]

    return JSONResponse(content={"status": "success", "data": meters}) 