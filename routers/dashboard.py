# routers/dashboard.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)  
async def home(request: Request, message: str = None): 
    return templates.TemplateResponse("dashboard.html", {"request": request, "message": message})   

@router.get("/Dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, message: str = None):
    message = request.query_params.get("message")
    conn = get_db_connection()
    registered_meters = conn.execute("SELECT * FROM registered_meters").fetchall()
    conn.close()
    return templates.TemplateResponse(
        "dashboard.html", 
        {
            "request": request,
            "message": message,
            "registered_meters": registered_meters
        }
    )
