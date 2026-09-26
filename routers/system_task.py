import sqlite3
from datetime import datetime

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from services.state import scheduler
from utils.utility_functions import add_task_to_existing_meters, remove_task_from_exsisting_meters,edit_tasks_on_existing_meters, require_permission, template_response
templates = Jinja2Templates(directory="templates")

router = APIRouter()

INVOKE_TARGETS = (
    "Energy load profile",
    "Instantanious load profile",
    "Voltage read",
    "Active Power read",
)
_WEEKDAYS = ("Ням", "Даваа", "Мягмар", "Лхагва", "Пүрэв", "Баасан", "Бямба")


def _cron_text(expr: str) -> str:
    parts = (expr or "").strip().split()
    if len(parts) != 5:
        return ""
    minute, hour, day, month, dow = parts
    if minute.startswith("*/") and hour == day == month == dow == "*":
        step = minute[2:]
        if step.isdigit():
            return f"{int(step)} минут тутамд"
    if hour.startswith("*/") and minute == "0" and day == month == dow == "*":
        step = hour[2:]
        if step.isdigit():
            return f"{int(step)} цаг тутамд"
    if minute == "0" and hour == "*" and day == month == dow == "*":
        return "Цаг тутам"
    if minute.isdigit() and hour.isdigit() and day == month == "*" and dow == "*":
        return f"Өдөр бүр {int(hour):02d}:{int(minute):02d}"
    if minute.isdigit() and hour.isdigit() and day.isdigit() and month == "*" and dow == "*":
        return f"Сар бүрийн {int(day)}-ний {int(hour):02d}:{int(minute):02d}"
    if minute.isdigit() and hour.isdigit() and day == month == "*" and dow.isdigit():
        index = int(dow)
        label = _WEEKDAYS[index] if 0 <= index <= 6 else dow
        return f"7 хоног бүрийн {label} {int(hour):02d}:{int(minute):02d}"
    return ""


def _next_fire(expr: str):
    try:
        trigger = CronTrigger.from_crontab((expr or "").strip())
        now = datetime.now(trigger.timezone)
        return trigger.get_next_fire_time(None, now)
    except Exception:
        return None


def _task_page(task_name: str = "", invoke_target: str = "", message: str = None):
    query = "SELECT task_name, invoke_target, cron_expression, remark FROM tasks WHERE 1=1"
    params = []
    if task_name:
        query += " AND task_name LIKE ?"
        params.append(f"%{task_name}%")
    if invoke_target and invoke_target in INVOKE_TARGETS:
        query += " AND invoke_target = ?"
        params.append(invoke_target)
    else:
        invoke_target = ""
    query += " ORDER BY task_name"
    conn = get_db_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    tasks = []
    earliest = None
    earliest_name = ""
    cron_ready = 0
    for row in rows:
        expr = row["cron_expression"] or ""
        nxt = _next_fire(expr)
        if expr:
            cron_ready += 1
        if nxt is not None and (earliest is None or nxt < earliest):
            earliest = nxt
            earliest_name = row["task_name"]
        tasks.append({
            "task_name": row["task_name"],
            "invoke_target": row["invoke_target"] or "",
            "cron_expression": expr,
            "remark": row["remark"] or "",
            "cron_text": _cron_text(expr),
            "next_run": nxt.strftime("%Y-%m-%d %H:%M:%S") if nxt else "",
        })

    try:
        scheduler_running = bool(scheduler.running)
        job_count = len(scheduler.get_jobs()) if scheduler_running else 0
    except Exception:
        scheduler_running = False
        job_count = 0

    now = datetime.now().astimezone()
    return {
        "tasks": tasks,
        "task_total": len(tasks),
        "cron_ready": cron_ready,
        "next_name": earliest_name,
        "next_run": earliest.strftime("%Y-%m-%d %H:%M:%S") if earliest else "",
        "next_iso": earliest.isoformat() if earliest else "",
        "scheduler_running": scheduler_running,
        "job_count": job_count,
        "page_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "page_iso": now.isoformat(timespec="seconds"),
        "task_name": task_name or "",
        "invoke_target": invoke_target or "",
        "invoke_targets": INVOKE_TARGETS,
        "message": message,
    }


@router.get("/system-task",response_class=HTMLResponse) 
async def system_task(
    request: Request,
    message: str = None,
    task_name: str = "",
    invoke_target: str = "",
    user: dict = Depends(require_permission("System Task")),
):
    return template_response(request, "system_task.html", {
        "request": request,
        **_task_page(task_name, invoke_target, message),
    }) 

@router.post("/add-task")  
async def add_task(
    request: Request,
    task_name: str = Form(...),
    invoke_target: str = Form(...),
    cron_expression: str = Form(None),
    remarks: str = Form(...)): 

    conn = get_db_connection() 
    cursor = conn.cursor() 
    try:
        # ✅ Check for duplicate based on invoke_target and cron_expression
        cursor.execute("""
            SELECT 1 FROM tasks
            WHERE invoke_target = ? AND cron_expression = ?
        """, (invoke_target, cron_expression))
        existing_task = cursor.fetchone()

        if existing_task:
            message = f"⚠️ A task with the same target and cron already exists."
        else:
            cursor.execute("""
                INSERT INTO tasks
                (task_name, invoke_target, cron_expression, remark)
                VALUES (?, ?, ?, ?)   
            """, (task_name, invoke_target, cron_expression, remarks))   
            conn.commit() 
            message = f"✅ Task added successfully."    
            add_task_to_existing_meters(invoke_target,cron_expression)    
    except sqlite3.IntegrityError: 
        message = f"⚠️ Task name already exists."   

    finally: 
        conn.close() 

    return RedirectResponse(url=f"/system-task?message={message}", status_code=303)




        
        

@router.post("/edit-task")
async def add_meter(
    request: Request,
    original_task_name: str = Form(...),
    task_name: str = Form(...),
    invoke_target: str = Form(...),
    cron_expression: str = Form(...),
    remarks: str = Form(None)):

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # ✅ Check for duplicate invoke_target + cron_expression (excluding the current task)
        cursor.execute("""
            SELECT 1 FROM tasks
            WHERE invoke_target = ? AND cron_expression = ?
              AND task_name != ?
        """, (invoke_target, cron_expression, original_task_name))
        existing_task = cursor.fetchone()
         

        if existing_task:
            message = f"⚠️ A task with the same target and cron already exists."
        else:
            cursor.execute("SELECT invoke_target, cron_expression FROM tasks WHERE task_name = ?", (original_task_name,)) 
            row = cursor.fetchone() 
            invoke_target_old, cron_expression_old = row 
            cursor.execute("""
                UPDATE tasks
                SET task_name = ?,
                    invoke_target = ?,
                    cron_expression = ?,
                    remark = ?
                WHERE task_name = ?
            """, (task_name, invoke_target, cron_expression, remarks, original_task_name)) 
            conn.commit()
            edit_tasks_on_existing_meters(invoke_target_old, cron_expression_old, invoke_target, cron_expression) 
            message = f"✅ Task edited successfully."

    except sqlite3.IntegrityError:
        message = f"⚠️ Task name already exists."

    finally:
        conn.close()

    return RedirectResponse(url=f"/system-task?message={message}", status_code=303)

@router.post("/clear-task")
async def clear_selected_task(request:Request):
    data = await request.json()
    selected_tasks = data.get("selected_tasks")  
    conn = get_db_connection()
    cursor = conn.cursor()
    
     
    for task in selected_tasks: 
        cursor.execute("SELECT invoke_target, cron_expression FROM tasks WHERE task_name = ?", (task,))
        row = cursor.fetchone() 
        invoke_target, cron_expression = row  
        cursor.execute("DELETE FROM tasks WHERE task_name = ?", (task,))   
        remove_task_from_exsisting_meters(invoke_target, cron_expression)  
    conn.commit()
    conn.close()
     
    message = f"✅ tasks are successfully deleted."  
    return RedirectResponse(url=f"/system-task?message={message}", status_code=303) 
@router.get("/search-task", response_class=HTMLResponse)
async def search_task(
    request: Request,
    task_name: str = "",
    invoke_target: str = "",
    user: dict = Depends(require_permission("System Task")),
):
    return template_response(request, "system_task.html", {
        "request": request,
        **_task_page(task_name, invoke_target),
    })
 