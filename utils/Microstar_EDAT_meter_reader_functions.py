

import asyncio
from utils.Microstar_EDAT_generator_functions import build_SNRM_frame, build_AARQ_frame, build_get_request  

from services.state import connected_clients
from utils.DCU_meter_reader_functions import send_frame_to_dcu 
async def read_RS485_with_EDAT_meter_manual(dcu_number,meter_number,HDLC_addr,meter_password,hex_frame,timeout=200):  
    print("read_RS485_with_EDAT_manual") 
    async def task():  
        if dcu_number not in connected_clients:
            return {"error": "Meter not connected"}
        # await send_handshake_frame_to_edat(dcu_number,HDLC_addr,meter_password,timeout) 
        await send_frame_to_dcu(dcu_number,meter_number,hex_frame,timeout=timeout)  
    # Put the task into the meter's queue
    task_queue = connected_clients[dcu_number]['task_queue']  
    await task_queue.put((0, task))  


async def send_handshake_frame_to_edat(dcu_number,HDLC_addr,meter_password,timeout): 
    print("sending_handshake_frame_dcu")  
    if dcu_number not in connected_clients:
        return {"error": "Meter not connected"} 

    queue = connected_clients[dcu_number]['queue']
    response_queue = connected_clients[dcu_number]['response_queue']
    result_queue = connected_clients[dcu_number]['real_time_result'] 
    snrm_frame = build_SNRM_frame(HDLC_addr) 
    aarq_frame = build_AARQ_frame(HDLC_addr, meter_password)   
    print("frame to send to dcu",snrm_frame) 
    await queue.put(bytes.fromhex(snrm_frame))    
    print(f"📤 Sent frame to DCU {dcu_number}") 

    try: 
        response = await asyncio.wait_for(response_queue.get(), timeout=timeout)
        print(f"✅ Got response from {dcu_number}: {response.hex().upper()}")
    except asyncio.TimeoutError: 
        print(f"❌ Timeout waiting for response from {dcu_number}")   
        return    
    print("frame to send to dcu",aarq_frame)
    await queue.put(bytes.fromhex(aarq_frame))   
    print(f"📤 Sent frame to DCU {dcu_number}") 

    try: 
        response = await asyncio.wait_for(response_queue.get(), timeout=timeout)
        print(f"✅ Got response from {dcu_number}: {response.hex().upper()}")
    except asyncio.TimeoutError: 
        print(f"❌ Timeout waiting for response from {dcu_number}")   
        return