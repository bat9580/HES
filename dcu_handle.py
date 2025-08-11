import utils.frames as frames
connected_clients = {}
pending_requests = {} 

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"✅ Connected: {addr}") 
    access_time = 0
    

    try:
        while True:
            data = await reader.read(1024) 
            if not data:
                break
            print(f"📥 From DCU {addr}: {data.hex()}") 
            access_time += 1 
             

            if access_time < 2:  # First connection:  gets DCU name tries 5 times  
                writer.write(bytes.fromhex(frames.AARQ))  
                await writer.drain() 
                print(f"🆔 From server: {frames.AARQ}")    

                data = await reader.read(1024)  
                print(f"📥 From DCU: {data.hex()}")   

                writer.write(bytes.fromhex(frames.GET_DCU_NAME))
                await writer.drain()  
                print(f"🆔 From server: {frames.GET_DCU_NAME}") 

                data = await reader.read(1024)  
                print(f"📥 From DCU: {data.hex()}") 

                DCU_number = data[22:30].decode('utf-8', errors='ignore').strip()
                print(f"DCU number = : {DCU_number}") 

                # Update connected_clients and database  


                # check if the the dcu is registered
                conn = get_db_connection() 
                cursor = conn.cursor() 
                result = cursor.execute("SELECT 1 FROM registered_dcus WHERE dcu_number = ?", (DCU_number,))    
                result = result.fetchone() 
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S') 
                if result is None: 
                    print("adding unregistered dcus") 
                    cursor.execute("""
                    INSERT OR REPLACE INTO unregistered_dcu (dcu_number, ip_address,first_connection,last_connection,access_time)    
                    VALUES (?,?,?,?,?)
                    """, (DCU_number, addr[0], current_time, current_time,access_time))
                    conn.commit()
                    conn.close()  
                  
                connected_clients[DCU_number] = {
                    'addr' : addr,  
                    'access_time': access_time,
                    'queue': asyncio.Queue() 
                } 
                
                
            try: 
                message = connected_clients[DCU_number]['queue'].get_nowait()
                writer.write(bytes.fromhex(frames.AARQ)) 
                await writer.drain()  
                print(f"read command")      
                print(f"🆔 From server: {frames.AARQ}")     
                  
                data = await reader.read(1024)  
                print(f"📥 From DCU: {data.hex()}")     
                writer.write(message) 
                await writer.drain() 
                print(f"📥 From DCU: {message}")  
                data = await reader.read(1024)   
                if DCU_number in pending_requests: 
                    pending_requests[DCU_number].set_result(data) 
                    del pending_requests[DCU_number]
            except asyncio.QueueEmpty:
                writer.write(bytes.fromhex(frames.DCU_ACK))
                await writer.drain() 
                print(f"🆔 From server: {frames.DCU_ACK}")    
            connected_clients[DCU_number]['access_time'] = access_time 
            conn = get_db_connection() 
            cursor = conn.cursor() 
            cursor.execute("""
            UPDATE unregistered_dcu
            SET last_connection = ?, access_time = access_time + 1
            WHERE dcu_number = ?
            """, (current_time, DCU_number)) 
            conn.commit()
            conn.close()
             
            
 
          
    finally:
        print(f"❌ Disconnected: {addr}")
        writer.close()
        await writer.wait_closed()
