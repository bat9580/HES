from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from services.database import get_db_connection
from utils.utility_functions import get_meters_by_line, require_permission, template_response

router = APIRouter()

TABLES = {
    "Original": "energy_profile_readings",
    "Calculated": "energy_profile_readings_calculated",
}
COLUMNS = (
    ("import_total_active_energy", "Нийт импорт (1.8.0)", "кВт·ц"),
    ("import_active_energy_T1", "Импорт T1 (1.8.1)", "кВт·ц"),
    ("import_active_energy_T2", "Импорт T2 (1.8.2)", "кВт·ц"),
    ("import_active_energy_T3", "Импорт T3 (1.8.3)", "кВт·ц"),
    ("export_total_active_energy", "Нийт экспорт (2.8.0)", "кВт·ц"),
    ("export_active_energy_T1", "Экспорт T1 (2.8.1)", "кВт·ц"),
    ("export_active_energy_T2", "Экспорт T2 (2.8.2)", "кВт·ц"),
    ("export_active_energy_T3", "Экспорт T3 (2.8.3)", "кВт·ц"),
    ("import_total_reactive_energy", "Реактив Q+ (3.8.0)", "квар·ц"),
    ("import_reactive_energy_T1", "Реактив T1 (3.8.1)", "квар·ц"),
    ("import_reactive_energy_T2", "Реактив T2 (3.8.2)", "квар·ц"),
    ("import_reactive_energy_T3", "Реактив T3 (3.8.3)", "квар·ц"),
    ("export_total_reactive_energy", "Экспорт реактив (4.8.0)", "квар·ц"),
    ("export_reactive_energy_T1", "Экспорт реактив T1 (4.8.1)", "квар·ц"),
    ("export_reactive_energy_T2", "Экспорт реактив T2 (4.8.2)", "квар·ц"),
    ("export_reactive_energy_T3", "Экспорт реактив T3 (4.8.3)", "квар·ц"),
)
CHART_KEYS = (
    "import_total_active_energy",
    "import_active_energy_T1",
    "import_active_energy_T2",
    "import_active_energy_T3",
)
SELECT_COLUMNS = ", ".join(name for name, _label, _unit in COLUMNS)


def _fmt(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def _delta(latest, earliest):
    if latest is None or earliest is None:
        return "—"
    change = float(latest) - float(earliest)
    text = _fmt(change)
    if change > 0:
        return f"+{text}"
    return text


def _hours(start, end):
    if not start or not end:
        return ""
    parsed = []
    for raw in (start, end):
        stamp = None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                stamp = datetime.strptime(str(raw)[:19], fmt)
                break
            except ValueError:
                continue
        if stamp is None:
            return ""
        parsed.append(stamp)
    hours = abs((parsed[1] - parsed[0]).total_seconds()) / 3600
    return f"{hours:.1f}".rstrip("0").rstrip(".") or "0"


def _filters(meter_number, line, start_date, end_date):
    where = "WHERE 1 = 1"
    params = []
    if line:
        meter_numbers = get_meters_by_line(line)
        if not meter_numbers:
            return {"empty": True, "where": where, "params": params}
        placeholders = ",".join("?" for _ in meter_numbers)
        where += f" AND meter_number IN ({placeholders})"
        params.extend(meter_numbers)
    elif meter_number:
        where += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    if start_date and end_date:
        where += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    return {"empty": False, "where": where, "params": params}


def _chart(rows):
    numeric = []
    for row in rows:
        for key in CHART_KEYS:
            value = row[key]
            if value is not None:
                numeric.append(float(value))
    if not numeric:
        return None
    low, high = min(numeric), max(numeric)
    span = high - low
    count = len(rows)
    series = {}
    for key in CHART_KEYS:
        coords = []
        for index, row in enumerate(rows):
            value = row[key]
            if value is None:
                continue
            x = 0 if count == 1 else index * 1000 / (count - 1)
            if span == 0:
                y = 80
            else:
                y = 140 - ((float(value) - low) / span) * 120
            coords.append({"x": round(x, 2), "y": round(y, 2)})
        if coords:
            series[key] = coords
    meters = {row["meter_number"] for row in rows if row["meter_number"]}
    return {
        "series": series,
        "min": _fmt(low),
        "max": _fmt(high),
        "first": rows[0]["timestamp"] or "",
        "last": rows[-1]["timestamp"] or "",
        "meter": next(iter(meters)) if len(meters) == 1 else "",
    }


def _load(
    meter_number="",
    reading_type="Original",
    start_date="",
    end_date="",
    line="",
    page=1,
    limit=15,
    message=None,
):
    if reading_type not in TABLES:
        reading_type = "Original"
    table_name = TABLES[reading_type]
    try:
        page = max(int(page or 1), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        limit = int(limit or 15)
    except (TypeError, ValueError):
        limit = 15
    if limit not in (15, 30, 50, 100):
        limit = 15

    spec = _filters(meter_number or "", line or "", start_date or "", end_date or "")
    readings = []
    chart = None
    total_rows = 0
    distinct_meters = 0
    today_rows = 0
    min_ts = ""
    max_ts = ""
    latest_total = "—"
    latest_t1 = "—"
    latest_t2 = "—"
    delta_total = "—"
    focus = None

    if not spec["empty"]:
        conn = get_db_connection()
        today = datetime.now().strftime("%Y-%m-%d")
        stats = conn.execute(
            f"""
            SELECT COUNT(*),
                   COUNT(DISTINCT meter_number),
                   MIN(timestamp),
                   MAX(timestamp),
                   SUM(CASE WHEN timestamp LIKE ? THEN 1 ELSE 0 END)
            FROM {table_name} {spec["where"]}
            """,
            (f"{today}%", *spec["params"]),
        ).fetchone()
        total_rows = stats[0] or 0
        distinct_meters = stats[1] or 0
        min_ts = stats[2] or ""
        max_ts = stats[3] or ""
        today_rows = stats[4] or 0
        total_pages_now = (total_rows + limit - 1) // limit if total_rows else 1
        if page > total_pages_now:
            page = total_pages_now

        offset = (page - 1) * limit
        rows = conn.execute(
            f"""
            SELECT meter_number, timestamp, {SELECT_COLUMNS}
            FROM {table_name} {spec["where"]}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (*spec["params"], limit, offset),
        ).fetchall()
        chart_rows = conn.execute(
            f"""
            SELECT meter_number, timestamp, {SELECT_COLUMNS}
            FROM {table_name} {spec["where"]}
            ORDER BY timestamp ASC
            LIMIT 200
            """,
            spec["params"],
        ).fetchall()
        latest = conn.execute(
            f"""
            SELECT import_total_active_energy, import_active_energy_T1, import_active_energy_T2
            FROM {table_name} {spec["where"]}
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            spec["params"],
        ).fetchone()
        earliest = conn.execute(
            f"""
            SELECT import_total_active_energy
            FROM {table_name} {spec["where"]}
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            spec["params"],
        ).fetchone()
        if latest:
            latest_total = _fmt(latest["import_total_active_energy"])
            latest_t1 = _fmt(latest["import_active_energy_T1"])
            latest_t2 = _fmt(latest["import_active_energy_T2"])
            delta_total = _delta(
                latest["import_total_active_energy"],
                earliest["import_total_active_energy"] if earliest else None,
            )

        meter_numbers = sorted({row["meter_number"] for row in rows if row["meter_number"]})
        meta = {}
        if distinct_meters == 1:
            only = conn.execute(
                f"SELECT meter_number FROM {table_name} {spec['where']} LIMIT 1",
                spec["params"],
            ).fetchone()
            if only and only["meter_number"] not in meter_numbers:
                meter_numbers.append(only["meter_number"])
        if meter_numbers:
            placeholders = ",".join("?" for _ in meter_numbers)
            for meter in conn.execute(
                f"""
                SELECT meter_number, type, POWER_grid
                FROM installed_meters
                WHERE meter_number IN ({placeholders})
                """,
                meter_numbers,
            ):
                meta[str(meter["meter_number"])] = meter
        conn.close()

        if distinct_meters == 1 and meter_numbers:
            info = meta.get(str(meter_numbers[0]))
            focus = {
                "meter_number": meter_numbers[0],
                "meter_type": (info["type"] if info and info["type"] else ""),
                "power_grid": (info["POWER_grid"] if info and info["POWER_grid"] else ""),
            }
        for row in rows:
            info = meta.get(str(row["meter_number"]))
            readings.append({
                "meter_number": row["meter_number"] or "",
                "timestamp": row["timestamp"] or "",
                "meter_type": (info["type"] if info and info["type"] else ""),
                "cells": [_fmt(row[name]) for name, _label, _unit in COLUMNS],
                "units": [unit for _name, _label, unit in COLUMNS],
            })
        chart = _chart(chart_rows)

    total_pages = (total_rows + limit - 1) // limit if total_rows else 1
    if page > total_pages:
        page = total_pages
    showing_start = ((page - 1) * limit) + 1 if total_rows else 0
    showing_end = min(page * limit, total_rows)
    now = datetime.now().astimezone()
    query = {
        "meter_number": meter_number or "",
        "type": reading_type,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "line": line or "",
        "limit": limit,
    }

    def page_href(target):
        params = {key: value for key, value in query.items() if value not in ("", None)}
        params["page"] = target
        params["limit"] = limit
        return "/energy-profile-read?" + urlencode(params)

    numbers = [1]
    for number in range(max(2, page - 1), min(total_pages, page + 1) + 1):
        numbers.append(number)
    if total_pages > 1:
        numbers.append(total_pages)
    seen = []
    for number in numbers:
        if number not in seen and 1 <= number <= total_pages:
            seen.append(number)

    return {
        "readings": readings,
        "columns": COLUMNS,
        "meter_number": meter_number or "",
        "selected_type": reading_type,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "line": line or "",
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_rows": total_rows,
        "distinct_meters": distinct_meters,
        "today_rows": today_rows,
        "min_ts": min_ts,
        "max_ts": max_ts,
        "span_hours": _hours(min_ts, max_ts),
        "latest_total": latest_total,
        "latest_t1": latest_t1,
        "latest_t2": latest_t2,
        "delta_total": delta_total,
        "focus": focus,
        "showing_start": showing_start,
        "showing_end": showing_end,
        "chart": chart,
        "page_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "prev_href": page_href(page - 1) if page > 1 else "",
        "next_href": page_href(page + 1) if page < total_pages else "",
        "page_hrefs": [(number, page_href(number)) for number in seen],
        "message": message,
    }


@router.get("/energy-profile-read", response_class=HTMLResponse)
async def profile_read(
    request: Request,
    page: int = 1,
    limit: int = 15,
    meter_number: str = "",
    type: str = "Original",
    start_date: str = "",
    end_date: str = "",
    line: str = "",
    message: str = None,
    user: dict = Depends(require_permission("Data analysis")),
):
    return template_response(request, "energy_profile_read.html", {
        "request": request,
        **_load(meter_number, type, start_date, end_date, line, page, limit, message),
    })


@router.get("/search-energy-profile", response_class=HTMLResponse)
async def search_energy_load_profile(
    request: Request,
    meter_number: str = "",
    type: str = "Original",
    start_date: str = None,
    end_date: str = None,
    line: str = "",
    page: int = 1,
    limit: int = 15,
    user: dict = Depends(require_permission("Data analysis")),
):
    return template_response(request, "energy_profile_read.html", {
        "request": request,
        **_load(meter_number, type, start_date or "", end_date or "", line, page, limit),
    })
