import asyncio
import sqlite3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.state import connected_clients 

from services.database import get_db_connection
from utils import frames
from utils.generator_funcitons import time_frame_generate
from utils.parameters import obis_to_column 
from datetime import datetime

from utils.parser_functions import map_meter_data, parse_dlms_frame, process_dlms_data, replace_obis_with_names,calculate_with_transformer_values
from utils.reader_functions import read_meter_manual
from utils.utility_functions import get_ratios 
from utils.storer import store_meter_reading_energy_profile 
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/ondemand-reading",response_class=HTMLResponse) # registered meters for now
async def ondemand_reading(request: Request, message: str=None): 
    conn = get_db_connection()  
    installed_meters = conn.execute("SELECT *FROM installed_meters").fetchall()
    print(installed_meters)  
    conn.close()
    return templates.TemplateResponse("ondemand_reading.html", {"request": request, "installed_meters": installed_meters, "connected_clients": connected_clients, "message": message,})
@router.get("/search-meters-ondemand", response_class=HTMLResponse)
async def search_meter(request:Request, meter_number: str = ""):  
    query = "SELECT * FROM installed_meters WHERE 1=1"
    params = [] 
    if meter_number: 
        query+= " AND meter_number LIKE ?" 
        params.append(f"%{meter_number}%")  
    conn = get_db_connection()  
    searched_meters = conn.execute(query,params).fetchall() 
    conn.close() 
    print(meter_number) 
    return templates.TemplateResponse("ondemand_reading.html",{  
        "request": request, 
        "installed_meters": searched_meters,
        "meter_number": meter_number,
        "connected_clients": connected_clients, 
    })
@router.post("/read-meter-ondemand-profile") 
async def read_meter_ondemand_profile(request: Request):
    data = await request.json()
    selected_meters = data.get("selected_meters")
    selected_profile = data.get("selected_profile") 
    start_date = data.get("start_date") 
    end_date = data.get("end_date")  
      
    results = []
    start_datetime = datetime.fromisoformat(start_date)
    end_datetime = datetime.fromisoformat(end_date)
    
    if selected_profile == "energy profile": 
        first_frame = frames.METER_ENERGY_LOAD_PROFILE_1
        second_frame = frames.METER_ENERGY_LOAD_PROFILE_2_HEADER 
    elif selected_profile == "instant profile":  
        first_frame = frames.METER_INSTANT_LOAD_PROFILE_1
        second_frame = frames.METER_INSTANT_LOAD_PROFILE_2_HEADER


    time_frame = time_frame_generate(second_frame, start_datetime, end_datetime)   

    for meter in selected_meters: 
        meter_id = int(meter) 
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
                "result": {}, 
                "result_calculated": {} 
            }
            is_first = True
            ratios = get_ratios(str(meter_id))   
            connected_clients[meter_id]['pause_event'].clear() ## busad task zogsooh 
            
            await read_meter_manual(meter_id, first_frame, is_first)     
            response = await asyncio.wait_for(result_queue.get(), timeout=30) 
            print(f"response:{response}") 
            data = response['response'] 
            data_bytes = bytes.fromhex(data) 
            parsed_data  = parse_dlms_frame(data_bytes)   
            definition_list = process_dlms_data(parsed_data)  
            print(definition_list) 
            is_first = False  

            await read_meter_manual(meter_id, time_frame,is_first) 
            response = await asyncio.wait_for(result_queue.get(), timeout=30) 
            print(f"response:{response}") 
            data = response['response'] 
            data_bytes = bytes.fromhex(data) 
            parsed_data  = parse_dlms_frame(data_bytes)     
            data_list = process_dlms_data(parsed_data) 
            print(data_list) 
            mapped_data = map_meter_data(definition_list, data_list) 
            renamed_data = replace_obis_with_names(mapped_data) 
            print(renamed_data)  
            mapped_data_calculated = calculate_with_transformer_values(mapped_data,ratios[0],ratios[1]) 
            renamed_data_calculated = replace_obis_with_names(mapped_data_calculated)    
            store_meter_reading_energy_profile(meter,mapped_data)  ## hadgalah 
            store_meter_reading_energy_profile(meter,mapped_data_calculated,"energy_profile_readings_calculated")  ## hadgalah  
            result_data["result"] = renamed_data 
            result_data["result_calculated"] = renamed_data_calculated 
            results.append(result_data)  
            connected_clients[meter_id]['pause_event'].set() 
        except asyncio.TimeoutError:
            results.append({
                "meter_number": meter,  
                "result": "Error: Timed out waiting for METER response" 
            })
    return JSONResponse(content=results)


