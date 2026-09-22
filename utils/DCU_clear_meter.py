def build_dcu_meter_clear_frame(str1, octet1, str2, str3,point_number):
    """
    Build DLMS SetRequestNormal frame matching the provided 'correct' example.
    Variable fields:
      - str1 : a regular ASCII string (e.g. "25701824796")
      - octet1: hex string of octets (e.g. "025701824796")  -- pass without 0x, spaces allowed
      - str2 : ASCII string (e.g. "UBEDNLAB")
      - str3 : ASCII string (e.g. "UBEDNLAB")
    Returns: hex string (lowercase) of the complete DLMS frame.
    """

    # helpers
    def to_ascii_hex(s: str) -> str:
        return s.encode("ascii").hex()

    def dlms_string(s: str) -> str:
        # DLMS string = tag 0x0A, 1-byte length, ASCII bytes
        if s is None:
            s = ""
        b = to_ascii_hex(s)
        length = len(s)
        return f"0a{length:02x}{b}"

    def dlms_octet(hexstr: str) -> str:
        # clean input (allow spaces/dashes)
        h = hexstr.replace(" ", "").replace("-", "").lower()
        if len(h) % 2 != 0:
            raise ValueError("octet hex string must have even length")
        length = len(h) // 2
        return f"09{length:02x}{h}"

    # --- Constants taken from your 'correct' frame ---
    header = "000100500001" 
    pdu_tag = "c101" 
    obis_code = "00010000803206ff" 
    before_point_number = "02000101021612"  
    after_point_nubmer = "1100" 
    prefix = (
        "000100500001"    # wrapper + len etc.
        "c101"                # PDU tag (Cosem SetRequest)
        "47"                  # variable
        "00010000803206ff"  # AttributeDescriptor (class id + instance + attribute id)
        "02000101021612 0002 1100"
        "1100"  # empty string  
        # up to before first string
    )

    between_str1_and_octet = ""  # nothing: we place str1 directly after prefix above
    # But to follow correct frame exactly, prefix already ends with "1100" then next is string tag for str1.

    after_octet = (
        # constants that appear after the octet string in the correct frame
        "110211001100110111111100"
        # followed by string2, string3, empty strings...
    )

    empty_strings_4 = "0a00" * 4

    suffix = "11020600004b001108110011010a00"

    # build variable parts
    v_str1 = dlms_string(str1)
    v_oct = dlms_octet(octet1)
    v_str2 = dlms_string(str2)
    v_str3 = dlms_string(str3)
    point_number_str = f"{point_number:04x}" 
    preframe = pdu_tag + "4b" + obis_code + before_point_number + point_number_str + after_point_nubmer + v_str1 + v_oct + after_octet + v_str2 + v_str3 + empty_strings_4 + suffix 
    length = f"{len(preframe)//2:04x}"  
    frame = header + length + preframe
    return frame.lower()


def build_clear_frame_for_one_meter(str1, octet1, str2, str3, point_number):
    """
    Build download frame for one meter.
    """
    # helpers
    def to_ascii_hex(s: str) -> str:
        return s.encode("ascii").hex()

    def dlms_string(s: str) -> str:
        if s is None:
            s = ""
        b = to_ascii_hex(s)
        length = len(s)
        return f"0a{length:02x}{b}"

    def dlms_octet(hexstr: str) -> str:
        h = hexstr.replace(" ", "").replace("-", "").lower()
        if len(h) % 2 != 0:
            raise ValueError("octet hex string must have even length")
        length = len(h) // 2
        if length == 4: 
            length = 6 
            h = "0000" + h 
        return f"09{length:02x}{h}"
    def dlms_visible_string_from_ascii_hex(s: str) -> str:
        """
        Example:
        input  = "00000000"
        output = 0a1033303330333033303330333033303330
        """
        # Step 1: ASCII -> hex ( "00000000" -> "3030303030303030" )
        ascii_hex = s.encode("ascii").hex()
    
        # Step 2: treat that hex as ASCII characters
        payload = ascii_hex.encode("ascii").hex()
    
        # Step 3: DLMS VisibleString
        length = len(payload) // 2
        return f"0a{length:02x}{payload}"

    # constants
    before_point_number = "021612"
    after_point_number = "1102"
    after_octet = "110211001100110111111100"
    empty_strings_4 = "0a00" * 4
    suffix = "11020600004b001108110011010a00"

    # build variable parts
    v_str1 = dlms_string(str1)
    v_oct = dlms_octet(octet1)
    v_str2 = dlms_visible_string_from_ascii_hex(str2)
    v_str3 = dlms_visible_string_from_ascii_hex(str3) 
    print(v_str2) 
    print(v_str3) 
    point_number_str = f"{point_number:04x}"

    preframe = (
        before_point_number
        + point_number_str
        + after_point_number
        + v_str1
        + v_oct
        + after_octet
        + v_str2
        + v_str3
        + empty_strings_4
        + suffix
    )

    return preframe.lower()


def build_dcu_clear_data_frame(meter_data):
    """
    Build download data frames for multiple meters.
    Returns list of frame hex strings (without headers).
    """
    frames = []
    for meter in meter_data:
        meter_number = meter["meter_number"]
        point_number = meter["point_number"]
        password = "00000000"
        octet_meter = meter_number if len(meter_number) % 2 == 0 else "0" + meter_number

        frame = build_clear_frame_for_one_meter(
            meter_number,
            octet_meter,
            password,
            password,
            point_number
        )
        frames.append(frame)

    return frames


def build_dcu_clear_frame(meters):
    """
    Build complete DCU download frame(s) for multiple meters.
    If the data is too large (>466 bytes), splits into multiple frames.
    Returns list of complete frame hex strings ready to send.
    """
    header = "000100500001"
    pri_service_first = "c102"
    pri_service_next = "c103"
    inv_pri_first = "49"
    inv_pri_next = inv_pri_first
    class_id = "0001"
    obis_code = "0000803206ff"
    att_value = "02"
    last_block_val = "00"
    data_length_descriptor = "81"
    array_length_indicator = "01"
    frames_data = build_dcu_clear_data_frame(meters)
    full_frame = "".join(frames_data)
    frame_length = len(full_frame)
    array_length = len(frames_data)

    result_frames = [] 
    print(len(meters)) 
    if len(meters) == 1:
        print("only one meter")
        array_qty = "01" 
        pdu_body = (
            "c101"
            + inv_pri_first
            + class_id
            + obis_code
            + att_value
            + "0001" 
            + array_qty  
            + full_frame
        )

        # length in bytes
        pdu_length = len(pdu_body) // 2 

        print(pdu_length)
        print(full_frame)

        frame_to_send = (
            header
            + f"{pdu_length:04x}"
            + pdu_body
        )

        result_frames.append(frame_to_send.lower())
        return result_frames
    elif len(meters) == 2:
        print("only one meter")
        array_qty = "02"   
        pdu_body = (
            "c101"
            + inv_pri_first
            + class_id
            + obis_code
            + att_value
            + "0001" 
            + array_qty
            + full_frame
        )

        # length in bytes
        pdu_length = len(pdu_body) // 2 

        print(pdu_length)
        print(full_frame)

        frame_to_send = (
            header
            + f"{pdu_length:04x}"
            + pdu_body
        )

        result_frames.append(frame_to_send.lower())
        return result_frames 
        

    if len(full_frame) > 466:  # 233 bytes = 466 hex chars
        frame_number = 1
        frame_end_index = 0
        is_first = True

        while frame_length > 0:
            frame_start_index = frame_end_index
            frame_number_str = f"{frame_number:08x}"
            frame_number = frame_number + 1

            if is_first:
                pdu_header = (
                    header + "00ff" + pri_service_first + inv_pri_first + class_id +
                    obis_code + att_value + "00" + last_block_val + frame_number_str
                )
                data_length = 526 - len(pdu_header) - 8
                frame_end_index = frame_start_index + data_length

                frame_to_send = (
                    pdu_header + data_length_descriptor + f"{data_length//2 + 2:02x}" +
                    array_length_indicator + f"{array_length:02x}" +
                    full_frame[frame_start_index:frame_end_index]
                )
                result_frames.append(frame_to_send.lower())
                is_first = False
            else:
                val = int(inv_pri_next, 16) + 1
                if val > 0x4F:
                    val = 0x40
                inv_pri_next = f"{val:02x}"

                if len(full_frame) > frame_start_index + 245 * 2:
                    frame_end_index = frame_start_index + 245 * 2
                else:
                    frame_end_index = len(full_frame)

                data_frame = full_frame[frame_start_index:frame_end_index]
                data_length = len(data_frame)

                if data_length < 466:
                    last_block_val = "01"

                pdu_length = len(
                    header + pri_service_next + inv_pri_next + last_block_val +
                    frame_number_str + data_length_descriptor + f"{data_length//2:02x}" + data_frame
                )

                pdu_header = (
                    header + f"{pdu_length//2-6:04x}" + pri_service_next + inv_pri_next +
                    last_block_val + frame_number_str + data_length_descriptor +
                    f"{data_length//2:02x}" + data_frame
                )

                result_frames.append(pdu_header.lower())

            frame_length = frame_length - data_length
    else:
        # Single frame - build complete frame
        pdu_header = (
            header + "00ff" + pri_service_first + inv_pri_first + class_id +
            obis_code + att_value + "00" + last_block_val + "00000001"
        )
        data_length = len(full_frame)
        frame_to_send = (
            pdu_header + data_length_descriptor + f"{data_length//2 + 2:02x}" +
            array_length_indicator + f"{array_length:02x}" + full_frame
        )
        result_frames.append(frame_to_send.lower())

    return result_frames