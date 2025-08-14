
import asyncio
from services.state import connected_clients
from utils import frames 

async def send_frame_to_meter(meter_id, hex_frame,is_first,timeout):
    if meter_id not in connected_clients:
        return {"error": "Meter not connected"}

    queue = connected_clients[meter_id]['queue']
    response_queue = connected_clients[meter_id]['response_queue']
    result_queue = connected_clients[meter_id]['real_time_result'] 
    if  is_first == True:
        await queue.put(bytes.fromhex(frames.METER_AARQ)) 
        print(f"📤 Sent frame to meter {meter_id}")

    try:
        if is_first == True:
            response = await asyncio.wait_for(response_queue.get(), timeout=timeout)
            print(f"✅ Got response from {meter_id}: {response.hex().upper()}")
        await queue.put(bytes.fromhex(hex_frame)) 
        response = await asyncio.wait_for(response_queue.get(), timeout=timeout)
        print(f"✅ Got response from {meter_id}: {response.hex().upper()}") 
        await result_queue.put({"response": response.hex().upper()})   
        return {"response": response.hex().upper()}
    except asyncio.TimeoutError:
        await queue.put(bytes.fromhex(hex_frame))
        try:  
            response = await asyncio.wait_for(response_queue.get(), timeout=timeout) 
            print(f"✅ Got response from {meter_id}: {response.hex().upper()}")
            await result_queue.put({"response": response.hex().upper()})
            return {"response": response.hex().upper()}
        except asyncio.TimeoutError:
            print(f"❌ Timeout waiting for response from {meter_id}")
            await result_queue.put({"response": "Timeout"})  
            return {"response": "Timeout"}
 
async def read_meter_manual(meter_number,hex_frame,is_first,timeout=30):
    async def task():
        await send_frame_to_meter(meter_number,hex_frame,is_first,timeout=timeout) 
    # Put the task into the meter's queue
    task_queue = connected_clients[meter_number]['task_queue'] 
    await task_queue.put((0, task))

    # asyncio.create_task(queue.put((2, task))) 
