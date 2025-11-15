from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any
from services.database import get_db_connection
from services.state import connected_clients, scheduler
from datetime import datetime

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/system/status")
async def get_system_status():
    """Get overall system status and statistics"""
    conn = get_db_connection()
    
    # Get counts from database
    installed_count = conn.execute("SELECT COUNT(*) FROM installed_meters").fetchone()[0]
    registered_meter_count = conn.execute("SELECT COUNT(*) FROM registered_meters").fetchone()[0]
    registered_dcu_count = conn.execute("SELECT COUNT(*) FROM registered_dcus").fetchone()[0]
    
    # Get connection statistics
    connected_count = len(connected_clients)
    
    # Get recent reading counts
    recent_readings_query = """
        SELECT COUNT(*) FROM (
            SELECT 1 FROM regular_task_readings 
            WHERE timestamp >= datetime('now', '-24 hours')
            UNION ALL
            SELECT 1 FROM instantaneous_profile_readings 
            WHERE timestamp >= datetime('now', '-24 hours')
            UNION ALL
            SELECT 1 FROM energy_profile_readings 
            WHERE timestamp >= datetime('now', '-24 hours')
        )
    """
    recent_readings = conn.execute(recent_readings_query).fetchone()[0]
    
    # Get scheduler status
    scheduler_status = {
        "running": scheduler.running,
        "jobs_count": len(scheduler.get_jobs())
    }
    
    conn.close()
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "data": {
            "meters": {
                "installed": installed_count,
                "registered": registered_meter_count,
                "connected": connected_count
            },
            "dcus": {
                "registered": registered_dcu_count
            },
            "readings": {
                "last_24_hours": recent_readings
            },
            "scheduler": scheduler_status
        }
    }


@router.get("/system/health")
async def get_system_health():
    """Get system health check"""
    health_status = {
        "status": "healthy",
        "checks": {}
    }
    
    try:
        # Database check
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["checks"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
    
    # Scheduler check
    try:
        if scheduler.running:
            health_status["checks"]["scheduler"] = "ok"
        else:
            health_status["checks"]["scheduler"] = "not_running"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["scheduler"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
    
    health_status["timestamp"] = datetime.now().isoformat()
    
    return health_status


@router.get("/system/connections")
async def get_all_connections():
    """Get all active meter connections"""
    connections = []
    
    for meter_number, client_info in connected_clients.items():
        connections.append({
            "meter_number": meter_number,
            "address": str(client_info.get('addr', '')),
            "access_time": client_info.get('access_time', 0),
            "has_reader": client_info.get('reader') is not None,
            "has_writer": client_info.get('writer') is not None
        })
    
    return {
        "status": "success",
        "count": len(connections),
        "data": connections
    }


@router.get("/system/statistics")
async def get_system_statistics():
    """Get detailed system statistics"""
    conn = get_db_connection()
    
    stats = {}
    
    # Meter statistics
    meter_stats = conn.execute("""
        SELECT 
            status,
            COUNT(*) as count
        FROM installed_meters
        GROUP BY status
    """).fetchall()
    stats["meters_by_status"] = {row["status"]: row["count"] for row in meter_stats}
    
    # DCU statistics
    dcu_stats = conn.execute("""
        SELECT 
            status,
            COUNT(*) as count
        FROM registered_dcus
        GROUP BY status
    """).fetchall()
    stats["dcus_by_status"] = {row["status"]: row["count"] for row in dcu_stats}
    
    # Reading statistics
    reading_stats = conn.execute("""
        SELECT 
            'regular_task_readings' as table_name,
            COUNT(*) as total_readings,
            MIN(timestamp) as earliest,
            MAX(timestamp) as latest
        FROM regular_task_readings
        UNION ALL
        SELECT 
            'instantaneous_profile_readings' as table_name,
            COUNT(*) as total_readings,
            MIN(timestamp) as earliest,
            MAX(timestamp) as latest
        FROM instantaneous_profile_readings
        UNION ALL
        SELECT 
            'energy_profile_readings' as table_name,
            COUNT(*) as total_readings,
            MIN(timestamp) as earliest,
            MAX(timestamp) as latest
        FROM energy_profile_readings
    """).fetchall()
    stats["readings"] = [dict(row) for row in reading_stats]
    
    # Line statistics
    line_stats = conn.execute("""
        SELECT 
            line,
            COUNT(*) as meter_count
        FROM installed_meters
        WHERE line IS NOT NULL AND line != ''
        GROUP BY line
        ORDER BY meter_count DESC
    """).fetchall()
    stats["meters_by_line"] = {row["line"]: row["meter_count"] for row in line_stats}
    
    conn.close()
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "data": stats
    }


@router.get("/system/tasks")
async def get_scheduled_tasks():
    """Get all scheduled tasks"""
    conn = get_db_connection()
    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()
    
    # Get active scheduler jobs
    scheduler_jobs = []
    for job in scheduler.get_jobs():
        scheduler_jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
    
    return {
        "status": "success",
        "database_tasks": [dict(task) for task in tasks],
        "scheduler_jobs": scheduler_jobs
    }

