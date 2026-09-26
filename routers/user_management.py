from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import sqlite3

from services.database import get_db_connection
from utils.utility_functions import require_permission, template_response

router = APIRouter()

ACTIVE = "Идэвхитэй"
INACTIVE = "Идэвхигүй"


def _load(user_name="", role_name="", status="", page=1, limit=15, message=None):
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

    where = "WHERE 1 = 1"
    params = []
    if user_name:
        where += " AND (user_name LIKE ? OR nick_name LIKE ? OR email LIKE ? OR phone_number LIKE ?)"
        token = f"%{user_name}%"
        params.extend([token, token, token, token])
    if role_name:
        where += " AND role_name = ?"
        params.append(role_name)
    if status:
        where += " AND status = ?"
        params.append(status)

    conn = get_db_connection()
    stats = conn.execute(
        f"""
        SELECT COUNT(*),
               SUM(CASE WHEN status = ? THEN 1 ELSE 0 END),
               SUM(CASE WHEN status = ? THEN 1 ELSE 0 END),
               COUNT(DISTINCT role_name)
        FROM users {where}
        """,
        (ACTIVE, INACTIVE, *params),
    ).fetchone()
    total_rows = stats[0] or 0
    active_rows = stats[1] or 0
    inactive_rows = stats[2] or 0
    role_count = stats[3] or 0
    top = conn.execute(
        f"""
        SELECT role_name, COUNT(*) AS n
        FROM users {where}
        GROUP BY role_name
        ORDER BY n DESC, role_name
        LIMIT 1
        """,
        params,
    ).fetchone()
    total_pages = (total_rows + limit - 1) // limit if total_rows else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * limit
    rows = conn.execute(
        f"""
        SELECT user_name, nick_name, phone_number, email, role_name, status
        FROM users {where}
        ORDER BY user_name
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()
    roles = [role["role_name"] for role in conn.execute("SELECT role_name FROM roles ORDER BY role_name")]
    conn.close()

    users = []
    for row in rows:
        users.append({
            "user_name": row["user_name"] or "",
            "nick_name": row["nick_name"] or "",
            "phone_number": row["phone_number"] or "",
            "email": row["email"] or "",
            "role_name": row["role_name"] or "",
            "status": row["status"] or "",
        })

    query = {
        "user_name": user_name or "",
        "role_name": role_name or "",
        "status": status or "",
        "limit": limit,
    }

    def page_href(target):
        kept = {key: value for key, value in query.items() if value not in ("", None)}
        kept["page"] = target
        kept["limit"] = limit
        return "/user-management?" + urlencode(kept)

    numbers = [1]
    for number in range(max(2, page - 1), min(total_pages, page + 1) + 1):
        numbers.append(number)
    if total_pages > 1:
        numbers.append(total_pages)
    seen = []
    for number in numbers:
        if number not in seen and 1 <= number <= total_pages:
            seen.append(number)

    showing_start = ((page - 1) * limit) + 1 if total_rows else 0
    showing_end = min(page * limit, total_rows)
    return {
        "users": users,
        "roles": roles,
        "user_name": user_name or "",
        "selected_role": role_name or "",
        "selected_status": status or "",
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_rows": total_rows,
        "active_rows": active_rows,
        "inactive_rows": inactive_rows,
        "role_count": role_count,
        "top_role": (top["role_name"] if top and top["role_name"] else ""),
        "top_role_count": (top["n"] if top else 0),
        "showing_start": showing_start,
        "showing_end": showing_end,
        "prev_href": page_href(page - 1) if page > 1 else "",
        "next_href": page_href(page + 1) if page < total_pages else "",
        "page_hrefs": [(number, page_href(number)) for number in seen],
        "active_status": ACTIVE,
        "inactive_status": INACTIVE,
        "message": message,
    }


@router.get("/user-management", response_class=HTMLResponse)
async def user_management(
    request: Request,
    message: str = None,
    user_name: str = "",
    role_name: str = "",
    status: str = "",
    page: int = 1,
    limit: int = 15,
    user: dict = Depends(require_permission("System Management")),
):
    return template_response(request, "user_management.html", {
        "request": request,
        **_load(user_name, role_name, status, page, limit, message),
    })


@router.post("/add-user")
async def add_user(
    request: Request,
    user_name: str = Form(...),
    role_name: str = Form(...),
    nick_name: str = Form(None),
    phone_number: str = Form(),
    password: str = Form(),
    status: str = Form(),
    email: str = Form(...),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM users WHERE user_name = ?", (user_name,))
        existing_user = cursor.fetchone()
        if existing_user:
            message = "A user with the same username already exists."
        else:
            cursor.execute(
                """
                INSERT INTO users
                (user_name, role_name, nick_name, phone_number, email, status, password)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_name, role_name, nick_name, phone_number, email, status, password),
            )
            conn.commit()
            message = "User added successfully."
    except sqlite3.IntegrityError:
        message = "User name already exists."
    finally:
        conn.close()
    return RedirectResponse(url=f"/user-management?message={message}", status_code=303)


@router.post("/edit-user")
async def edit_user(
    request: Request,
    original_user_name: str = Form(...),
    user_name: str = Form(...),
    role_name: str = Form(...),
    nick_name: str = Form(None),
    phone_number: str = Form(),
    status: str = Form(),
    email: str = Form(...),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        existing_user = None
        if original_user_name != user_name:
            cursor.execute("SELECT 1 FROM users WHERE user_name = ?", (user_name,))
            existing_user = cursor.fetchone()
        if existing_user:
            message = "A user with the same username already exists."
        else:
            cursor.execute(
                """
                UPDATE users
                SET user_name = ?,
                    role_name = ?,
                    nick_name = ?,
                    phone_number = ?,
                    status = ?,
                    email = ?
                WHERE user_name = ?
                """,
                (user_name, role_name, nick_name, phone_number, status, email, original_user_name),
            )
            conn.commit()
            message = "User edited successfully."
    except sqlite3.IntegrityError:
        message = "Username already exists."
    finally:
        conn.close()
    return RedirectResponse(url=f"/user-management?message={message}", status_code=303)


@router.post("/clear-user")
async def clear_selected_user(request: Request):
    data = await request.json()
    selected_users = data.get("selected_users") or []
    conn = get_db_connection()
    cursor = conn.cursor()
    for user in selected_users:
        cursor.execute("DELETE FROM users WHERE user_name = ?", (user,))
    conn.commit()
    conn.close()
    message = "Users deleted."
    return RedirectResponse(url=f"/user-management?message={message}", status_code=303)


@router.get("/search-user", response_class=HTMLResponse)
async def search_user(
    request: Request,
    user_name: str = "",
    role_name: str = "",
    status: str = "",
    page: int = 1,
    limit: int = 15,
    user: dict = Depends(require_permission("System Management")),
):
    return template_response(request, "user_management.html", {
        "request": request,
        **_load(user_name, role_name, status, page, limit),
    })


@router.get("/get-roles")
async def get_roles():
    conn = get_db_connection()
    roles = conn.execute("SELECT role_name FROM roles").fetchall()
    role_names = [role["role_name"] for role in roles]
    conn.close()
    return JSONResponse(role_names)
