import sqlite3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.state import connected_clients

from services.database import get_db_connection
from utils.utility_functions import add_task_to_existing_meters, remove_task_from_exsisting_meters,edit_tasks_on_existing_meters
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/system-task",response_class=HTMLResponse) 
async def system_task(request: Request, message: str=None): 
    conn = get_db_connection()   
    tasks = conn.execute("SELECT *FROM tasks").fetchall()    
    print(tasks)    
    conn.close()
    return templates.TemplateResponse("system_task.html", {"request": request, "tasks":tasks,"message":message})
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
async def search_task(request:Request, task_name: str = ""):  
    query = "SELECT * FROM tasks WHERE 1=1"  
    params = [] 
    if task_name: 
        query+= " AND task_name LIKE ?"    
        params.append(f"%{task_name}%") 
    conn = get_db_connection()  
    searched_tasks = conn.execute(query, params).fetchall() 
    conn.close() 
 
    return templates.TemplateResponse("system_task.html",{  
        "request": request, 
        "tasks": searched_tasks,
        "task_name": task_name
    })