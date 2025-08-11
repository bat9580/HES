import asyncio
import sqlite3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.state import connected_clients, pending_requests
from utils.parameters import obis_name_map 
from utils.generator_funcitons import generate_frame_from_obis 
import utils.frames as frames 
from utils.parser_functions import get_real_value 

from services.database import get_db_connection
from utils.reader_functions import read_meter_manual
templates = Jinja2Templates(directory="templates")

router = APIRouter()
@router.get("/meter-parameter",response_class=HTMLResponse) # registered meters for now
async def meter_parameter(request: Request, message: str=None): 
    conn = get_db_connection() 
    installed_meters = conn.execute("SELECT *FROM installed_meters").fetchall()  
    conn.close()
    return templates.TemplateResponse("meter_parameter.html", {"request": request, "installed_meters": installed_meters, "connected_clients": connected_clients, "message": message,})
@router.get("/search-meter-parameter", response_class=HTMLResponse)
async def search_meter(request:Request, meter_number: str = ""):  
    query = "SELECT * FROM installed_meters WHERE 1=1"
    params = [] 
    if meter_number: 
        query+= " AND meter_number LIKE ?" 
        params.append(f"%{meter_number}%")  
    conn = get_db_connection()  
    searched_meters = conn.execute(query,params).fetchall() 
    conn.close() 
    return templates.TemplateResponse("meter_parameter.html",{  
        "request": request, 
        "installed_meters": searched_meters,
        "meter_number": meter_number,
        "connected_clients": connected_clients, 
    })
@router.post("/read-meter-parameter")
async def read_Meter_parameter(request: Request):
    data = await request.json()
    selected_meters = data.get("selected_meters")
    selected_parameters = data.get("selected_parameters")
    results = []
    for meter in selected_meters: 
        meter_id = int(meter) 
        print(meter) 
        
        if meter_id not in connected_clients:
            results.append({
                "meter_number": meter, 
                "result": "Error: meter is offline" 
            })
            continue  # skip the rest 
    
        try:
            result_queue = connected_clients[meter_id]['real_time_result'] 
            result_data = {
                "meter_number": meter_id,
                "result": {}
            }
            is_first = True
            connected_clients[meter_id]['pause_event'].clear()
            for parameter in selected_parameters:
                #response = await read_meter_manual(meter_id, meter_parameters[parameter],is_first) 
                await read_meter_manual(meter_id, generate_frame_from_obis(parameter),is_first) 
                response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                is_first = False 
                print(f"response:{response}")   
                data_bytes = response['response'] 
                value =  get_real_value(data_bytes)      
                # value = data_bytes[-4:]
                new_key = obis_name_map.get(parameter, parameter) 
                print (new_key, value) 
                result_data["result"][new_key] = value
            results.append(result_data)
            connected_clients[meter_id]['pause_event'].set() 
        except asyncio.TimeoutError:
            results.append({
                "meter_number": meter,  
                "result": "Error: Timed out waiting for METER response" 
            })

    return JSONResponse(content=results)