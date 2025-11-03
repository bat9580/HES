from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from services.database import get_db_connection
from utils.utility_functions import require_permission
router = APIRouter()


@router.get("/api/meter-installation")
async def get_installed_meters_api(): 
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM installed_meters").fetchall()
    conn.close()

    # Convert SQLite Row objects (if using sqlite3) to dicts
    meters = [dict(row) for row in rows]

    return JSONResponse(content={"status": "success", "data": meters}) 