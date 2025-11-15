from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from services.database import get_db_connection
from services.state import connected_clients

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"]) 


def _round_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def _round_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


@router.get("/summary")
async def get_dashboard_summary():
    """High-level dashboard summary counts."""
    conn = get_db_connection()
    installed_count = conn.execute("SELECT COUNT(*) FROM installed_meters").fetchone()[0]
    registered_meter_count = conn.execute("SELECT COUNT(*) FROM registered_meters").fetchone()[0]

    # Meter type counts for selected types
    type_rows = conn.execute(
        """
        SELECT type, COUNT(*) as count 
        FROM installed_meters
        WHERE type IN ('DDSY283SR', 'DTSD546', 'DTSD545S')
        GROUP BY type
        """
    ).fetchall()
    conn.close()

    type_counts: Dict[str, int] = {row["type"]: row["count"] for row in type_rows}
    for t in ["DDSY283SR", "DTSD546", "DTSD545S"]:
        type_counts.setdefault(t, 0)

    return {
        "status": "success",
        "data": {
            "meters": {
                "installed": installed_count,
                "registered": registered_meter_count,
                "connected": len(connected_clients),
            },
            "types": type_counts,
        },
    }


@router.get("/active-power")
async def get_active_power(
    line: str = Query("", description="Line identifier to filter meters"),
    start: Optional[str] = Query(None, description="Start datetime YYYY-MM-DD HH:MM:SS"),
    end: Optional[str] = Query(None, description="End datetime YYYY-MM-DD HH:MM:SS"),
):
    print(line) 
    print(start) 
    print(end) 

    """Aggregate total_active_power (regular_task_readings) over common timestamps."""
    column_name = "total_active_power"
    table_name = "regular_task_readings"

    # Resolve meters by line (if provided)
    meters = _get_meter_by_line(line)
    series_by_meter: Dict[str, Dict[datetime, float]] = {}
    all_ts_sets: List[set] = []

    for meter in meters:
        query = f"SELECT meter_number, timestamp, {column_name} FROM {table_name} WHERE 1=1"
        params: List[Any] = []
        if meter:
            query += " AND meter_number LIKE ?"
            params.append(f"%{meter}%")
        if start and end:
            query += " AND timestamp BETWEEN ? AND ?"
            params.extend([start, end])

        conn = get_db_connection()
        rows = conn.execute(query, params).fetchall()
        conn.close()
        readings = {_round_to_minute(datetime.fromisoformat(r["timestamp"])): r[column_name] for r in rows}
        series_by_meter[meter] = readings
        all_ts_sets.append(set(readings.keys()))

    if not all_ts_sets:
        return []

    common_ts = set.intersection(*all_ts_sets) if all_ts_sets else set()
    total_load = []
    for ts in sorted(common_ts):
        total_value = sum(series_by_meter[m].get(ts, 0) for m in meters)
        total_load.append({"timestamp": ts.isoformat(), "value": total_value})
    print(total_load) 

    return JSONResponse(total_load)


@router.get("/hourly-consumption")
async def get_hourly_consumption(
    line: str = Query("", description="Line identifier to filter meters"),
    start: Optional[str] = Query(None, description="Start datetime YYYY-MM-DD HH:MM:SS"),
    end: Optional[str] = Query(None, description="End datetime YYYY-MM-DD HH:MM:SS"),
):
    """Compute hourly energy consumption deltas across meters (calculated energy profile)."""
    column_name = "import_total_active_energy"
    table_name = "energy_profile_readings_calculated"

    meters = _get_meter_by_line(line)

    series_by_meter: Dict[str, Dict[datetime, float]] = {}
    all_ts_sets: List[set] = []

    for meter in meters:
        query = f"SELECT meter_number, timestamp, {column_name} FROM {table_name} WHERE 1=1"
        params: List[Any] = []
        if meter:
            query += " AND meter_number LIKE ?"
            params.append(f"%{meter}%")
        if start and end:
            query += " AND timestamp BETWEEN ? AND ?"
            params.extend([start, end])

        conn = get_db_connection()
        rows = conn.execute(query, params).fetchall()
        conn.close()
        readings = {_round_to_hour(datetime.fromisoformat(r["timestamp"])): r[column_name] for r in rows}
        series_by_meter[meter] = readings
        all_ts_sets.append(set(readings.keys()))

    if not all_ts_sets:
        return []

    common_ts = sorted(set.intersection(*all_ts_sets)) if all_ts_sets else []

    meter_hourly_values: Dict[str, List[tuple]] = {}
    for meter in meters:
        readings = series_by_meter[meter]
        filtered = {ts: readings[ts] for ts in common_ts if ts in readings}
        meter_hourly_values[meter] = sorted(filtered.items())

    hourly = []
    for i in range(1, len(common_ts)):
        ts_prev = common_ts[i - 1]
        ts_curr = common_ts[i]
        total_diff = 0.0
        for meter in meters:
            m_series = dict(meter_hourly_values[meter])
            prev_val = m_series.get(ts_prev)
            curr_val = m_series.get(ts_curr)
            if prev_val is not None and curr_val is not None:
                diff = curr_val - prev_val
                total_diff += max(diff, 0)
        hourly.append({"timestamp": ts_curr.isoformat(), "value": total_diff})

    return JSONResponse(hourly)


@router.get("/daily-consumption")
async def get_daily_consumption(
    line: str = Query("", description="Line identifier to filter meters"),
    start: Optional[str] = Query(None, description="Start datetime YYYY-MM-DD HH:MM:SS"),
    end: Optional[str] = Query(None, description="End datetime YYYY-MM-DD HH:MM:SS"),
):
    """Compute daily energy consumption deltas across meters (calculated energy profile)."""
    column_name = "import_total_active_energy"
    table_name = "energy_profile_readings_calculated"

    # Default to last 30 days if no date range
    if not start or not end:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=30)
        start = start_dt.strftime("%Y-%m-%d 00:00:00")
        end = end_dt.strftime("%Y-%m-%d 23:59:59")

    meters = _get_meter_by_line(line)

    series_by_meter: Dict[str, Dict[datetime, float]] = {}
    all_ts_sets: List[set] = []

    for meter in meters:
        query = f"SELECT meter_number, timestamp, {column_name} FROM {table_name} WHERE 1=1"
        params: List[Any] = []
        if meter:
            query += " AND meter_number LIKE ?"
            params.append(f"%{meter}%")
        if start and end:
            query += " AND timestamp BETWEEN ? AND ?"
            params.extend([start, end])

        conn = get_db_connection()
        rows = conn.execute(query, params).fetchall()
        conn.close()

        readings = {datetime.fromisoformat(r["timestamp"]).replace(hour=0, minute=0, second=0, microsecond=0): r[column_name] for r in rows}
        series_by_meter[meter] = readings
        all_ts_sets.append(set(readings.keys()))

    if not all_ts_sets:
        return []

    common_days = sorted(set.intersection(*all_ts_sets)) if all_ts_sets else []

    meter_daily_values: Dict[str, List[tuple]] = {}
    for meter in meters:
        readings = series_by_meter[meter]
        filtered = {ts: readings[ts] for ts in common_days if ts in readings}
        meter_daily_values[meter] = sorted(filtered.items())

    daily = []
    for i in range(1, len(common_days)):
        ts_prev = common_days[i - 1]
        ts_curr = common_days[i]
        total_diff = 0.0
        for meter in meters:
            m_series = dict(meter_daily_values[meter])
            prev_val = m_series.get(ts_prev)
            curr_val = m_series.get(ts_curr)
            if prev_val is not None and curr_val is not None:
                diff = curr_val - prev_val
                total_diff += max(diff, 0)
        daily.append({"timestamp": ts_curr.isoformat(), "value": total_diff})

    return JSONResponse(daily)


def _get_meter_by_line(line: str) -> List[str]:
    """Return list of meter numbers for a given line. If no line provided, return distinct meter numbers."""
    query = "SELECT meter_number FROM installed_meters WHERE 1=1"
    params: List[Any] = []
    if line:
        query += " AND line LIKE ?"
        params.append(f"%{line}%")

    conn = get_db_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [row[0] for row in rows]
