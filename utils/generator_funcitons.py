import binascii
from datetime import datetime

def generate_frame_from_obis(obis_code: str) -> str:
    header = "000100110001000DC0018100030100"
    try:
        A, B, C = map(int, obis_code.split("."))
    except ValueError:
        raise ValueError("OBIS code format error A.B.C (e.g., 1.8.0)")
    obis_hex = f"{A:02X}{B:02X}{C:02X}"

    frame = header + obis_hex + "FF0200"
    return frame

def time_frame_generate(frame_header_hex, date_from, date_to): 

    def date_to_octet_hex(dt):
        """Convert datetime to DLMS OctetString hex format (12 bytes)"""
        weekday = (dt.weekday() + 1) % 7 or 7  # Python Monday=0 → DLMS Monday=1, Sunday=7
        return (
            f"{dt.year:04X}"          # Year (2 bytes)
            f"{dt.month:02X}"         # Month
            f"{dt.day:02X}"           # Day
            f"{weekday:02X}"          # Weekday (auto)
            f"{dt.hour:02X}"          # Hour
            f"{dt.minute:02X}"        # Minute
            f"{dt.second:02X}"        # Second
            "00800000"                # Fixed suffix
        )
    
    # Generate date hex strings
    octet_from_hex = date_to_octet_hex(date_from)
    octet_to_hex = date_to_octet_hex(date_to)
    
    # Construct the complete frame
    complete_frame = (
        frame_header_hex +
        octet_from_hex +
        "090C" +
        octet_to_hex +
        "0100"  # Fixed suffix
    )
    
    return complete_frame.upper()