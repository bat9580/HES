import sqlite3
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.state import connected_clients

from services.database import get_db_connection
from collections import defaultdict

from utils.utility_functions import require_permission, template_response 
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/role-management", response_class=HTMLResponse) 
async def role_management(request: Request, message: str = None,user: dict = Depends(require_permission("System Management"))):   
    conn = get_db_connection()   
    roles = conn.execute("SELECT * FROM roles").fetchall()     
    role_permissions = conn.execute("SELECT * FROM role_permissions").fetchall()  
    conn.close()

    # Group permissions by role
    role_perms_map = defaultdict(list)
    for row in role_permissions:
        role_perms_map[row["role_name"]].append(row["permission_name"])

    return template_response(
        request, 
        "role_management.html",
        {
            "request": request,
            "roles": roles,
            "message": message,
            "role_permissions": dict(role_perms_map)  # much easier to use
        }
    )

@router.post("/add-role")     
async def add_role(
    request: Request,
    role_name: str = Form(...),
    remarks: str = Form(None)):  

    conn = get_db_connection() 
    cursor = conn.cursor() 
    try:
        # ✅ Check for duplicate based on invoke_target and cron_expression
        cursor.execute("""
            SELECT 1 FROM roles
            WHERE role_name = ?
        """, (role_name,))
        existing_user = cursor.fetchone() 
 
        if existing_user:
            message = f"⚠️ A Role with the same rolename already exists." 
        else: 
            cursor.execute("""
                INSERT INTO roles
                (role_name, remark)
                VALUES (?,?)    
            """, (role_name, remarks))    
            conn.commit() 
            message = f"✅ Role added successfully."    
    except sqlite3.IntegrityError: 
        message = f"⚠️ Role already exists."    

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


@router.post("/update-permissions")
async def update_permissions(role_name: str = Form(...), permissions: list[str] = Form([])):
    # Save new permissions for this role 
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM role_permissions WHERE role_name = ?", (role_name,))
    for perm in permissions:
        cursor.execute(
            "INSERT INTO role_permissions (role_name, permission_name) VALUES (?, ?)",
            (role_name, perm)
        )

    conn.commit()
    conn.close() 
    print(permissions) 
    print(f"Updating {role_name} with permissions: {permissions}")
    # Here you would update the database
    return RedirectResponse(url="/role-management", status_code=303) 
@router.post("/clear-roles")
async def clear_selected_role(request:Request): 
    data = await request.json()    
    selected_roles = data.get("selected_roles")    
    conn = get_db_connection()
    cursor = conn.cursor()
    
     
    for role in selected_roles:  
        cursor.execute("DELETE FROM roles WHERE role_name = ?", (role,))   
        cursor.execute("DELETE FROM role_permissions WHERE role_name = ?", (role,))  
    conn.commit()
    conn.close()
     
    message = f"✅ roles are successfully deleted."  
    return RedirectResponse(url=f"/role-management?message={message}", status_code=303) 
@router.get("/search-role", response_class=HTMLResponse)
async def search_role(request:Request, role_name: str = "", user: dict = Depends(require_permission("System Management"))):  
    query = "SELECT * FROM roles WHERE 1=1"  
    params = [] 
    if role_name: 
        query+= " AND role_name LIKE ?"    
        params.append(f"%{role_name}%")  
    conn = get_db_connection()  
    searched_roles = conn.execute(query, params).fetchall()    
    role_permissions = conn.execute("SELECT * FROM role_permissions").fetchall()  
    conn.close()

    # Group permissions by role
    role_perms_map = defaultdict(list)
    for row in role_permissions:
        role_perms_map[row["role_name"]].append(row["permission_name"])

    return template_response(
        request, 
        "role_management.html",
        {
            "request": request,
            "roles": searched_roles,
            "role_permissions": dict(role_perms_map)  # much easier to use
        }
    )



