import binascii
from datetime import datetime
from collections import defaultdict
from utils.parameters import obis_scaling, obis_name_map, current_obis, voltage_obis, energy_obis 

def parse_dlms_frame(hex_data,header_length=11):  # array eer irsen datag parse hiih 
    # Convert hex string to bytes
    # try:
    #     data = binascii.unhexlify(hex_data)
    # except binascii.Error:
    #     return {"error": "Invalid hex data"}
    data = hex_data 
    if len(data) <= header_length:
        return {"error": "Frame too short - missing payload"}
    if b'\x00\x00\x00\x00\x01\x00\x82\x01' in data:
        header_length = 20 
        print("yes") 
    data = data[header_length:] # tolgoi hesgiig hasch data-g avah 
    result = {
        "wrapper": {
            "length": None,
            "target_address": None,
            "source_address": None
        },
        "pdu": {
            "type": None,
            "invoke_id": None,
            "priority": None,
            "service_class": None,
            "data": []
        }
    }

    # Simplified parsing - in reality you'd need a full DLMS parser
    # This focuses on extracting the array data structures
    
    # Find the start of the array (0x01 is array tag)
    try:
        array_start = data.index(b'\x01')  #\x00\x01 
    except ValueError:
        return {"error": "No array data found in frame"}

    # Get array quantity (next byte)
    array_qty = data[array_start + 1]
    # Initialize position
    pos = array_start + 2  
    for _ in range(array_qty):
        # Each structure starts with 0x02 (structure tag)
        try: 
            if data[pos] != 0x02:
                print("breaking") 
                break
        except: 
            print("error") 
            return result 
            
        struct_qty = data[pos + 1] 
        
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
                        structure.append({"type": "timestamp", "value": timestamp})
                    except ValueError:
                        structure.append({"type": "octet_string", "value": octet_str.hex()})
                elif len(octet_str) == 6: # OctetString (Obis code) 
                    obis_code  = f"{octet_str[2]}.{octet_str[3]}.{octet_str[4]}"
                    structure.append({"type": "obis_code", "value": obis_code})
                else:
                    structure.append({"type": "octet_string", "value": octet_str.hex()})
                    
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
            else:
                # Skip unknown types
                length = data[pos + 1]
                pos += 2 + length
                structure.append({"type": "unknown", "tag": tag})
        result["pdu"]["data"].append(structure)
    
    return result

def process_dlms_data(parsed_data):
    """Process the parsed data into a more readable format"""
    if "error" in parsed_data:
        return parsed_data
    
    processed = []
    
    for structure in parsed_data["pdu"]["data"]:
        item = {}
        for i, field in enumerate(structure):
            if field["type"] == "timestamp":
                item["timestamp"] = field["value"]
            else:
                # Use generic field names if we don't know their meaning
                field_name = f"field_{i}"
                if field["type"] == "octet_string":
                    field_name = "raw_data"
                item[field_name] = field["value"]
        processed.append(item)
    
    return processed
def map_meter_data(definition_list, data_list):
    mapped_readings = []

    # OBIS scaling map: OBIS → scaling divisor
    

    for data_entry in data_list:
        mapped_entry = {'timestamp': data_entry['timestamp']}
        
        for i, obis_def in enumerate(definition_list[1:], start=1):  # skip field_0
            obis_code = obis_def['field_1']
            value_field = f'field_{i}'

            if value_field in data_entry:
                raw_value = data_entry[value_field]
                
                # Apply scale if OBIS code is in the scaling map
                if obis_code in obis_scaling:
                    scaled_value = raw_value / obis_scaling[obis_code]
                else:
                    scaled_value = raw_value  # Keep as-is

                mapped_entry[obis_code] = scaled_value
        mapped_readings.append(mapped_entry)
    return mapped_readings 

def calculate_with_transformer_values(mapped_readings, meter_number):
    CT_ratio = 1000
    VT_ratio = 1000
    for reading in mapped_readings:
        for obis, value in reading.items():
            if obis in current_obis:
                reading[obis] = value * CT_ratio
            elif obis in voltage_obis:
                reading[obis] = value * VT_ratio
            elif obis in energy_obis:
                reading[obis] = value * CT_ratio * VT_ratio
    return mapped_readings 


        
def get_real_value(data): 
    array_start = 0  
    print (type(data))
    array_start = data.index("8100") 
    pos = array_start + 4
    print(pos)
    tag = data[pos:pos+2] 
    if tag == "06":  # Uint32 
        real_number = float(int(data[pos+2:], 16))/1000
        return str(real_number) 
    elif tag == "12": # Uint16   
        real_number = float(int(data[pos+2:], 16))/100 
        return str(real_number)  
    elif tag == "05": # int32  
        real_number = float(int(data[pos+2:], 16))/10000
        return str(real_number) 
    else: 
        real_number = float(int(data[pos+2:], 16))
        return str(real_number)  


def replace_obis_with_names(data_list):
    renamed_data = []
    for entry in data_list:
        new_entry = {}
        for key, value in entry.items():
            # Replace OBIS code with human-readable name if available
            new_key = obis_name_map.get(key, key)  # fallback to original key if not in map
            new_entry[new_key] = value
        renamed_data.append(new_entry)
    return renamed_data  