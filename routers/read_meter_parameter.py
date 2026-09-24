import asyncio
import sqlite3
import time
from urllib import request
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from services.state import connected_clients, pending_requests
from utils.Microstar_EDAT_generator_functions import build_get_request
from utils.Microstar_EDAT_meter_reader_functions import read_RS485_with_EDAT_meter_manual, send_handshake_frame_to_edat
from utils.parameters import obis_name_map 
from utils.generator_funcitons import generate_frame_from_obis 
import utils.frames as frames 
from utils.parser_functions import get_real_value,calculate_value_with_ratio_single, get_real_value_plc               
from utils.utility_functions import get_ratios, require_permission, template_response  
from utils.DCU_meter_reader_functions import read_plc_meter_manual, generate_frame_from_obis_plc_meter 
from services.database import get_db_connection, update_online_status
from utils.reader_functions import read_meter_manual
from fastapi.responses import StreamingResponse 
import utils.Microstar_EDAT_parser_functions as Microstar_EDAT_parser_functions   
from api_endpoints.Lorawan_api import send_downlink, incoming_responses 
from utils.esp32_gateway import enqueue_obis_read, uses_esp32
import json 
templates = Jinja2Templates(directory="templates")

router = APIRouter()
@router.get("/meter-parameter",response_class=HTMLResponse) # registered meters for now
async def meter_parameter(request: Request, message: str=None, user: dict = Depends(require_permission("Remote Maintain"))): 
    conn = get_db_connection() 
    installed_meters = conn.execute("SELECT *FROM installed_meters").fetchall()  
    conn.close()
    return template_response(request,"meter_parameter.html", {"request": request, "installed_meters": installed_meters, "connected_clients": connected_clients, "message": message,})
@router.get("/search-meter-parameter", response_class=HTMLResponse)
async def search_meter(request:Request, meter_number: str = "",line: str= "", user: dict = Depends(require_permission("Remote Maintain"))):  
    print(line) 
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
    return template_response(request,"meter_parameter.html",{  
        "request": request, 
        "installed_meters": searched_meters,
        "meter_number": meter_number,
        "line": line,
        "connected_clients": connected_clients, 
    })

@router.post("/read-meter-parameter")
async def read_Meter_parameter(request: Request):
    
    data = await request.json()
    selected_meters = data.get("selected_meters")
    print(selected_meters) 
    selected_parameters = data.get("selected_parameters")
    print("selected parameters: ") 
    print(selected_parameters) 
    async def result_generator(): 
        for meter in selected_meters: 
            print(type(meter))  
            meter_id = int(meter)  
            conn = get_db_connection()
            conn.row_factory = sqlite3.Row
            meter_info = conn.execute(
                "SELECT device_type, DCU_number, com_address, type, password FROM installed_meters WHERE meter_number = ?",
                (meter,)
            ).fetchone()
            meter_info_registered = conn.execute(
                "SELECT device_type, com_address FROM registered_meters WHERE meter_number = ?", 
                (meter,)
            ).fetchone() 
            ddsd285_meter = bool(meter_info) and uses_esp32(meter_info["device_type"], meter_info["type"])
            if not ddsd285_meter:
                HDLC_addr =  meter_info_registered['com_address']  
                print("HDLC_addr:")  
                print(HDLC_addr)   
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
                dcu_number = str(dcu_number).strip()  
            is_plc_meter = "plc" in device_type.lower() 
            is_lorawan_meter = "lorawan" in device_type.lower()  
            is_rs485_with_edat = "rs485 with edat" in device_type.lower() 
            if ddsd285_meter:
                print(f"Processing DDSD285_2018 meter via ESP32: {meter}")
                password = str(meter_info["password"] or "").strip().replace(" ", "") or "00000000"
                bus_address = str(meter).strip()
                if not dcu_number:
                    update_online_status(meter, False)
                    yield json.dumps({
                        "meter_number": meter,
                        "result": "Error: no ESP32"
                    }) + "\n"
                    continue
                elif dcu_number not in connected_clients:
                    update_online_status(meter, False)
                    yield json.dumps({
                        "meter_number": meter,
                        "result": "Error: ESP32 is offline"
                    }) + "\n"
                    continue
                try:
                    result_queue = connected_clients[dcu_number]["real_time_result"]
                    ratios = get_ratios(str(meter_id)) or (1, 1)
                    result_data = {
                        "meter_number": meter,
                        "result": {},
                        "result_calculated": {}
                    }
                    while True:
                        try:
                            result_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    for parameter in selected_parameters:
                        queued = await enqueue_obis_read(dcu_number, bus_address, parameter, password)
                        if queued and queued.get("error"):
                            update_online_status(meter_id, False)
                            yield json.dumps({
                                "meter_number": meter,
                                "result": f"Error: {queued['error']}"
                            }) + "\n"
                            break
                        response = await asyncio.wait_for(result_queue.get(), timeout=50)
                        print(f"ESP32 response: {response}")
                        if response.get("error"):
                            update_online_status(meter_id, False)
                            yield json.dumps({
                                "meter_number": meter,
                                "result": f"Error: {response['error']}"
                            }) + "\n"
                            break
                        value = response.get("value")
                        new_key = obis_name_map.get(parameter, parameter)
                        result_data["result"][new_key] = value
                        try:
                            result_data["result_calculated"][new_key] = calculate_value_with_ratio_single(
                                value, parameter, ratios[0], ratios[1]
                            )
                        except (TypeError, ValueError):
                            result_data["result_calculated"][new_key] = value
                    else:
                        update_online_status(meter_id, True)
                        yield json.dumps(result_data) + "\n"
                except asyncio.TimeoutError:
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter,
                        "result": "Error: Timed out waiting for METER response"
                    }) + "\n"
            elif is_plc_meter:
                dcu_number = int(dcu_number)    
                print("PLC meter") 
                print(f"dcu_number: {dcu_number}") 
                if not dcu_number: 
                    # Missing DCU -> mark meter offline
                    update_online_status(meter, False) 
                    yield json.dumps({
                        "meter_number": meter, 
                        "result": "Error: no DCU"  
                    }) + "\n" 
                    continue
                elif dcu_number not in connected_clients:  
                    print(type(dcu_number))  
                    print(connected_clients)  
                    # DCU offline -> mark meter offline
                    update_online_status(meter, False) 
                    print("DCU is offline sdf")  
                    yield json.dumps({
                        "meter_number": meter, 
                        "result": "Error: DCU is offline" 
                    }) + "\n" 
                    continue
                try:
                    result_queue = connected_clients[dcu_number]['real_time_result']  
                    response_queue = connected_clients[dcu_number]['response_queue'] 
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
                    await read_plc_meter_manual(dcu_number,meter_id, generate_frame_from_obis_plc_meter(meter_id,selected_parameters))    
                    # read_plc_meter_manual()
                    print("waiting for response") 
                    response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                    is_first = False 
                    print(f"response:{response}")   
                    data_bytes = response['response'] 
                    
                    #RS485 aar holbogdson tooluurt zoriulsan heseg
                    if data_bytes == "00000000": 
                        # Timed out / no data -> offline
                        update_online_status(meter_id, False)
                        yield json.dumps({ 
                            "meter_number": meter,  
                            "result": "Error: Timed out waiting for METER response" 
                        }) + "\n"
                        break  # stop reading more parameters for this meter
                    #############################

                    connected_clients[dcu_number]['pause_event'].set() 
                    value =  get_real_value_plc(data_bytes) 
                    print(f"value: {value}") 
                #     value_calculated = calculate_value_with_ratio_single(value,parameter,ratios[0],ratios[1]) 
                #     print(f"calculated:  {value_calculated}")
                #     # value = data_bytes[-4:]
                    for idx, parameter in enumerate(selected_parameters):
                            if idx < len(value):
                                new_key = obis_name_map.get(parameter, parameter)
                                print(f"{new_key}: {value[idx]}")
                                result_data["result"][new_key] = value[idx]
                #     result_data["result_calculated"][new_key] = value_calculated
                    
                    # connected_clients[meter_id]['pause_event'].set()
                    # Successful PLC parameter read -> online
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
                    # Timeout -> offline
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter,  
                        "result": "Error: Timed out waiting for METER response" 
                    }) + "\n"
            
            elif is_rs485_with_edat: 
                print(f"Processing rs485 with EDAT meter: {meter}") 
                print(f"dcu_number: {dcu_number}") 
                if not dcu_number: 
                    # Missing DCU -> mark meter offline
                    update_online_status(meter, False)
                    yield json.dumps({
                        "meter_number": meter, 
                        "result": "Error: no DCU"  
                    }) + "\n" 
                    continue
                elif dcu_number not in connected_clients: 
                    # DCU offline -> mark meter offline
                    update_online_status(meter, False) 
                    yield json.dumps({
                        "meter_number": meter, 
                        "result": "Error: DCU is offline" 
                    }) + "\n" 
                    continue
                try:
                    result_queue = connected_clients[dcu_number]['real_time_result']  
                    response_queue = connected_clients[dcu_number]['response_queue'] 
                    result_data = {
                        "meter_number": meter, 
                        "result": {}, 
                        "result_calculated": {}
                    }
                    
                    is_first = True 
                    connected_clients[dcu_number]['pause_event'].clear() 
                    HDLC_addr = format(int(meter_info_registered['com_address']), 'X')     
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
                    await send_handshake_frame_to_edat(dcu_number,HDLC_addr,"47190205",100)                     
                    for parameter in selected_parameters:
                        #response = await read_meter_manual(meter_id, meter_parameters[parameter],is_first) 
                        obiscode = "1.1." + parameter + ".255" 
                        await read_RS485_with_EDAT_meter_manual(dcu_number,meter_id,HDLC_addr,"47190205",build_get_request(HDLC_addr,obiscode))  
                        response = await asyncio.wait_for(result_queue.get(), timeout=30) 
                        print(f"response:{response}")   
                        data_bytes = response['response']
                        value =  Microstar_EDAT_parser_functions.get_real_value(data_bytes) 
                        
                        # value_calculated = calculate_value_with_ratio_single(value,parameter,ratios[0],ratios[1]) 
                        # print(f"calculated:  {value_calculated}")
                        # value = data_bytes[-4:]
                        new_key = obis_name_map.get(parameter, parameter)  
                        print (new_key, value) 
                        result_data["result"][new_key] = value
                        result_data["result_calculated"][new_key] = value  
                    update_online_status(meter_id, True)
                    print("returning result") 
                    yield json.dumps(result_data) + "\n"
                    print("returned results" ) 
                    print(result_data) 
                         
                except asyncio.TimeoutError:
                    print("timeout") 
                    while True:
                        try:
                            result_queue.get_nowait()
                            print("Clearing old response...")
                        except asyncio.QueueEmpty:
                            print("Queue is empty now.")
                            break 
                    # Timeout -> offline
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter,  
                        "result": "Error: Timed out waiting for METER response" 
                    }) + "\n"
                finally: 
                    connected_clients[dcu_number]['pause_event'].set() 
            elif is_lorawan_meter: 
                print(f"Processing LoRaWAN meter: {meter}")
                dev_eui = meter_info['com_address'] 
                
                # 1. Clear any stale data from previous attempts
                incoming_responses.pop(dev_eui, None)
                
                # 2. Send the command to ChirpStack
                send_downlink(dev_eui, "08FF", 1)  

                # 3. NOW WAIT for the Webhook to fill 'incoming_responses'
                timeout = 120 # seconds
                start_time = time.time()
                final_result = None

                while time.time() - start_time < timeout:
                    if dev_eui in incoming_responses:
                        # The Webhook caught the response!
                        final_result = incoming_responses.pop(dev_eui)
                        break
                    
                    # Give the CPU a tiny break
                    await asyncio.sleep(0.5)

                # 4. Report the actual outcome
                if final_result:
                    print(f"Success! Device {dev_eui} replied: {final_result}")
                    update_online_status(meter_id, True)
                    yield json.dumps({
                        "meter_number": meter,  
                        "status": "Success",
                        "result": final_result
                    }) + "\n"
                else:
                    print(f"Timeout! Device {dev_eui} did not reply within {timeout}s")
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter,  
                        "status": "Error",
                        "result": "Timeout waiting for device response" 
                    }) + "\n"
                
                continue
            else:   # for GRPS meter 
                print("gprs meter")  
                ratios = get_ratios(str(meter_id)) # transformer coefficient      
                if meter_id not in connected_clients:
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter, 
                        "result": "Error: meter is offline" 
                    }) + "\n" 
                    continue  # skip the rest 

                try:
                    result_queue = connected_clients[meter_id]['real_time_result'] 
                    result_data = {
                        "meter_number": meter_id,
                        "result": {}, 
                        "result_calculated": {}
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
                        
                        #RS485 aar holbogdson tooluurt zoriulsan heseg
                        if data_bytes == "00000000": 
                            update_online_status(meter_id, False)
                            yield json.dumps({ 
                                "meter_number": meter,  
                                "result": "Error: Timed out waiting for METER response" 
                            }) + "\n"
                            connected_clients[meter_id]['pause_event'].set()
                            break  # stop reading more parameters for this meter
                        #############################


                        value =  get_real_value(data_bytes)
                        
                        value_calculated = calculate_value_with_ratio_single(value,parameter,ratios[0],ratios[1]) 
                        print(f"calculated:  {value_calculated}")
                        # value = data_bytes[-4:]
                        new_key = obis_name_map.get(parameter, parameter) 
                        print (new_key, value) 
                        result_data["result"][new_key] = value
                        result_data["result_calculated"][new_key] = value_calculated
                    
                    connected_clients[meter_id]['pause_event'].set()
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
                    update_online_status(meter_id, False)
                    yield json.dumps({
                        "meter_number": meter,  
                        "result": "Error: Timed out waiting for METER response" 
                    }) + "\n" 
    return StreamingResponse(result_generator(), media_type="application/json") 



