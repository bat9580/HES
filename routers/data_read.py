from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from services.database import get_db_connection
from utils.parameters import obis_to_column
from utils.utility_functions import get_meters_by_line, require_permission, template_response

router = APIRouter()

OBIS_OPTIONS = (
    ("1.8.0", "Нийт импортын актив энерги (1.8.0)"),
    ("1.8.1", "Импортын актив энерги T1 (1.8.1)"),
    ("1.8.2", "Импортын актив энерги T2 (1.8.2)"),
    ("1.8.3", "Импортын актив энерги T3 (1.8.3)"),
    ("2.8.0", "Нийт экспортын актив энерги (2.8.0)"),
    ("2.8.1", "Экспортын актив энерги T1 (2.8.1)"),
    ("2.8.2", "Экспортын актив энерги T2 (2.8.2)"),
    ("2.8.3", "Экспортын актив энерги T3 (2.8.3)"),
    ("3.8.0", "Нийт импортын реактив энерги (3.8.0)"),
    ("3.8.1", "Импортын реактив энерги T1 (3.8.1)"),
    ("3.8.2", "Импортын реактив энерги T2 (3.8.2)"),
    ("3.8.3", "Импортын реактив энерги T3 (3.8.3)"),
    ("4.8.0", "Нийт экспортын реактив энерги (4.8.0)"),
    ("4.8.1", "Экспортын реактив энерги T1 (4.8.1)"),
    ("4.8.2", "Экспортын реактив энерги T2 (4.8.2)"),
    ("4.8.3", "Экспортын реактив энерги T3 (4.8.3)"),
    ("32.7.0", "A фазын хүчдэл (32.7.0)"),
    ("52.7.0", "Б фазын хүчдэл (52.7.0)"),
    ("72.7.0", "С фазын хүчдэл (72.7.0)"),
    ("31.7.0", "A фазын гүйдэл (31.7.0)"),
    ("51.7.0", "Б фазын гүйдэл (51.7.0)"),
    ("71.7.0", "С фазын гүйдэл (71.7.0)"),
    ("15.7.0", "Нийт актив чадал (15.7.0)"),
    ("21.7.0", "A фазын актив чадал (21.7.0)"),
    ("41.7.0", "Б фазын актив чадал (41.7.0)"),
    ("61.7.0", "С фазын актив чадал (61.7.0)"),
    ("3.7.0", "Нийт реактив чадал (3.7.0)"),
    ("23.7.0", "A фазын реактив чадал (23.7.0)"),
    ("43.7.0", "Б фазын реактив чадал (43.7.0)"),
    ("63.7.0", "С фазын реактив чадал (63.7.0)"),
    ("14.7.0", "Давтамж (14.7.0)"),
)
OBIS_LABELS = dict(OBIS_OPTIONS)
OBIS_UNITS = {
    "1.8.0": "кВт·ц", "1.8.1": "кВт·ц", "1.8.2": "кВт·ц", "1.8.3": "кВт·ц",
    "2.8.0": "кВт·ц", "2.8.1": "кВт·ц", "2.8.2": "кВт·ц", "2.8.3": "кВт·ц",
    "3.8.0": "квар·ц", "3.8.1": "квар·ц", "3.8.2": "квар·ц", "3.8.3": "квар·ц",
    "4.8.0": "квар·ц", "4.8.1": "квар·ц", "4.8.2": "квар·ц", "4.8.3": "квар·ц",
    "32.7.0": "В", "52.7.0": "В", "72.7.0": "В",
    "31.7.0": "А", "51.7.0": "А", "71.7.0": "А",
    "15.7.0": "кВт", "21.7.0": "кВт", "41.7.0": "кВт", "61.7.0": "кВт",
    "3.7.0": "квар", "23.7.0": "квар", "43.7.0": "квар", "63.7.0": "квар",
    "14.7.0": "Гц",
}


def _fmt(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def _table_for(obis_code: str, reading_type: str):
    obis_code = obis_code or "1.8.0"
    mapping = obis_to_column.get(obis_code)
    if not mapping:
        return obis_code, None, None
    table_name, column_name = mapping
    if reading_type == "Calculated":
        if table_name == "energy_profile_readings":
            table_name = "energy_profile_readings_calculated"
        elif table_name == "instantaneous_profile_readings":
            table_name = "instantaneous_profile_readings_calculated"
    return obis_code, table_name, column_name


def _filters(meter_number, obis_code, reading_type, start_date, end_date, line):
    obis_code, table_name, column_name = _table_for(obis_code, reading_type)
    if not table_name:
        return {
            "empty": True,
            "obis_code": obis_code,
            "table_name": "",
            "column_name": "",
            "where": "",
            "params": [],
        }
    where = "WHERE 1 = 1"
    params = []
    meter_numbers_line = []
    if line:
        meter_numbers_line = get_meters_by_line(line)
        if not meter_numbers_line:
            return {
                "empty": True,
                "obis_code": obis_code,
                "table_name": table_name,
                "column_name": column_name,
                "where": where,
                "params": params,
            }
    if meter_numbers_line:
        placeholders = ",".join("?" for _ in meter_numbers_line)
        where += f" AND meter_number IN ({placeholders})"
        params.extend(meter_numbers_line)
    elif meter_number:
        where += " AND meter_number LIKE ?"
        params.append(f"%{meter_number}%")
    if start_date and end_date:
        where += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    return {
        "empty": False,
        "obis_code": obis_code,
        "table_name": table_name,
        "column_name": column_name,
        "where": where,
        "params": params,
    }


def _chart(points):
    usable = [point for point in points if point["value"] is not None]
    if not usable:
        return None
    values = [point["value"] for point in usable]
    low, high = min(values), max(values)
    span = high - low or 1
    count = len(usable)
    coords = []
    for index, point in enumerate(usable):
        x = 0 if count == 1 else index * 1000 / (count - 1)
        y = 50 - ((point["value"] - low) / span) * 40
        coords.append({"x": round(x, 2), "y": round(y, 2), "t": point["timestamp"]})
    return {
        "coords": coords,
        "min": _fmt(low),
        "max": _fmt(high),
        "mean": _fmt(sum(values) / len(values)),
        "first": usable[0]["timestamp"],
        "last": usable[-1]["timestamp"],
        "meter": usable[0]["meter_number"] if len({point["meter_number"] for point in usable}) == 1 else "",
    }


def _load(
    meter_number="",
    obis_code="1.8.0",
    reading_type="Original",
    start_date="",
    end_date="",
    line="",
    page=1,
    limit=15,
    message=None,
):
    if reading_type not in ("Original", "Calculated"):
        reading_type = "Original"
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

    spec = _filters(meter_number or "", obis_code or "1.8.0", reading_type, start_date or "", end_date or "", line or "")
    column_name = spec["column_name"]
    readings = []
    chart = None
    total_rows = 0
    distinct_meters = 0
    today_rows = 0
    avg_value = None
    min_ts = ""
    max_ts = ""

    if not spec["empty"]:
        conn = get_db_connection()
        today = datetime.now().strftime("%Y-%m-%d")
        stats = conn.execute(
            f"""
            SELECT COUNT(*),
                   COUNT(DISTINCT meter_number),
                   MIN(timestamp),
                   MAX(timestamp),
                   AVG({column_name}),
                   SUM(CASE WHEN timestamp LIKE ? THEN 1 ELSE 0 END)
            FROM {spec["table_name"]} {spec["where"]}
            """,
            (f"{today}%", *spec["params"]),
        ).fetchone()
        total_rows = stats[0] or 0
        distinct_meters = stats[1] or 0
        min_ts = stats[2] or ""
        max_ts = stats[3] or ""
        avg_value = stats[4]
        today_rows = stats[5] or 0
        total_pages_now = (total_rows + limit - 1) // limit if total_rows else 1
        if page > total_pages_now:
            page = total_pages_now

        offset = (page - 1) * limit
        rows = conn.execute(
            f"""
            SELECT meter_number, timestamp, {column_name} AS value
            FROM {spec["table_name"]} {spec["where"]}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (*spec["params"], limit, offset),
        ).fetchall()
        chart_rows = conn.execute(
            f"""
            SELECT meter_number, timestamp, {column_name} AS value
            FROM {spec["table_name"]} {spec["where"]}
            ORDER BY timestamp ASC
            LIMIT 200
            """,
            spec["params"],
        ).fetchall()
        meter_numbers = sorted({row["meter_number"] for row in rows if row["meter_number"]})
        meta = {}
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
                meta[meter["meter_number"]] = meter
        conn.close()

        for row in rows:
            info = meta.get(row["meter_number"])
            readings.append({
                "meter_number": row["meter_number"] or "",
                "timestamp": row["timestamp"] or "",
                "value": _fmt(row["value"]),
                "meter_type": (info["type"] if info and info["type"] else ""),
                "power_grid": (info["POWER_grid"] if info and info["POWER_grid"] else ""),
            })
        chart = _chart([
            {
                "meter_number": row["meter_number"] or "",
                "timestamp": row["timestamp"] or "",
                "value": row["value"],
            }
            for row in chart_rows
        ])

    total_pages = (total_rows + limit - 1) // limit if total_rows else 1
    if page > total_pages:
        page = total_pages
    showing_start = ((page - 1) * limit) + 1 if total_rows else 0
    showing_end = min(page * limit, total_rows)
    now = datetime.now().astimezone()
    query = {
        "meter_number": meter_number or "",
        "obis_code": spec["obis_code"],
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
        return "/data-read?" + urlencode(params)

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
        "meter_number": meter_number or "",
        "selected_obis_code": spec["obis_code"],
        "selected_obis_label": OBIS_LABELS.get(spec["obis_code"], spec["obis_code"]),
        "selected_type": reading_type,
        "unit": OBIS_UNITS.get(spec["obis_code"], ""),
        "start_date": start_date or "",
        "end_date": end_date or "",
        "line": line or "",
        "column": column_name,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_rows": total_rows,
        "distinct_meters": distinct_meters,
        "today_rows": today_rows,
        "avg_value": _fmt(avg_value) if avg_value is not None else "—",
        "min_ts": min_ts,
        "max_ts": max_ts,
        "showing_start": showing_start,
        "showing_end": showing_end,
        "chart": chart,
        "obis_options": OBIS_OPTIONS,
        "page_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "prev_href": page_href(page - 1) if page > 1 else "",
        "next_href": page_href(page + 1) if page < total_pages else "",
        "page_hrefs": [(number, page_href(number)) for number in seen],
        "message": message,
    }


@router.get("/data-read", response_class=HTMLResponse)
async def data_read(
    request: Request,
    page: int = 1,
    limit: int = 15,
    meter_number: str = "",
    obis_code: str = "1.8.0",
    type: str = "Original",
    start_date: str = "",
    end_date: str = "",
    line: str = "",
    message: str = None,
    user: dict = Depends(require_permission("Data analysis")),
):
    return template_response(request, "data_read.html", {
        "request": request,
        **_load(meter_number, obis_code, type, start_date, end_date, line, page, limit, message),
    })


@router.get("/search-one-reading", response_class=HTMLResponse)
async def search_energy_load_profile(
    request: Request,
    meter_number: str = "",
    obis_code: str = "1.8.0",
    type: str = "Original",
    start_date: str = None,
    end_date: str = None,
    line: str = "",
    page: int = 1,
    limit: int = 15,
    user: dict = Depends(require_permission("Data analysis")),
):
    return template_response(request, "data_read.html", {
        "request": request,
        **_load(meter_number, obis_code, type, start_date or "", end_date or "", line, page, limit),
    })
