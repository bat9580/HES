import asyncio
import json
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional, List
from datetime import datetime, timedelta
from services.database import get_db_connection
from utils.generator_funcitons import generate_frame_from_obis
from utils.parser_functions import calculate_value_with_ratio_single, get_real_value
from utils.reader_functions import read_meter_manual
from utils.utility_functions import get_meters_by_line, get_ratios
from services.state import connected_clients
from utils.parameters import obis_name_map 

router = APIRouter(prefix="/api", tags=["Readings"])



@router.post("/read-meter-parameter")
async def read_meter_parameter(request: Request):
    try:
        data = await request.json()
        selected_meters = data.get("selected_meters")
        selected_parameters = data.get("selected_parameters")

        if not selected_meters or not selected_parameters:
            raise HTTPException(status_code=400, detail="Missing selected_meters or selected_parameters")

        async def result_generator():
            for meter in selected_meters:
                meter_id = int(meter)
                ratios = get_ratios(str(meter_id))  # transformer coefficient

                if meter_id not in connected_clients:
                    yield json.dumps({
                        "meter_number": meter,
                        "result": "Error: meter is offline"
                    }) + "\n"
                    continue

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
                        await read_meter_manual(meter_id, generate_frame_from_obis(parameter), is_first)
                        response = await asyncio.wait_for(result_queue.get(), timeout=30)
                        is_first = False
                        print(f"response: {response}")

                        data_bytes = response['response']

                        # RS485 device timeout handling
                        if data_bytes == "00000000":
                            yield json.dumps({
                                "meter_number": meter,
                                "result": "Error: Timed out waiting for METER response"
                            }) + "\n"
                            connected_clients[meter_id]['pause_event'].set()
                            break

                        value = get_real_value(data_bytes)
                        value_calculated = calculate_value_with_ratio_single(
                            value, parameter, ratios[0], ratios[1]
                        )
                        print(f"calculated: {value_calculated}")

                        new_key = obis_name_map.get(parameter, parameter)
                        result_data["result"][new_key] = value
                        result_data["result_calculated"][new_key] = value_calculated

                    connected_clients[meter_id]['pause_event'].set()
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
                    yield json.dumps({
                        "meter_number": meter,
                        "result": "Error: Timed out waiting for METER response"
                    }) + "\n"

    except Exception as e:
        print(f"Error in read_meter_parameter: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(result_generator(), media_type="application/json")