import asyncio
import datetime
from services.database import get_db_connection
from services.state import connected_clients
from utils.meter_task_functions import meter_writer
from utils.Microstar_EDAT_frames import SNRM, AARQ  
from utils.DCU_functions import task_executor 


def is_heartbeat_frame_EDAT(data): 
    if len(data) == 47:  
        return True 
    else:
        return False

def get_EDAT_dev_ID(data): 
    return data[35:].decode("ascii") 

def is_EDAT_installed(EDAT_dev_addr): 
    conn = get_db_connection()   
    result = conn.execute(
        "SELECT 1 FROM registered_dcus WHERE dcu_number = ?", (str(EDAT_dev_addr),) 
    ).fetchone()
    conn.close()
    return result is not None


def creat_edat_task(EDAT_dev_addr):
    
    print("beginning task") 
    connected_clients[EDAT_dev_addr]['tasks'] = [
        asyncio.create_task(meter_writer(EDAT_dev_addr)),
        asyncio.create_task(keep_connection(EDAT_dev_addr)),
        asyncio.create_task(task_executor(EDAT_dev_addr))   
    ]

async def exchange_handshake_frame(response_queue, sender_queue):
    try:
        # Send SNRM
        await sender_queue.put(bytes.fromhex(SNRM))

        response = await asyncio.wait_for(response_queue.get(), timeout=20)
        
        if not response:
            raise Exception("No UA response")
        print(f"got response: {response}") 
        # Send AARQ
        await sender_queue.put(bytes.fromhex(AARQ))

        response = await asyncio.wait_for(response_queue.get(), timeout=20)

        if not response:
            raise Exception("No AARE response")
        print(f"got response: {response}") 
        return True

    except Exception as e:
        print("Handshake failed:", e)
        return False  
     

async def keep_connection(EDAT_dev_addr): 
    client = connected_clients[EDAT_dev_addr]
    response_queue = client['response_queue']  
    sender_queue = client['queue'] 
    pause_event = client['pause_event']
    await exchange_handshake_frame(response_queue,sender_queue)     # shaardalgatai eseh ? 
    # while True:        
    #     print("started listening in keep connection") 
    #     try:
    #         sender_queue.put()  
    #         response = await asyncio.wait_for(response_queue.get(),timeout=300)    
    #         if response:
    #             print(len(response)) 
    #             if len(response) == 10: 
    #                 reply = bytes.fromhex('0001001000010000') 
    #                 await pause_event.wait() # 
    #                 await sender_queue.put(reply)  
    #         else:
    #             print("timed out") 
    #             print(connected_clients[DCU_number])  
    #     except Exception as e:
    #         print("timed out")
    #         print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ⚠️ [meter_writer] Error sending DCU {DCU_number}: {e}")    
