
import asyncio
from services.state import connected_clients
from utils import frames,generator_funcitons 
from utils.parser_functions import parse_dlms_frame, process_dlms_data,map_meter_data  
from datetime import datetime 
import pytz

from utils.storer import store_meter_reading_energy_profile, store_meter_reading_instant_profile
tz = pytz.timezone("Asia/Ulaanbaatar") 
 

async def schedule_voltage_read(meter_number):
    async def task():
        await voltageReadTask(meter_number)

    # Put the task into the meter's queue
    queue = connected_clients[meter_number]['task_queue']
    await queue.put((2, task))
    # asyncio.create_task(queue.put((2, task))) 

async def voltageReadTask(meter_number):
    client = connected_clients[meter_number]
    response_queue = client['response_queue'] 
    sender_queue = client['queue']
    print("voltage task started")
    try:
        print("voltage read")
        await sender_queue.put(bytes.fromhex(frames.METER_AARQ))  
        response = await asyncio.wait_for(response_queue.get(),timeout=10) 
        print(response)
        await sender_queue.put(bytes.fromhex(frames.METER_VOLTAGE_PHASE_A))  
        response = await asyncio.wait_for(response_queue.get(),timeout=10)    
        print(response)   
    except Exception as e:
            await sender_queue.put(bytes.fromhex(frames.METER_VOLTAGE_PHASE_A))  
            response = await asyncio.wait_for(response_queue.get(),timeout=10)    
            print(response)

async def schedule_load_profile(meter_number):
    async def task():
        await loadProfileTask(meter_number) 

    # Put the task into the meter's queue
    queue = connected_clients[meter_number]['task_queue']
    await queue.put((1, task)) 



async def loadProfileTask(meter_number):
    client = connected_clients[meter_number]
    response_queue = client['response_queue'] 
    sender_queue = client['queue']
    print("loadProfile task started")
    try:
        print("loadProfile read")
        await sender_queue.put(bytes.fromhex(frames.METER_AARQ)) 
        response = await asyncio.wait_for(response_queue.get(),timeout=10) 
        mapped_data = await get_profile_data_and_parse(frames.METER_ENERGY_LOAD_PROFILE_1,frames.METER_ENERGY_LOAD_PROFILE_2_HEADER, sender_queue, response_queue) 
        print(mapped_data)  
        store_meter_reading_energy_profile(meter_number,mapped_data) 
          
    except Exception as e:

        mapped_data = await get_profile_data_and_parse(frames.METER_ENERGY_LOAD_PROFILE_1,frames.METER_ENERGY_LOAD_PROFILE_2_HEADER, sender_queue, response_queue) 
        print(mapped_data)
        store_meter_reading_energy_profile(meter_number,mapped_data) 
         


async def get_profile_data_and_parse(first_frame, second_frame, sender_queue, response_queue):
    await sender_queue.put(bytes.fromhex(first_frame))       
    response = await asyncio.wait_for(response_queue.get(),timeout=10) 
    parsed_data  = parse_dlms_frame(response)  
    definition_list = process_dlms_data(parsed_data)  
    date_now = datetime.now(tz).replace(minute=0, second=0,microsecond=0).replace(tzinfo=None)     
    time_frame = generator_funcitons.time_frame_generate(second_frame,date_now, date_now)  
    await sender_queue.put(bytes.fromhex(time_frame))     
    response = await asyncio.wait_for(response_queue.get(),timeout=10)   
    parsed_data  = parse_dlms_frame(response) 
    data_list = process_dlms_data(parsed_data) 
    mapped_data = map_meter_data(definition_list, data_list)
    return mapped_data 
         
    


async def schedule_instantanious_profile(meter_number):
    async def task():
        await instantanousProfileTask(meter_number)  
    
    queue = connected_clients[meter_number]['task_queue']
    await queue.put((3, task))

async def instantanousProfileTask(meter_number): 
    client = connected_clients[meter_number]
    response_queue = client['response_queue'] 
    sender_queue = client['queue']
    print("instantanousProfileTask task started")
    try:
        print("instantanousProfile read") 
        await sender_queue.put(bytes.fromhex(frames.METER_AARQ))  
        response = await asyncio.wait_for(response_queue.get(),timeout=10) 
        mapped_data = await get_profile_data_and_parse(frames.METER_INSTANT_LOAD_PROFILE_1,frames.METER_INSTANT_LOAD_PROFILE_2_HEADER, sender_queue, response_queue) 
        print(mapped_data)  
        store_meter_reading_instant_profile(meter_number,mapped_data)
    except Exception as e:
            mapped_data = await get_profile_data_and_parse(frames.METER_INSTANT_LOAD_PROFILE_1,frames.METER_INSTANT_LOAD_PROFILE_2_HEADER, sender_queue, response_queue) 
            print(mapped_data)  
            store_meter_reading_instant_profile(meter_number,mapped_data)
            
async def meter_writer(meter_number):
    client = connected_clients[meter_number]
    queue = client['queue']
    writer = client['writer']

    while True:
        try:
            frame = await queue.get()
            print(f"📤 [meter_writer] Sending to {meter_number}: {frame.hex()}")
            writer.write(frame)
            await writer.drain()
        except Exception as e:
            print(f"⚠️ [meter_writer] Error sending meter {meter_number}: {e}")
            break
            
async def keep_connection(meter_number):
    client = connected_clients[meter_number]
    response_queue = client['keep_connection_queue'] 
    sender_queue = client['queue'] 
    pause_event = client['pause_event']
    while True:        
        print("started listening in keep connection") 
        try:
            response = await asyncio.wait_for(response_queue.get(),timeout=100)    
            if response:
                print(len(response)) 
                if len(response) == 26:
                    reply = response[0:2] + response[4:6] + response[2:4] + response[6:8] + b'\xDA' + response[9:10] + b'\x00\x00' + response[12:]
                    await pause_event.wait() # 
                    await sender_queue.put(reply)  
            else:
                print("timed out") 
                print(connected_clients[meter_number])  
        except Exception as e:
            print("timed out")
            print(f"⚠️ Error reading  from meter {meter_number}: {e}")    



async def task_executor(meter_number):
    queue = connected_clients[meter_number]['task_queue']
    while True:
        priority, task_func = await queue.get()
        try:
            await task_func() 
        except Exception as e:
            print(f"❌ Task failed for {meter_number}: {e}")