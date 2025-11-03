from fastapi import  Request, Form 
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter, Request

from services.database import get_db_connection  

router = APIRouter() 
templates = Jinja2Templates(directory="templates") 
USERS = {
    "admin": "12345",
    "user": "password"
} 
@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/Dashboard", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})  

@router.post("/login") 
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()  
    if username == "admin" and password == "123456": 
        request.session["user"] = {
                "username" : "admin",
                "role" : "administrator", 
                "permissions": ['Archive', 'Dashboard', 'Data analysis', 'Remote Maintain', 'System Management', 'System Task', 'Warehouse']
            } 
        return RedirectResponse("/Dashboard", status_code=302)   # default user
    user = conn.execute(
        "SELECT * FROM users WHERE user_name = ? AND password = ?",
        (username, password)
    ).fetchone()
    # return RedirectResponse("/Dashboard", status_code=302)   # Match found  

    if user:
        if user["status"] == "Идэвхитэй": 
            permissions = get_permissions(user["role_name"]) 
            print(permissions) 
            request.session["user"] = {
                "username" : user["user_name"],
                "role" : user["role_name"], 
                "permissions": permissions
            }
            return RedirectResponse("/Dashboard", status_code=302)   # Match found
        else:
            return templates.TemplateResponse("login.html", {"request": request, "error": "Хэрэглэгч идэвхгүй байна"}) 
    else:
            return templates.TemplateResponse("login.html", {"request": request, "error": "Хэрэглэгчийн нэр эсвэл нууц үг буруу."})  
      

@router.post("/logout")
async def logout(request: Request):  
    request.session.clear() 
    return RedirectResponse("/login", status_code=302)   
 
def get_permissions(role_name): 
    conn = get_db_connection()     
    rows = conn.execute(
        "SELECT permission_name FROM role_permissions WHERE role_name = ?", 
        (role_name,)
    ).fetchall()  
    conn.close()
    # Extract just the permission_name values
    return [row["permission_name"] for row in rows]  
