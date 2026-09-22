def crc16(hex_string):
    # Remove non-hex characters
    clean_hex = ''.join(c for c in hex_string if c in '0123456789abcdefABCDEF')

    if len(clean_hex) % 2 != 0:
        raise ValueError("Hex string must have even length")

    data = bytes.fromhex(clean_hex)

    polynomial = 0x1021
    crc = 0xFFFF
    xor_out = 0xFFFF
    reflect_in = True
    reflect_out = True

    for byte in data:

        # Input reflection
        if reflect_in:
            byte = ((byte & 0x55) << 1) | ((byte & 0xAA) >> 1)
            byte = ((byte & 0x33) << 2) | ((byte & 0xCC) >> 2)
            byte = ((byte & 0x0F) << 4) | ((byte & 0xF0) >> 4)

        crc ^= (byte << 8)

        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ polynomial
            else:
                crc <<= 1

            crc &= 0xFFFF

    # Output reflection
    if reflect_out:
        crc = ((crc & 0x5555) << 1) | ((crc & 0xAAAA) >> 1)
        crc = ((crc & 0x3333) << 2) | ((crc & 0xCCCC) >> 2)
        crc = ((crc & 0x0F0F) << 4) | ((crc & 0xF0F0) >> 4)
        crc = ((crc & 0x00FF) << 8) | ((crc & 0xFF00) >> 8)

    crc ^= xor_out

    return crc


def string_to_hex(s):
    return ''.join(f"{ord(c):02X}" for c in s)


def get_HDLC_address(addr_hex):
    addr = int(addr_hex, 16)
    parts = []

    while addr > 0:
        parts.append(addr & 0x7F)
        addr >>= 7

    parts.reverse()

    result = []
    for i, part in enumerate(parts):
        byte = part << 1
        if i == len(parts) - 1:
            byte |= 1
        result.append(byte)

    addr_bytes = bytes(result)

    # If address length is 3 bytes, make it 4 by adding 00 in front
    if len(addr_bytes) == 3:
        addr_bytes = b'\x00' + addr_bytes

    return addr_bytes

def build_SNRM_frame(dest_addr): 
    dest = get_HDLC_address(dest_addr)
    src = get_HDLC_address("20") 
    control = bytes.fromhex("93")

    # frame format placeholder
    frame_format = bytes.fromhex("A0 00")

    header = frame_format + dest + src + control

    # calculate length (header + HCS)
    length = len(header) + 2
    header = bytes([0xA0, length]) + dest + src + control

    crc_input = header.hex()
    crc = crc16(crc_input)

    hcs = bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    frame = bytes.fromhex("7E") + header + hcs + bytes.fromhex("7E")

    return frame.hex()

def build_AARQ_frame(dest_addr, password):

    dest = get_HDLC_address(dest_addr)
    src = get_HDLC_address("20")  # client address

    control = bytes.fromhex("10")  # I-frame

    # LLC header
    llc = bytes.fromhex("E6E600")

    # password -> hex
    pwd_hex = password.encode().hex().upper()

    # AARQ body (static part used by most meters)
    aarq = bytes.fromhex(
        "6036"
        "A109060760857405080101"
        "8A020780"
        "8B0760857405080201"
    )

    # authentication
    auth = bytes.fromhex("AC0A8008") + bytes.fromhex(pwd_hex)

    # initiate request
    initiate = bytes.fromhex(
        "BE10"
        "040E"
        "01000000"
        "06"
        "5F1F0400007E1F"
        "04B0"
    )

    pdu = llc + aarq + auth + initiate

    # build header
    frame_format = b'\xA0\x00'
    header = frame_format + dest + src + control

    # compute HCS
    length = len(header) + 2 + len(pdu) + 2
    header = bytes([0xA0, length]) + dest + src + control

    hcs_crc = crc16(header.hex()) 
    hcs = bytes([hcs_crc & 0xFF, (hcs_crc >> 8) & 0xFF])

    # full frame for FCS
    frame_no_flags = header + hcs + pdu

    fcs_crc = crc16(frame_no_flags.hex()) 
    fcs = bytes([fcs_crc & 0xFF, (fcs_crc >> 8) & 0xFF])

    frame = b'\x7E' + frame_no_flags + fcs + b'\x7E'

    return frame.hex()
def obis_to_bytes(obis):
    return bytes(int(x) for x in obis.split(".")) 

def build_get_request(dest_addr, obis, class_id="0003", attribute="02",frame_type = "32", invoke_id = "C1"): 

    dest = get_HDLC_address(dest_addr)
    src = get_HDLC_address("20") 

    control = bytes.fromhex(frame_type)  # I-frame

    llc = bytes.fromhex("E6E600")

    invoke = bytes.fromhex(invoke_id) 

    class_bytes = bytes.fromhex(class_id)
    obis_bytes = obis_to_bytes(obis)
    attribute_bytes = bytes.fromhex(attribute)

    selective_access = bytes.fromhex("00")

    dlms = (
        bytes.fromhex("C001") +
        invoke +
        class_bytes +
        obis_bytes +
        attribute_bytes +
        selective_access
    )

    pdu = llc + dlms

    frame_format = b'\xA0\x00'
    header = frame_format + dest + src + control

    length = len(header) + 2 + len(pdu) + 2
    header = bytes([0xA0, length]) + dest + src + control

    hcs_crc = crc16(header.hex())
    hcs = bytes([hcs_crc & 0xFF, (hcs_crc >> 8) & 0xFF])

    frame_no_flags = header + hcs + pdu

    fcs_crc = crc16(frame_no_flags.hex()) 
    fcs = bytes([fcs_crc & 0xFF, (fcs_crc >> 8) & 0xFF])

    frame = b'\x7E' + frame_no_flags + fcs + b'\x7E'

    return frame.hex()


def build_relay_operation_byte(dest_addr, obis, class_id="0003", attribute="02",frame_type = "32", invoke_id = "C1",operation = "01"):  

    dest = get_HDLC_address(dest_addr)
    src = get_HDLC_address("20") 

    control = bytes.fromhex(frame_type)  # I-frame

    llc = bytes.fromhex("E6E600")

    invoke = bytes.fromhex(invoke_id) 

    class_bytes = bytes.fromhex(class_id)
    obis_bytes = obis_to_bytes(obis)
    attribute_bytes = bytes.fromhex(attribute)
    relay_operation_byte = bytes.fromhex(operation) 
    relay_operation_byte2 = bytes.fromhex("01") 
    selective_access = bytes.fromhex("00")

    dlms = (
        bytes.fromhex("C301") +
        invoke +
        class_bytes +
        obis_bytes + 
        relay_operation_byte + 
        relay_operation_byte2 + 
        attribute_bytes +
        selective_access
    )

    pdu = llc + dlms

    frame_format = b'\xA0\x00'
    header = frame_format + dest + src + control

    length = len(header) + 2 + len(pdu) + 2
    header = bytes([0xA0, length]) + dest + src + control

    hcs_crc = crc16(header.hex())
    hcs = bytes([hcs_crc & 0xFF, (hcs_crc >> 8) & 0xFF])

    frame_no_flags = header + hcs + pdu

    fcs_crc = crc16(frame_no_flags.hex()) 
    fcs = bytes([fcs_crc & 0xFF, (fcs_crc >> 8) & 0xFF])

    frame = b'\x7E' + frame_no_flags + fcs + b'\x7E'

    return frame.hex()

def _date_to_octet_hex(dt):
    """Convert datetime to DLMS OctetString hex format (12 bytes) for profile selective access."""
    weekday = (dt.weekday() + 1) % 7 or 7
    return (
        f"{dt.year:04X}" + f"{dt.month:02X}" + f"{dt.day:02X}" +
        f"{weekday:02X}" + f"{dt.hour:02X}" + f"{dt.minute:02X}" +
        f"{dt.second:02X}" + "00800000"
    )


def build_profile_get_request(dest_addr, date_from, date_to, obis="99.1.0", invoke_id="C1"):
    """
    Build HDLC GetRequest for profile buffer (attribute 2) with selective access by time range.
    Used for energy load profile (99.1.0) or instant profile (99.2.0).
    """
    dest = get_HDLC_address(dest_addr)
    src = get_HDLC_address("20")
    control = bytes.fromhex("32")

    llc = bytes.fromhex("E6E600")
    invoke = bytes.fromhex(invoke_id)
    class_bytes = bytes.fromhex("0007")  # Profile generic
    obis_bytes = obis_to_bytes(obis)
    attribute = bytes.fromhex("02")  # buffer

    octet_from = _date_to_octet_hex(date_from)
    octet_to = _date_to_octet_hex(date_to)
    selective_access = bytes.fromhex(
        "01010204020412000809060000010000FF0F02120000"
        "09" + "0C" + octet_from +
        "09" + "0C" + octet_to +
        "0100"
    )

    dlms = (
        bytes.fromhex("C001") +
        invoke +
        class_bytes +
        obis_bytes +
        attribute +
        selective_access
    )

    pdu = llc + dlms
    frame_format = b'\xA0\x00'
    header = frame_format + dest + src + control
    length = len(header) + 2 + len(pdu) + 2
    header = bytes([0xA0, length]) + dest + src + control

    hcs_crc = crc16(header.hex())
    hcs = bytes([hcs_crc & 0xFF, (hcs_crc >> 8) & 0xFF])
    frame_no_flags = header + hcs + pdu
    fcs_crc = crc16(frame_no_flags.hex())
    fcs = bytes([fcs_crc & 0xFF, (fcs_crc >> 8) & 0xFF])
    frame = b'\x7E' + frame_no_flags + fcs + b'\x7E'

    return frame.hex()


# def generate_relay_frame_rs485_edat()