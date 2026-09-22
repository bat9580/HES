def get_real_value(data): 
    array_start = 0  
    array_start = data.index("C401")  
    pos = array_start + 8
    print(pos)
    tag = data[pos:pos+2] 
    if tag == "06":  # Uint32 
        real_number = float(int(data[pos+2:], 16))/1000
        return str(real_number) 
    elif tag == "12": # Uint16   
        real_number = float(int(data[pos+2:], 16))/100 
        return str(real_number)  
    elif tag == "05": # int32  
        real_number = float(int(data[pos+2:pos+10], 16))/100
        return str(real_number) 
    elif tag == "14": # int64   
        real_number = float(int(data[pos+2:pos+18], 16))/100000
        return str(real_number) 
    else: 
        real_number = float(int(data[pos+2:], 16))
        return str(real_number)    