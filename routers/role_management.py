import sqlite3
from collections import defaultdict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.utility_functions import require_permission, template_response

templates = Jinja2Templates(directory="templates")
router = APIRouter()

# These are the menu gates the app actually checks. They are not sample roles.
MENUS = [
    {"name": "Warehouse", "label": "Бүртгэл"},
    {"name": "Archive", "label": "Суурилуулалт"},
    {"name": "Remote Maintain", "label": "Шууд унших"},
    {"name": "System Task", "label": "Хуваариуд"},
    {"name": "Data analysis", "label": "Өгөгдлүүд"},
    {"name": "System Management", "label": "Систем"},
]


def _href(role_name, page, limit):
    return "/role-management?" + urlencode({
        "role_name": role_name or "",
        "page": page,
        "limit": limit,
    })


def _load(role_name="", page=1, limit=15, message=None):
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 15
    if limit not in (15, 30, 50, 100):
        limit = 15

    conn = get_db_connection()
    roles_total = conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
    grants_total = conn.execute("SELECT COUNT(*) FROM role_permissions").fetchone()[0]
    users_total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    empty_roles = conn.execute(
        """
        SELECT COUNT(*) FROM roles r
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions p WHERE p.role_name = r.role_name
        )
        """
    ).fetchone()[0]

    where = "WHERE 1=1"
    params = []
    token = (role_name or "").strip()
    if token:
        where += " AND r.role_name LIKE ?"
        params.append(f"%{token}%")

    filtered = conn.execute(
        f"SELECT COUNT(*) FROM roles r {where}",
        params,
    ).fetchone()[0]
    pages = max(1, (filtered + limit - 1) // limit) if filtered else 1
    if page > pages:
        page = pages
    offset = (page - 1) * limit

    rows = conn.execute(
        f"""
        SELECT r.role_name, r.remark, COUNT(u.user_name) AS user_count
        FROM roles r
        LEFT JOIN users u ON u.role_name = r.role_name
        {where}
        GROUP BY r.role_name, r.remark
        ORDER BY r.role_name
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    names = [row["role_name"] for row in rows]
    perms_map = defaultdict(list)
    if names:
        marks = ",".join("?" for _ in names)
        for row in conn.execute(
            f"""
            SELECT role_name, permission_name
            FROM role_permissions
            WHERE role_name IN ({marks})
            ORDER BY permission_name
            """,
            names,
        ):
            perms_map[row["role_name"]].append(row["permission_name"])
    conn.close()

    start = offset + 1 if filtered else 0
    end = offset + len(rows)
    page_links = [
        {"n": n, "href": _href(token, n, limit), "current": n == page}
        for n in range(1, pages + 1)
    ]
    return {
        "roles": [
            {
                "role_name": row["role_name"],
                "remark": row["remark"] or "",
                "user_count": row["user_count"] or 0,
                "grant_count": len(perms_map.get(row["role_name"], [])),
            }
            for row in rows
        ],
        "role_permissions": dict(perms_map),
        "menus": MENUS,
        "menu_count": len(MENUS),
        "message": message,
        "role_name": token,
        "page": page,
        "limit": limit,
        "pages": page_links,
        "prev_href": _href(token, page - 1, limit) if page > 1 else "",
        "next_href": _href(token, page + 1, limit) if page < pages else "",
        "showing_start": start,
        "showing_end": end,
        "filtered": filtered,
        "roles_total": roles_total,
        "grants_total": grants_total,
        "users_total": users_total,
        "empty_roles": empty_roles,
    }


@router.get("/role-management", response_class=HTMLResponse)
async def role_management(
    request: Request,
    message: str = None,
    role_name: str = "",
    page: int = 1,
    limit: int = 15,
    user: dict = Depends(require_permission("System Management")),
):
    return template_response(
        request,
        "role_management.html",
        {"request": request, **_load(role_name, page, limit, message)},
    )


@router.post("/add-role")
async def add_role(
    request: Request,
    role_name: str = Form(...),
    remarks: str = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM roles WHERE role_name = ?", (role_name,))
        existing_user = cursor.fetchone()
        if existing_user:
            message = "A role with the same name already exists."
        else:
            cursor.execute(
                "INSERT INTO roles (role_name, remark) VALUES (?, ?)",
                (role_name, remarks),
            )
            conn.commit()
            message = "Role added successfully."
    except sqlite3.IntegrityError:
        message = "Role already exists."
    finally:
        conn.close()
    return RedirectResponse(url=f"/role-management?message={message}", status_code=303)


@router.post("/edit-user")
async def add_meter(
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
        if original_user_name != user_name:
            cursor.execute("SELECT 1 FROM users WHERE user_name = ?", (user_name,))
            existing_user = cursor.fetchone()
        else:
            existing_user = None
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


@router.post("/update-permissions")
async def update_permissions(role_name: str = Form(...), permissions: list[str] = Form([])):
    role_name = (role_name or "").strip()
    if not role_name:
        return RedirectResponse(url="/role-management?message=Select a role first.", status_code=303)
    allowed = {item["name"] for item in MENUS}
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM role_permissions WHERE role_name = ?", (role_name,))
    for perm in permissions:
        if perm not in allowed:
            continue
        cursor.execute(
            "INSERT OR IGNORE INTO permissions (permission_name) VALUES (?)",
            (perm,),
        )
        cursor.execute(
            "INSERT INTO role_permissions (role_name, permission_name) VALUES (?, ?)",
            (role_name, perm),
        )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/role-management", status_code=303)


@router.post("/clear-roles")
async def clear_selected_role(request: Request):
    data = await request.json()
    selected_roles = data.get("selected_roles") or []
    if not isinstance(selected_roles, list):
        selected_roles = []
    conn = get_db_connection()
    cursor = conn.cursor()
    for role in selected_roles:
        cursor.execute("DELETE FROM roles WHERE role_name = ?", (role,))
        cursor.execute("DELETE FROM role_permissions WHERE role_name = ?", (role,))
    conn.commit()
    conn.close()
    message = "Roles deleted successfully."
    return RedirectResponse(url=f"/role-management?message={message}", status_code=303)


@router.get("/search-role", response_class=HTMLResponse)
async def search_role(
    request: Request,
    role_name: str = "",
    page: int = 1,
    limit: int = 15,
    user: dict = Depends(require_permission("System Management")),
):
    return template_response(
        request,
        "role_management.html",
        {"request": request, **_load(role_name, page, limit)},
    )
