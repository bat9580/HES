from datetime import datetime, timedelta, timezone

def dlms_datetime_to_python(hex_str: str) -> datetime | None:
    if len(hex_str) != 24:
        raise ValueError("DLMS datetime must be 12 bytes")

    b = bytes.fromhex(hex_str)

    year = int.from_bytes(b[0:2], "big")
    month = b[2]
    day = b[3]
    hour = b[5]
    minute = b[6]
    second = b[7]

    # Unspecified fields
    if 0xFF in (month, day, hour, minute, second):
        return None

    deviation = int.from_bytes(b[9:11], "big", signed=True)

    # DLMS: 0x8000 means deviation not specified
    if deviation == -32768:
        return datetime(year, month, day, hour, minute, second)

    # Valid timezone offset (±24h)
    if not (-1440 < deviation < 1440):
        return datetime(year, month, day, hour, minute, second)

    tz = timezone(timedelta(minutes=deviation))
    return datetime(year, month, day, hour, minute, second, tzinfo=tz)


def is_empty_dcu_blacklist_response(frame_hex: str) -> bool:
    """
    DCU returns a 14-byte frame when the blacklist has no entries.
    The invoke/priority byte after c401 varies (e.g. 42 with static templates, 44 with rotation).
    Example: 0001000100500006c40144000100
    """
    h = frame_hex.lower().replace(" ", "")
    if len(h) != 28:
        return False
    return h.startswith("0001000100500006c401") and h.endswith("000100")


ENTRY_HEX_LEN = 82  # 02 04 + meter + uint16 + 2 datetimes
ENTRY_BYTE_LEN = ENTRY_HEX_LEN // 2


def _find_block_payload_offset(frame: bytes, is_first: bool) -> tuple[int, str]:
    """
    Locate the start of DLMS blacklist data inside a DCU response frame.

    Large responses use 8203 block transfer (slice after block length).
    Small responses use 01 <qty> 02 04 directly after the APDU header (no 8203).
    """
    h = frame.hex().lower()

    marker = h.find("8203", 26)  # skip 13-byte HDLC header
    if marker != -1:
        offset = (marker + 6) // 2
        note = f"8203 block transfer, payload at byte {offset}"
        if not is_first:
            payload_hex = h[offset * 2 :]
            if not payload_hex.startswith("0204"):
                alt = payload_hex.find("0204")
                if 0 <= alt <= 32:
                    offset += alt // 2
                    note += f", realigned to 0204 at +{alt // 2}"
        return offset, note

    struct_idx = h.find("0204", 26)
    if struct_idx == -1:
        struct_idx = h.find("0204")

    if struct_idx != -1:
        if struct_idx >= 4 and h[struct_idx - 4 : struct_idx - 2] == "01":
            offset = (struct_idx - 4) // 2
            qty_hex = h[struct_idx - 2 : struct_idx]
            note = f"compact array at byte {offset} (qty=0x{qty_hex})"
            return offset, note
        offset = struct_idx // 2
        note = f"structure at byte {offset} (no array prefix)"
        return offset, note

    if len(frame) > 13:
        return 13, "fallback HDLC+APDU offset 13"
    return 0, "no header strip"


def stitch_blacklist_frames(frames: list[bytes]) -> tuple[str, list[dict]]:
    """Concatenate multi-frame blacklist block data with per-frame slice diagnostics."""
    if not frames:
        return "", []

    details: list[dict] = []
    parts: list[str] = []

    for i, frame in enumerate(frames):
        is_first = i == 0
        offset, note = _find_block_payload_offset(frame, is_first)
        chunk = frame[offset:]
        chunk_hex = chunk.hex().lower()
        head = chunk_hex[:12]
        details.append(
            {
                "frame": i + 1,
                "total_bytes": len(frame),
                "offset": offset,
                "payload_bytes": len(chunk),
                "starts_with": head,
                "note": note,
            }
        )
        parts.append(chunk_hex)

    return "".join(parts), details


def _find_array_header(h: str) -> tuple[int, int] | None:
    """Return (array_pos, array_qty) or None if not found."""
    idx = h.find("0204")
    if idx == -1:
        return None
    array_pos = idx - 4
    if array_pos < 0 or h[array_pos:array_pos + 2] != "01":
        return None
    array_qty = int(h[array_pos + 2:array_pos + 4], 16)
    return array_pos, array_qty


def peek_blacklist_array_qty(frame_hex: str) -> int | None:
    h = frame_hex.lower().replace(" ", "")
    header = _find_array_header(h)
    if header:
        return header[1]
    if "0204" in h:
        return 1
    return None


def estimate_entries_in_payload(frame_hex: str) -> int:
    """How many full structures fit in the payload after the array header."""
    h = frame_hex.lower().replace(" ", "")
    header = _find_array_header(h)
    if header:
        _, array_qty = header
        data_len = len(h) - (header[0] + 4)
        by_size = data_len // ENTRY_HEX_LEN
        return min(array_qty, by_size)
    idx = h.find("0204")
    if idx == -1:
        return 0
    return max(1, (len(h) - idx) // ENTRY_HEX_LEN)


def parse_dlms_array(frame_hex: str):
    # 1. Find array start (01 <qty> 02 04)
    h = frame_hex.lower().replace(" ", "")
    idx = h.find("0204")
    if idx == -1:
        if is_empty_dcu_blacklist_response(h):
            return []
        raise ValueError("No DLMS structure found")

    header = _find_array_header(h)
    if header:
        array_pos, array_qty = header
        pos = array_pos + 4
    else:
        # Small single-entry frame: payload starts at 0204 without 01 <qty> prefix
        array_pos = idx
        array_qty = 1
        pos = idx

    results = []

    for entry_idx in range(array_qty):
        remaining = len(h) - pos
        if remaining < ENTRY_HEX_LEN:
            print(
                f"⚠️  Only {entry_idx}/{array_qty} entries parsed "
                f"(ran out of data with {remaining} hex chars left)"
            )
            break

        # Structure tag
        if h[pos:pos + 2] != "02" or h[pos + 2:pos + 4] != "04":
            if entry_idx == 0:
                raise ValueError(
                    f"Expected structure 0204 at entry {entry_idx + 1}/{array_qty}, "
                    f"pos={pos}, got={h[pos:pos + 8]!r}, "
                    f"remaining={remaining} hex chars"
                )
            print(
                f"⚠️  Only {entry_idx}/{array_qty} entries parsed "
                f"(unexpected data at pos={pos}: {h[pos:pos + 8]!r})"
            )
            break
        pos += 4

        # Meter number
        if h[pos:pos + 2] != "09" or h[pos + 2:pos + 4] != "06":
            raise ValueError(
                f"Expected meter 0906 at entry {entry_idx + 1}/{array_qty}, "
                f"pos={pos}, got={h[pos:pos + 8]!r}"
            )
        meter = h[pos+4:pos+16]
        meter = meter.lstrip("0")
        pos += 16

        # UInt16
        if h[pos:pos + 2] != "12":
            raise ValueError(
                f"Expected uint16 12 at entry {entry_idx + 1}/{array_qty}, "
                f"pos={pos}, got={h[pos:pos + 8]!r}"
            )
        connection_time = int(h[pos+2:pos+6], 16)
        pos += 6

        # Start date
        if h[pos:pos + 2] != "09" or h[pos + 2:pos + 4] != "0c":
            raise ValueError(
                f"Expected start date 090c at entry {entry_idx + 1}/{array_qty}, "
                f"pos={pos}, got={h[pos:pos + 8]!r}"
            )
        start_date = h[pos+4:pos+28]
        start_date = dlms_datetime_to_python(start_date)
        pos += 28

        # End date
        if h[pos:pos + 2] != "09" or h[pos + 2:pos + 4] != "0c":
            raise ValueError(
                f"Expected end date 090c at entry {entry_idx + 1}/{array_qty}, "
                f"pos={pos}, got={h[pos:pos + 8]!r}"
            )
        end_date = h[pos+4:pos+28]
        end_date = dlms_datetime_to_python(end_date)
        pos += 28

        results.append({
            "meter": meter,
            "connection_time": connection_time,
            "start_date": start_date,
            "end_date": end_date
        })

    if results and len(results) < array_qty:
        print(
            f"⚠️  DCU header declared {array_qty} entries, "
            f"parsed {len(results)} from stitched payload"
        )

    return results

