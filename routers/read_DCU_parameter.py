import asyncio
import sqlite3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.state import connected_clients, pending_requests
import utils.frames as frames 

from services.database import get_db_connection
templates = Jinja2Templates(directory="templates")

router = APIRouter()
@router.get("/read_DCU_parameter", response_class=HTMLResponse) 
async def read_DCU_parameter(request: Request, message: str=None): 
    conn = get_db_connection() 
    registered_dcu = conn.execute("SELECT *FROM registered_dcus").fetchall()   
    conn.close()
    return templates.TemplateResponse("read_DCU_parameter.html", {"request": request,"registered_dcus": registered_dcu,"connected_clients": connected_clients})  
@router.get("/search-dcu-1", response_class=HTMLResponse)
async def search_dcu(request:Request, dcu_number: str = ""):   
    query = "SELECT * FROM registered_dcus WHERE 1=1"  
    params = [] 
    query+= " AND dcu_number LIKE ?"   
    params.append(f"%{dcu_number}%") 
    
    conn = get_db_connection()  
    searched_dcus = conn.execute(query, params).fetchall() 
    conn.close()  
 
    return templates.TemplateResponse("read_DCU_parameter.html",{  
        "request": request, 
        "registered_dcus": searched_dcus,
        "dcu_number": dcu_number 
    })
@router.post("/read-dcu-parameter")
async def read_DCU_parameter(request: Request):
    data = await request.json()
    selected_dcus = data.get("selected_dcus")
    selected_parameters = data.get("selected_parameters")

    results = []

    for dcu in selected_dcus:
        if dcu not in connected_clients:
            results.append({
                "dcu_number": dcu,
                "result": "Error: DCU is offline"
            })
            continue

        response_future = asyncio.Future()
        pending_requests[dcu] = response_future

        # You can tailor what frame to send based on selected_parameters if needed
        await connected_clients[dcu]['queue'].put(bytes.fromhex(frames.GET_DCU_NAME))

        try:
            response_data = await asyncio.wait_for(response_future, timeout=20)
            response_data = response_data[22:30].decode('utf-8', errors='ignore').strip()  
            results.append({
                "dcu_number": dcu,
                "result": response_data
            })

        except asyncio.TimeoutError:
            results.append({
                "dcu_number": dcu,
                "result": "Error: Timed out waiting for DCU response"
            })

    return JSONResponse(content=results)
