

import asyncio
import datetime
from services.state import connected_clients


async def keep_connection(DCU_number):
    client = connected_clients[DCU_number]
    response_queue = client['keep_connection_queue'] 
    sender_queue = client['queue'] 
    pause_event = client['pause_event']
    while True:        
        print("started listening in keep connection") 
        try:
            response = await asyncio.wait_for(response_queue.get(),timeout=300)    
            if response:
                print(len(response)) 
                if len(response) == 10: 
                    reply = bytes.fromhex('0001001000010000') 
                    await pause_event.wait() # 
                    await sender_queue.put(reply)  
            else:
                print("timed out") 
                print(connected_clients[DCU_number])  
        except Exception as e:
            print("timed out")
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ⚠️ [meter_writer] Error sending DCU {DCU_number}: {e}")    
