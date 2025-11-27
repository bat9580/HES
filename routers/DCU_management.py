import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.utility_functions import require_permission, template_response

templates = Jinja2Templates(directory="templates")

router = APIRouter()


@router.get("/DCU-management", response_class=HTMLResponse)
async def dcu_management(
    request: Request,
    message: Optional[str] = None,
    user: dict = Depends(require_permission("Warehouse")),
):
    message = request.query_params.get("message")
    filter_dcu = request.query_params.get("dcu_number", "") or ""
    filter_status = request.query_params.get("status", "") or ""

    conn = get_db_connection()
    dcus = conn.execute("SELECT * FROM registered_dcus").fetchall()
    conn.close()
    return template_response(
        request,
        "DCU_management.html",
        {
            "request": request,
            "registered_dcus": dcus,
            "message": message,
            "dcu_number": filter_dcu,
            "status": filter_status,
        },
    )


@router.post("/add-dcu")
async def add_dcu(
    request: Request,
    dcu_number: str = Form(...),
    comm_address: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO registered_dcus 
            (dcu_number, com_address, password, remarks, status)
            VALUES (?, ?, ?, ?, ?)
        """,
            (dcu_number, comm_address, password, remarks, status),
        )
        conn.commit()
        message = "✅ DCU added successfully."
    except sqlite3.IntegrityError:
        message = "⚠️ Same DCU NUMBER is already registered."
    finally:
        conn.close()

    return RedirectResponse(url=f"/DCU-management?message={message}", status_code=303)


@router.post("/edit-dcu")
async def edit_dcu(
    request: Request,
    original_dcu_number: str = Form(...),
    dcu_number: str = Form(...),
    comm_address: str = Form(...),
    remarks: str = Form(None),
    password: str = Form(...),
    status: str = Form(...),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE registered_dcus 
            SET dcu_number = ?,
                com_address = ?,
                password = ?, 
                remarks = ?,
                status = ? 
            WHERE dcu_number = ?
        """,
            (dcu_number, comm_address, password, remarks, status, original_dcu_number),
        )
        conn.commit()
        message = "✅ DCU edited successfully."
    except sqlite3.IntegrityError:
        message = "⚠️ Same DCU NUMBER is already registered."
    finally:
        conn.close()
    return RedirectResponse(url=f"/DCU-management?message={message}", status_code=303)


@router.post("/delete-dcu")
async def delete_dcu(dcu_number: str = Form(...)):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM registered_dcus WHERE 1=1"
    params: List[str] = []
    if dcu_number:
        query += " AND dcu_number LIKE ?"
        params.append(f"%{dcu_number}%")

    dcu = conn.execute(query, params).fetchone()

    if not dcu:
        message = "⚠️ DCU not found."
    elif dcu["status"] == "installed":
        message = "⚠️ Please dismantle the DCU first."
    else:
        cursor.execute("DELETE FROM registered_dcus WHERE dcu_number = ?", (dcu_number,))
        conn.commit()
        message = "✅ DCU is successfully deleted."

    conn.close()
    return RedirectResponse(url=f"/DCU-management?message={message}", status_code=303)


@router.get("/search-dcu", response_class=HTMLResponse)
async def search_dcu(
    request: Request,
    dcu_number: str = "",
    status: str = "",
    user: dict = Depends(require_permission("Warehouse")),
):
    query = "SELECT * FROM registered_dcus WHERE 1=1"
    params = []
    if dcu_number:
        query += " AND dcu_number LIKE ?"
        params.append(f"%{dcu_number}%")
    if status:
        query += " AND status LIKE ?"
        params.append(f"%{status}%")

    conn = get_db_connection()
    searched_dcus = conn.execute(query, params).fetchall()
    conn.close()

    return template_response(
        request,
        "DCU_management.html",
        {
            "request": request,
            "registered_dcus": searched_dcus,
            "dcu_number": dcu_number,
            "status": status,
        },
    )