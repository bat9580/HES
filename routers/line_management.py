import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.parameters import obis_to_column
from utils.utility_functions import require_permission, template_response 
templates = Jinja2Templates(directory="templates")

router = APIRouter()

_LEVEL_ORDER = ["Цахилгаан станц", "Дэд станц", "Фидер", "Трансформер"]


def _line_filters(request: Request):
    q = (request.query_params.get("q") or request.query_params.get("line_name") or "").strip()
    level = (request.query_params.get("level") or "").strip()
    parent = (request.query_params.get("parent") or "").strip()
    bound = (request.query_params.get("bound") or "").strip()
    return q, level, parent, bound


def _load_lines(conn, q, level, parent, bound):
    rows = conn.execute(
        "SELECT line_name, line_level, parent_node FROM lines ORDER BY line_name"
    ).fetchall()

    meter_counts = {}
    dcu_for_line = {}
    try:
        grouped = conn.execute(
            """
            SELECT TRIM(line) AS line_name, DCU_number, COUNT(*) AS c
            FROM installed_meters
            WHERE line IS NOT NULL AND TRIM(line) != ''
            GROUP BY TRIM(line), DCU_number
            """
        ).fetchall()
    except sqlite3.Error:
        grouped = []
    for row in grouped:
        name = row["line_name"]
        meter_counts[name] = meter_counts.get(name, 0) + row["c"]
        if row["DCU_number"]:
            bucket = dcu_for_line.setdefault(name, {})
            key = str(row["DCU_number"])
            bucket[key] = bucket.get(key, 0) + row["c"]

    try:
        unassigned = conn.execute(
            """
            SELECT COUNT(*) AS c FROM installed_meters
            WHERE line IS NULL OR TRIM(line) = ''
            """
        ).fetchone()["c"]
        installed_total = conn.execute(
            "SELECT COUNT(*) AS c FROM installed_meters"
        ).fetchone()["c"]
    except sqlite3.Error:
        unassigned = 0
        installed_total = 0

    records = []
    for row in rows:
        name = row["line_name"]
        dcus = dcu_for_line.get(name, {})
        dominant = max(dcus, key=dcus.get) if dcus else ""
        count = meter_counts.get(name, 0)
        records.append(
            {
                "line_name": name,
                "line_level": row["line_level"] or "",
                "parent_node": row["parent_node"] or "",
                "meter_count": count,
                "meter_pct": int(round(count / installed_total * 100)) if installed_total else 0,
                "dcu": dominant,
                "is_root": not (row["parent_node"] or "").strip(),
            }
        )

    level_counts = {}
    for item in records:
        key = item["line_level"] or "Тодорхойгүй"
        level_counts[key] = level_counts.get(key, 0) + 1

    groups = []
    seen = set()
    for name in _LEVEL_ORDER + sorted(level_counts):
        if name in seen or name not in level_counts:
            continue
        seen.add(name)
        members = [item for item in records if (item["line_level"] or "Тодорхойгүй") == name]
        groups.append(
            {
                "level": name,
                "count": level_counts[name],
                "meters": sum(item["meter_count"] for item in members),
                "names": [item["line_name"] for item in members[:3]],
            }
        )

    filtered = records
    if q:
        needle = q.lower()
        filtered = [
            item
            for item in filtered
            if needle in item["line_name"].lower()
            or needle in item["parent_node"].lower()
            or needle in item["line_level"].lower()
        ]
    if level:
        filtered = [item for item in filtered if item["line_level"] == level]
    if parent:
        filtered = [item for item in filtered if item["parent_node"] == parent]
    if bound == "yes":
        filtered = [item for item in filtered if item["meter_count"] > 0]
    elif bound == "no":
        filtered = [item for item in filtered if item["meter_count"] == 0]

    total = len(records)
    roots = sum(1 for item in records if item["is_root"])

    return {
        "lines": filtered,
        "line_total": total,
        "line_roots": roots,
        "line_branches": total - roots,
        "level_count": len(level_counts),
        "level_groups": groups,
        "substation_count": level_counts.get("Дэд станц", 0),
        "plant_count": level_counts.get("Цахилгаан станц", 0),
        "assigned_meters": sum(item["meter_count"] for item in records),
        "unassigned_meters": unassigned,
        "installed_total": installed_total,
        "level_options": [name for name in _LEVEL_ORDER if name in level_counts]
        + [name for name in sorted(level_counts) if name not in _LEVEL_ORDER],
        "parent_options": sorted({item["parent_node"] for item in records if item["parent_node"]}),
        "q": q,
        "level": level,
        "parent": parent,
        "bound": bound,
        "page_time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
    }


@router.get("/line-management", response_class=HTMLResponse)
async def line_management(
    request: Request,
    message: str = None,
    user: dict = Depends(require_permission("Warehouse")),
):
    q, level, parent, bound = _line_filters(request)
    conn = get_db_connection()
    context = _load_lines(conn, q, level, parent, bound)
    conn.close()
    context.update(
        {
            "request": request,
            "message": request.query_params.get("message") or message,
        }
    )
    return template_response(request, "line_management.html", context)


@router.get("/search-line")
async def search_line(request: Request):
    query = request.url.query
    target = "/line-management" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=307)
@router.post("/add-line") 
async def add_line( 
    line_name: str = Form(...),
    line_level: str = Form(...),  
    parent_node: str = Form(None),  
):  
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO lines 
            (line_name, line_level, parent_node)
            VALUES (?, ?, ?) 
        """, (line_name, line_level, parent_node,))  
        conn.commit()
        message = "✅ Line added successfully."
    except sqlite3.IntegrityError:
        message = "⚠️ Same Line is already registered." 
    finally:
        conn.close()

    return RedirectResponse(url=f"/line-management?message={message}", status_code=303)   

@router.post("/edit-line")
async def edit_line(
    original_line_name: str = Form(...),  # hidden input for original name
    line_name: str = Form(...),
    line_level: str = Form(...),
    parent_node: str = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Rule 1: Parent node cannot be itself
        if parent_node == original_line_name:
            message = "❌ Parent node cannot be the same as the line itself."
            return RedirectResponse(url=f"/line-management?message={message}", status_code=303)

        # Rule 2: Parent node cannot be any of its descendants
        descendants = get_descendants(cursor, original_line_name)
        if parent_node in descendants:
            message = "❌ Parent node cannot be a child or descendant of this line."
            return RedirectResponse(url=f"/line-management?message={message}", status_code=303)

        # If all checks pass, update the line
        cursor.execute("""
            UPDATE lines
            SET line_name = ?, line_level = ?, parent_node = ?
            WHERE line_name = ?
        """, (line_name, line_level, parent_node, original_line_name))
        conn.commit()

        message = "✅ Line updated successfully."
    except sqlite3.IntegrityError:
        message = "⚠️ A line with the same name already exists."
    finally:
        conn.close()

    return RedirectResponse(url=f"/line-management?message={message}", status_code=303)

@router.post("/delete-line")  
async def delete_line( line_name : str = Form(...)):   
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lines WHERE line_name = ?", (line_name,)) 
    conn.commit()
    conn.close()
    message = f"✅ Line is successfully deleted."  
    return RedirectResponse(url=f"/line-management?message={message}", status_code=303) 


def get_lines_from_db():
    conn = get_db_connection()  
    cursor = conn.cursor()
    cursor.execute("SELECT line_name, parent_node FROM lines")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def build_tree(data):
    lookup = {}

    # Create lookup nodes
    for d in data:
        lookup[d["line_name"]] = {"text": d["line_name"], "children": []}

    # Assign children to parents
    root_nodes = []
    for d in data:
        if d["parent_node"] is None or d["parent_node"] == '':
            root_nodes.append(lookup[d["line_name"]])
        else:
            lookup[d["parent_node"]]["children"].append(lookup[d["line_name"]])

    return root_nodes  # jsTree expects a list

@router.get("/line-tree-data")
def get_line_tree():
    lines = get_lines_from_db()
    tree_result = build_tree(lines)
    return JSONResponse(tree_result)  




def get_descendants(cursor, line_name):
    """
    Recursively get all descendant lines for a given line_name.
    """
    descendants = set()
    stack = [line_name]

    while stack:
        current = stack.pop()
        cursor.execute("SELECT line_name FROM lines WHERE parent_node = ?", (current,))
        children = [row[0] for row in cursor.fetchall()]
        for child in children:
            if child not in descendants:
                descendants.add(child)
                stack.append(child)

    return descendants 