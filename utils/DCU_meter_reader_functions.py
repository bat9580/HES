import asyncio
from services.state import connected_clients
from utils import frames
from services.database import get_db_connection
from datetime import datetime

from utils.storer import (
    store_meter_reading_instant_profile_from_DCU,
    store_meter_reading_load_profile_from_DCU,
)
from utils.dcu_invoke_id import with_dcu_invoke


async def send_frame_to_dcu(dcu_number,meter_id, hex_frame,timeout):
    print("send_frame_to_dcu") 
    if dcu_number not in connected_clients:
        return {"error": "Meter not connected"}

    queue = connected_clients[dcu_number]['queue']
    response_queue = connected_clients[dcu_number]['response_queue']
    result_queue = connected_clients[dcu_number]['real_time_result'] 
    
    frame_hex = with_dcu_invoke(hex_frame, dcu_number)
    print("frame to send to dcu", frame_hex)
    await queue.put(bytes.fromhex(frame_hex))  
    print(f"📤 Sent frame to DCU {dcu_number}") 

    try: 
        response = await asyncio.wait_for(response_queue.get(), timeout=timeout)
        print(f"✅ Got response from {dcu_number}: {response.hex().upper()}") 
        await result_queue.put({"response": response.hex().upper()})   
        return {"response": response.hex().upper()}
    except asyncio.TimeoutError: 
        print(f"❌ Timeout waiting for response from {meter_id}")
        #await result_queue.put({"response": "Timeout"})  
        return {"response": "Timeout"}   

async def read_plc_meter_manual(dcu_number,meter_number,hex_frame,timeout=30): 
    print("read_plc_meter_manual") 
    async def task():
        print("read_plc_meter_manual")   
        await send_frame_to_dcu(dcu_number,meter_number,hex_frame,timeout=timeout) 
    # Put the task into the meter's queue
    task_queue = connected_clients[dcu_number]['task_queue']  
    await task_queue.put((0, task)) 

def generate_frame_from_obis_plc_meter(meter_id, obis_codes=["1.8.0"]): 
    """
    Build PLC frame for DCU.
    
    Frame format: 00010050 [meter_point] [frame_length] c001 [sequence] 0003 [obis_code] 0200
    
    Args:
        meter_id: Meter number (used to query point_number from database)
        obis_code: OBIS code in hex format (default: "0100010800ff" for 1.8.0)
    
    Returns:
        Hex string of the complete frame
    """
    converted_obis_codes = [] 
    for obis_code in obis_codes: 
        try:
            A, B, C = map(int, obis_code.split("."))
        except ValueError:
            raise ValueError("OBIS code format error A.B.C (e.g., 1.8.0)")
        obis_hex = f"{A:02X}{B:02X}{C:02X}" 
        converted_obis_codes.append("0100" + obis_hex + "FF")  
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
    print(f"converted_obis_codes: {converted_obis_codes}" ) 
    # Constants
    CONSTANT_HEADER = "00010050"
    if len(converted_obis_codes) > 1: 
        CONSTANT_MIDDLE = "c003" # solino 
    else:
        CONSTANT_MIDDLE = "c001" # solino 
    if(obis_codes == ["99.1.0"] or obis_codes == ["99.2.0"]):
        CONSTANT_BEFORE_OBIS = "0007"
        CONSTANT_FOOTER  = "0300" 
    else: 
        CONSTANT_BEFORE_OBIS = "0003"
        CONSTANT_FOOTER  = "0200" 
    # Convert point_number to hex (2 bytes, zero-padded)
    meter_point_hex = f"{int(point_number):04X}"
    
    # Invoke byte is assigned in send_frame_to_dcu (0x40–0x4F per DCU).
    sequence_hex = "40"
    
    # Calculate frame length (in bytes, excluding header and length field itself)
    # The length is from after the length field to the end
    # Convert hex string to bytes and calculate 
    full_obis = "" 
    for obis_code in converted_obis_codes: 
        full_obis = full_obis + CONSTANT_BEFORE_OBIS+ obis_code + CONSTANT_FOOTER
    print(f"full_obis: {full_obis}" )   
    if len(converted_obis_codes) > 1:
        array_qty_hex = f"{len(converted_obis_codes):02X}"
    else:
        array_qty_hex = ""

    frame_after_length_hex = (
        CONSTANT_MIDDLE +
        sequence_hex +
        array_qty_hex + 
        full_obis 
    )
    print(f"frame_after_length_hex: {frame_after_length_hex}" )  
    frame_length_bytes = len(bytes.fromhex(frame_after_length_hex))
    frame_length_hex = f"{frame_length_bytes:04X}"
    
    # Build final frame with correct length
    frame = (
        CONSTANT_HEADER +
        meter_point_hex +
        frame_length_hex +
        CONSTANT_MIDDLE +
        sequence_hex +
        array_qty_hex +  
        full_obis 
    )
    
    return frame.lower()

def generate_relay_frame_plc(meter_id,action): 
    print(action) 
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
    CONSTANT_HEADER = "00010050" 
    meter_point_hex = f"{int(point_number):04X}" 
    CONSTANT_MIDDLE = "c001" 
    sequence_hex = "41"
    class_id_val = "0046" 
    OBIS = "000060030aff" 
    if action == "connect": 
        CONSTANT_FOOTER = "02010f00" 
        CONSTANT_MIDDLE = "c301" 
    elif action == "disconnect": 
        CONSTANT_FOOTER = "01010f00"
        CONSTANT_MIDDLE = "c301"
    elif action == "relay_status": 
        CONSTANT_FOOTER = "0200"  
        CONSTANT_MIDDLE = "c001" 

    frame_after_length_hex = (
        CONSTANT_MIDDLE +
        sequence_hex +
        class_id_val +
        OBIS + 
        CONSTANT_FOOTER 
    ) 
    frame_length_bytes = len(bytes.fromhex(frame_after_length_hex))
    frame_length_hex = f"{frame_length_bytes:04X}" 

    frame = (
        CONSTANT_HEADER +
        meter_point_hex +
        frame_length_hex +
        CONSTANT_MIDDLE +
        sequence_hex +
        class_id_val +
        OBIS + 
        CONSTANT_FOOTER 
    )
    return frame.lower() 

def parse_dlms_profile_frame_from_DCU(hex_data,header_length = 19):
    data = hex_data 
    
    data = data[header_length:] # tolgoi hesgiig hasch data-g avah 
    print(data.hex()) 
    result = {
        "pdu": {
            "date": None,
            "meter_number": None,
            "data": []
        }
    }

    pos = 0

        # Each structure starts with 0x02 (structure tag)
    try: 
        if data[pos] != 0x02:
            print("stucture not found")  
    except: 
        print("error") 
        return result 
        
    struct_qty = data[pos + 1] 
    print(struct_qty) 
    pos += 2
    structure = []
    for _ in range(struct_qty):
        # Get the tag for each element
        tag = data[pos]
        
        
        # Handle different data types
        if tag == 0x09:  # OctetString (timestamp)
            length = data[pos + 1]
            octet_str = data[pos + 2: pos + 2 + length]
            pos += 2 + length
            
            # Try to parse as timestamp (12-byte format)
            if len(octet_str) == 12:
                year = int.from_bytes(octet_str[0:2], 'big')
                month = octet_str[2]
                day = octet_str[3]
                hour = octet_str[5]  # Skip weekday (octet_str[4])
                minute = octet_str[6]
                second = octet_str[7]
                
                try:
                    timestamp = datetime(year, month, day, hour, minute, second).isoformat()
                    result["pdu"]["date"] =  timestamp
                except ValueError:
                    structure.append({"type": "octet_string", "value": octet_str.hex()})
            elif len(octet_str) == 6: # OctetString (Obis code) 
                obis_code  = f"{octet_str[2]}.{octet_str[3]}.{octet_str[4]}"
                structure.append({"type": "obis_code", "value": obis_code})
            else:
                result["pdu"]["meter_number"] = octet_str.decode("ascii")
                
        elif tag == 0x06:  # UInt32
            value = int.from_bytes(data[pos + 1:pos + 5], 'big')
            pos += 5
            structure.append({"type": "uint32", "value": value})
            
        elif tag == 0x05:  # UInt8
            value = data[pos + 1]
            pos += 2
            structure.append({"type": "uint8", "value": value})
        elif tag == 0x11:  # UInt8
            value = data[pos + 1]
            pos += 2
            structure.append({"type": "uint8", "value": value})
        elif tag == 0x12:  # UInt8
            value = int.from_bytes(data[pos + 1:pos + 3], 'big') 
            pos += 3 
            structure.append({"type": "uint16", "value": value}) 
        elif tag == 0x0F:  # Int8 
            value = data[pos + 1] 
            pos += 2
            structure.append({"type": "int8", "value": value}) 
        elif tag == 0x00: 
            pos += 1 
            structure.append({"type": "Unknown", "value": None}) 
        else:
            # Skip unknown types
            length = data[pos + 1]
            pos += 2 + length
            structure.append({"type": "unknown", "tag": tag})
    result["pdu"]["data"].append(structure)
    print(result) 
    return result
    
def extract_and_save_profile_data(hex_frame):
    obis_code = hex_frame[12:18].hex().lower()
    parsed_data = parse_dlms_profile_frame_from_DCU(hex_frame)
    if obis_code == "0100630233ff":
        print("instantaneous_profile_readings")
        store_meter_reading_instant_profile_from_DCU(parsed_data)
    elif obis_code == "0100630232ff":
        print("energy_profile_readings / load profile")
        store_meter_reading_load_profile_from_DCU(parsed_data)
    else:
        print("daily billing")

    print(parsed_data)
        
