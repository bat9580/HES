import asyncio
import sqlite3
from urllib import request
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from services.state import connected_clients 

from services.database import get_db_connection, update_online_status
from utils import frames
from utils.DCU_meter_reader_functions import generate_frame_from_obis_plc_meter, read_plc_meter_manual
from utils.generator_funcitons import time_frame_generate
from utils.parameters import obis_to_column 
from datetime import datetime

from utils.parser_functions import map_meter_data, parse_dlms_frame, process_dlms_data, replace_obis_with_names,calculate_with_transformer_values
from utils.reader_functions import read_meter_manual
from utils.utility_functions import get_ratios, require_permission, template_response 
from utils.storer import store_meter_reading_energy_profile
import json 
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/ondemand-reading",response_class=HTMLResponse) # registered meters for now
async def ondemand_reading(request: Request, message: str=None,user: dict = Depends(require_permission("Remote Maintain"))): 
    conn = get_db_connection()  
    installed_meters = conn.execute("SELECT *FROM installed_meters").fetchall()
    print(installed_meters)  
    conn.close()
    return template_response(request,"ondemand_reading.html", {"request": request, "installed_meters": installed_meters, "connected_clients": connected_clients, "message": message,})


@router.get("/search-meters-ondemand", response_class=HTMLResponse)
async def search_meter(request:Request, meter_number: str = "",line: str = " ",  user: dict = Depends(require_permission("Remote Maintain"))):   
    query = "SELECT * FROM installed_meters WHERE 1=1"
    params = [] 
    if meter_number: 
        query+= " AND meter_number LIKE ?" 
        params.append(f"%{meter_number}%") 
    if line: 
        query+= " AND line LIKE ?" 
        params.append(f"%{line}%")   
    conn = get_db_connection()  
    searched_meters = conn.execute(query,params).fetchall() 
    conn.close() 
    return template_response(request, "ondemand_reading.html",{  
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
      
    start_datetime = datetime.fromisoformat(start_date)
    end_datetime = datetime.fromisoformat(end_date)
    
    if selected_profile == "energy profile": 
        obis_code = ["99.1.0"] 
        first_frame = frames.METER_ENERGY_LOAD_PROFILE_1
        second_frame = frames.METER_ENERGY_LOAD_PROFILE_2_HEADER 
    elif selected_profile == "instant profile":
        obis_code = ["99.2.0"]   
        first_frame = frames.METER_INSTANT_LOAD_PROFILE_1
        second_frame = frames.METER_INSTANT_LOAD_PROFILE_2_HEADER

    time_frame = time_frame_generate(second_frame, start_datetime, end_datetime).lower() 
    print(f"time_frame: {time_frame}") 
    async def result_generator(): 
        for meter in selected_meters: 
            meter_id = int(meter) 
            conn = get_db_connection()
            conn.row_factory = sqlite3.Row
            meter_info = conn.execute(
                "SELECT device_type, DCU_number FROM installed_meters WHERE meter_number = ?",
                (str(meter_id),)
            ).fetchone()
            conn.close()
            if not meter_info:
                yield json.dumps({
                    "meter_number": meter,
                    "result": "Error: Meter not found in database"
                }) + "\n"
                continue
            device_type = meter_info['device_type']
            dcu_number = meter_info["DCU_number"] 
            is_plc_meter = "plc" in device_type.lower() 
            if dcu_number: 
                dcu_number = int(str(dcu_number).strip()) 
            
            if is_plc_meter: 
                print("PLC meter - profile reading not supported via DCU")
                print(f"dcu_number: {dcu_number}") 
                if not dcu_number: 
                    # DCU missing -> treat meter as offline
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter, 
                        "result": "Error: no DCU"  
                    }) + "\n" 
                    continue
                elif dcu_number not in connected_clients:  
                    print(connected_clients)  
                    # DCU offline -> treat meter as offline
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter, 
                        "result": "Error: DCU is offline" 
                    }) + "\n" 
                    continue
                try:
                    result_queue = connected_clients[dcu_number]['real_time_result']  
                    response_queue = connected_clients[dcu_number]['response_queue'] 
                    ratios = get_ratios(str(meter_id))  # transformer coefficient
                    result_data = {
                        "meter_number": meter_id,
                        "result": {}, 
                        "result_calculated": {}
                    }
                    is_first = True 
                    connected_clients[dcu_number]['pause_event'].clear()   
                    #response = await read_meter_manual(meter_id, meter_parameters[parameter],is_first) 
                    while True:
                        try:
                            response_queue.get_nowait() 
                            print("Clearing old response from queue...")
                        except asyncio.QueueEmpty:
                            print("Response queue cleared.")
                            break
                    # await read_meter_manual(meter_id, generate_frame_from_obis(parameter),is_first) 
                    print("frame sent") 

                    await read_plc_meter_manual(dcu_number,meter_id, generate_frame_from_obis_plc_meter(meter_id,obis_code))      
                    response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                    data = response['response'] 
                    if data[:12] == "000100010001":
                       response = await asyncio.wait_for(result_queue.get(), timeout=30)  
                       data = response['response']  
                    conn = get_db_connection()  
                    try:
                        meter_info = conn.execute(
                            "SELECT point_number FROM installed_meters WHERE meter_number = ?",
                            (str(meter_id),)
                        ).fetchone()
                        
                        if meter_info is None:
                            raise ValueError(f"Meter {meter_id} not found in database")
                        
                        point_number = meter_info["point_number"]
                        if point_number is None:
                            raise ValueError(f"Point number not set for meter {meter_id}")
                    finally:
                        conn.close() 
                    time_frame_dcu = (
                        time_frame[:4] +
                        "0050" +
                        f"{point_number:04X}" +
                        time_frame[12:20] +
                        "ce" +
                        time_frame[22:]
                    )
                    print(f"time_frame: {time_frame_dcu}")    
                    print(f"response:{response}")   
                    data_bytes = bytes.fromhex(data) 
                    parsed_data  = parse_dlms_frame(data_bytes)   
                    print("printing definition list") 
                    definition_list = process_dlms_data(parsed_data)  
                    
                    print(definition_list)
                    print("printed definition list")  
                #     result_data["result_calculated"][new_key] = value_calculated
                    await read_plc_meter_manual(dcu_number,meter_id, time_frame_dcu)       
                    response = await asyncio.wait_for(result_queue.get(), timeout=30)
                    data = response['response'] 
                    if data[:12] == "000100010001":
                       response = await asyncio.wait_for(result_queue.get(), timeout=30)  
                       data = response['response']
                    print(f"response:{response}")
                    print(len(data))    
                    is_last_frame = False  
                    data_bytes_profile = ""  
                    if len(data) >= 800: 
                        while is_last_frame == False:
                            if len(data) >= 800: 
                                if len(data) <= 40:
                                    print("unintended value") 
                                    break 
                                data = data.lower()            
                                pos = data.index("c4")   
                                last_block_value = data[pos+6:pos+8]
                                print(f"last_block_value: {last_block_value}")  
                                block_number_value = data[pos+8:pos+16]
                                pos_data = pos + 24   
                                data_bytes = data[pos_data:]
                                data_bytes_profile += data_bytes    
                                # Invoke byte is set in send_frame_to_dcu (0x40–0x4F per DCU).
                                nextframe = (
                                    "00010050"
                                    + f"{point_number:04X}"
                                    + "0007"
                                    + "c002"
                                    + "40"
                                    + block_number_value
                                )
                                await read_plc_meter_manual(dcu_number,meter_id, nextframe)  
                                response = await asyncio.wait_for(result_queue.get(), timeout=30)
                                data = response['response'] 
                                if data[:12] == "000100010001":
                                    response = await asyncio.wait_for(result_queue.get(), timeout=30)  
                                    data = response['response']
                                
                            else: 
                                data = data.lower()            
                                pos = data.index("c4")   
                                last_block_value = data[pos+6:pos+8]
                                print(f"last_block_value: {last_block_value}")  
                                block_number_value = data[pos+8:pos+16] 
                                pos_data = pos + 20
                                data_bytes = data[pos_data:] 
                                data_bytes_profile += data_bytes 
                                data_bytes_profile = "0000000000000000000000" + data_bytes_profile 
                                break    
                    else: 
                        # Data is less than 800 bytes - process it directly
                        data_bytes = bytes.fromhex(data) 
                        parsed_data  = parse_dlms_frame(data_bytes)     
                        data_list = process_dlms_data(parsed_data) 
                        mapped_data = map_meter_data(definition_list, data_list)
                        # Set empty string so we skip the profile processing below
                        data_bytes_profile = ""
                    
                    # Process accumulated profile data (only if we have chunks >= 800 bytes)
                    if data_bytes_profile:
                        print("data_bytes_profile") 
                        print(data_bytes_profile) 
                        data_bytes = bytes.fromhex(data_bytes_profile)  
                        parsed_data  = parse_dlms_frame(data_bytes)     
                        data_list = process_dlms_data(parsed_data) 
                        mapped_data = map_meter_data(definition_list, data_list)
                    
                    # Rename OBIS codes to human-readable names
                    renamed_data = replace_obis_with_names(mapped_data)
                    
                    # Store original data to database
                    store_meter_reading_energy_profile(meter_id, mapped_data)
                    
                    # Calculate with transformer values
                    mapped_data_calculated = calculate_with_transformer_values(mapped_data, ratios[0], ratios[1])
                    renamed_data_calculated = replace_obis_with_names(mapped_data_calculated)
                    
                    # Store calculated data to database
                    store_meter_reading_energy_profile(meter_id, mapped_data_calculated, "energy_profile_readings_calculated")
                    
                    # Format result data for frontend
                    result_data["result"] = renamed_data
                    result_data["result_calculated"] = renamed_data_calculated
                    
                    connected_clients[dcu_number]['pause_event'].set()
                    # Successful real-time PLC read -> meter online
                    update_online_status(meter_id, True)
                    print("done") 
                    yield json.dumps(result_data) + "\n"
                except asyncio.TimeoutError:
                    print("timeout") 
                    while True:
                        try:
                            result_queue.get_nowait()
                            print("Clearing old response...")
                        except asyncio.QueueEmpty:
                            print("Queue is empty now.")
                            break 
                    # Timeout -> meter offline
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter,  
                        "result": "Error: Timed out waiting for METER response" 
                    }) + "\n"
                    continue
            
            else:   # for GPRS meter 
                print("gprs meter")  
                ratios = get_ratios(str(meter_id)) # transformer coefficient      
                if meter_id not in connected_clients:
                    # Not connected -> meter offline
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter, 
                        "result": "Error: meter is offline" 
                    }) + "\n" 
                    continue  # skip the rest 

                try:
                    result_queue = connected_clients[meter_id]['real_time_result'] 
                    response_queue = connected_clients[meter_id]['response_queue']
                    result_data = {
                        "meter_number": meter_id,
                        "result": {}, 
                        "result_calculated": {} 
                    }
                    is_first = True
                    connected_clients[meter_id]['pause_event'].clear() ## busad task zogsooh 
                    
                    # Clear response queue before sending frames
                    while True:
                        try:
                            response_queue.get_nowait() 
                            print("Clearing old response from queue...")
                        except asyncio.QueueEmpty:
                            print("Response queue cleared.")
                            break
                    
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
                    mapped_data = map_meter_data(definition_list, data_list) 
                    renamed_data = replace_obis_with_names(mapped_data) 
                    store_meter_reading_energy_profile(meter,mapped_data)  ## hadgalah 
                    mapped_data_calculated = calculate_with_transformer_values(mapped_data,ratios[0],ratios[1]) 
                    renamed_data_calculated = replace_obis_with_names(mapped_data_calculated)     
                    store_meter_reading_energy_profile(meter,mapped_data_calculated,"energy_profile_readings_calculated")  ## hadgalah  
                    result_data["result"] = renamed_data 
                    result_data["result_calculated"] = renamed_data_calculated 
                    connected_clients[meter_id]['pause_event'].set() 
                    # Successful real-time GPRS read -> meter online
                    update_online_status(meter_id, True)
                    yield json.dumps(result_data) + "\n"  
                except asyncio.TimeoutError:
                    print("timeout") 
                    while True:
                        try:
                            result_queue.get_nowait()
                            print("Clearing old response...")
                        except asyncio.QueueEmpty:
                            print("Queue is empty now.")
                            break 
                    # Timeout -> meter offline
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter,  
                        "result": "Error: Timed out waiting for METER response" 
                    }) + "\n" 
    return StreamingResponse(result_generator(), media_type="application/json")


