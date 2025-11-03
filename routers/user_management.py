import sqlite3
from urllib import request
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.state import connected_clients

from services.database import get_db_connection
from utils.utility_functions import add_task_to_existing_meters, remove_task_from_exsisting_meters,edit_tasks_on_existing_meters, require_permission, template_response
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/user-management",response_class=HTMLResponse) 
async def user_management(request: Request, message: str=None,user: dict = Depends(require_permission("System Management")) ): 
    conn = get_db_connection()   
    users = conn.execute("SELECT *FROM users").fetchall( )    
    print(users)     
    conn.close()
    return template_response(request,"user_management.html", {"request": request, "users":users,"message":message}) 
 
@router.post("/add-user")    
async def add_user( 
    request: Request,
    user_name: str = Form(...),
    role_name: str = Form(...),
    nick_name: str = Form(None),
    phone_number: str = Form(),
    password: str = Form(), 
    status: str = Form(),  
    email: str = Form(...)): 

    conn = get_db_connection() 
    cursor = conn.cursor() 
    try:
        # ✅ Check for duplicate based on invoke_target and cron_expression
        cursor.execute("""
            SELECT 1 FROM users
            WHERE user_name = ?
        """, (user_name,))
        existing_user = cursor.fetchone() 
 
        if existing_user:
            message = f"⚠️ A User with the same username already exists."
        else: 
            cursor.execute("""
                INSERT INTO users
                (user_name, role_name, nick_name, phone_number, email, status, password) 
                VALUES (?, ?, ?, ?, ?, ?, ?)   
            """, (user_name, role_name, nick_name, phone_number, email, status, password))    
            conn.commit() 
            message = f"✅ User added successfully."    
    except sqlite3.IntegrityError: 
        message = f"⚠️ User name already exists."    
 
    finally: 
        conn.close() 

    return RedirectResponse(url=f"/user-management?message={message}", status_code=303)




        
        

@router.post("/edit-user") 
async def add_meter(
    request: Request,
    original_user_name: str = Form(...), 
    user_name: str = Form(...),
    role_name: str = Form(...),
    nick_name: str = Form(None),
    phone_number: str = Form(),
    status: str = Form(),  
    email: str = Form(...)):

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # ✅ Check for duplicate invoke_target + cron_expression (excluding the current task)
        if original_user_name != user_name:
            cursor.execute("""
                SELECT 1 FROM users
                WHERE user_name = ?
            """, (user_name,))
            existing_user = cursor.fetchone() 
        else: 
            existing_user = None  
         

        if existing_user:
            message = f"⚠️ A User with the same username already exists." 
        else:
            cursor.execute("""
                UPDATE users
                SET user_name = ?,
                    role_name = ?,
                    nick_name = ?,
                    phone_number = ?,
                    status = ?, 
                    email = ?
                WHERE user_name = ?
            """, (user_name, role_name, nick_name, phone_number,status, email, original_user_name))  
            conn.commit()
            message = f"✅ User edited successfully." 

    except sqlite3.IntegrityError:
        message = f"⚠️ Username already exists."

    finally:
        conn.close()

    return RedirectResponse(url=f"/user-management?message={message}", status_code=303) 

@router.post("/clear-user")
async def clear_selected_user(request:Request):
    data = await request.json() 
    selected_users = data.get("selected_users")   
    conn = get_db_connection()
    cursor = conn.cursor()
    
     
    for user in selected_users: 
        cursor.execute("DELETE FROM users WHERE user_name = ?", (user,))   
    conn.commit()
    conn.close()
     
    message = f"✅ users are successfully deleted."  
    return RedirectResponse(url=f"/user-management?message={message}", status_code=303)  
@router.get("/search-user", response_class=HTMLResponse)
async def search_task(request:Request, user_name: str = "",user: dict = Depends(require_permission("System Management"))):  
    query = "SELECT * FROM users WHERE 1=1"  
    params = [] 
    if user_name: 
        query+= " AND user_name LIKE ?"     
        params.append(f"%{user_name}%") 
    conn = get_db_connection()  
    searched_users = conn.execute(query, params).fetchall() 
    conn.close() 
 
    return template_response(request,"system_task.html",{   
        "request": request, 
        "users": searched_users, 
        "user_name": user_name 
    })
@router.get("/get-roles")
async def get_roles(): 
    conn = get_db_connection() 
    roles = conn.execute("SELECT role_name FROM roles").fetchall()
    role_names = [role['role_name'] for role in roles]
    conn.close()
    return JSONResponse(role_names)  

