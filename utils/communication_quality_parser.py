"""
Parse DCU communication-quality GetResponse (DLMS/COSEM).

Uses the fixed layout: Array of structures (7 elements each):
  OctetString (meter id) | UInt8 | UInt8 | UInt16 | UInt16 | UInt8 | UInt8

See FrameParser / MeterRecord for field semantics. Adjust FRAME_HEADER_LEN or
_find_array_offset() if your DCU wraps the payload differently.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Optional

# DLMS type tags
TAG_ARRAY = 0x01
TAG_STRUCTURE = 0x02
TAG_OCTET_STR = 0x09
TAG_UINT8 = 0x11
TAG_UINT16 = 0x12
TAG_UINT32 = 0x06


def _norm_comm(s: str) -> str:
    if not s:
        return ""
    h = s.strip().lower().replace(" ", "").replace("0x", "")
    return h.lstrip("0") or "0"


@dataclass
class MeterRecord:
    """One row from the DCU quality array (7 DLMS elements after comm addr)."""

    meter_id: str  # element 0: octet string (comm addr)
    field1: int  # element 1: 0x6F → online, else offline
    field2: int  # element 2: success rate (typically 0–100)
    value_a: int  # element 3: sent frame count (UInt16)
    value_b: int  # element 4: received frame count (UInt16)
    status1: int  # element 5: relay level (UInt8)
    status2: int  # element 6: node phase (UInt8)

    @property
    def delta(self) -> int:
        return self.value_a - self.value_b


class FrameParser:
    """
    Parses raw DLMS/COSEM GetResponseNormal payload (hex).

    Default: skip FRAME_HEADER_LEN bytes, then Array (0x01) + count, then
    structures (0x02 0x07 + seven typed fields).
    """

    FRAME_HEADER_LEN = 12

    def __init__(self, hex_str: str):
        clean = hex_str.replace(" ", "").replace("0x", "").lower()
        self.data = bytes.fromhex(clean)
        self.pos = 0

    def _read(self, n: int) -> bytes:
        chunk = self.data[self.pos : self.pos + n]
        if len(chunk) < n:
            raise ValueError(f"Unexpected end of frame at offset {self.pos}")
        self.pos += n
        return chunk

    def _u8(self) -> int:
        return struct.unpack("B", self._read(1))[0]

    def _u16(self) -> int:
        return struct.unpack(">H", self._read(2))[0]

    def _u32(self) -> int:
        return struct.unpack(">I", self._read(4))[0]

    def _expect(self, tag: int, label: str = "") -> None:
        t = self._u8()
        if t != tag:
            raise ValueError(
                f"Expected tag 0x{tag:02X} ({label}) at offset {self.pos - 1}, got 0x{t:02X}"
            )

    def parse_from_offset(self, start: int) -> List[MeterRecord]:
        """Parse array of MeterRecord starting at byte offset ``start`` (Array tag)."""
        self.pos = start
        self._expect(TAG_ARRAY, "Array")
        qty = self._u8()
        records: List[MeterRecord] = []
        for _ in range(qty):
            # Some DCU firmware inserts 0x01 between array elements before the next structure
            if (
                self.pos < len(self.data)
                and self.data[self.pos] == TAG_ARRAY
                and self.pos + 1 < len(self.data)
                and self.data[self.pos + 1] == TAG_STRUCTURE
            ):
                self.pos += 1
            records.append(self._parse_structure())
        return records

    def _parse_structure(self) -> MeterRecord:
        self._expect(TAG_STRUCTURE, "Structure")
        n = self._u8()
        if n != 7:
            raise ValueError(f"Expected structure with 7 elements, got {n}")

        self._expect(TAG_OCTET_STR, "OctetString")
        length = self._u8()
        meter_bytes = self._read(length)
        meter_id = meter_bytes.hex().upper()

        self._expect(TAG_UINT8, "UInt8 field1")
        field1 = self._u8()
        self._expect(TAG_UINT8, "UInt8 field2")
        field2 = self._u8()

        self._expect(TAG_UINT16, "UInt16 A")
        value_a = self._u16()
        self._expect(TAG_UINT16, "UInt16 B")
        value_b = self._u16()

        self._expect(TAG_UINT8, "UInt8 status1")
        status1 = self._u8()
        self._expect(TAG_UINT8, "UInt8 status2")
        status2 = self._u8()

        return MeterRecord(
            meter_id=meter_id,
            field1=field1,
            field2=field2,
            value_a=value_a,
            value_b=value_b,
            status1=status1,
            status2=status2,
        )


def _strip_hdlc_if_present(data: bytes) -> bytes:
    if len(data) > 1 and data[0] == 0x7E:
        end = data.rfind(0x7E)
        if end > 0:
            return data[1:end]
    return data


def _find_array_offset(data: bytes) -> Optional[int]:
    """
    Locate 0x01 (array) followed by qty byte then 0x02 0x07 (structure of 7).
    Searches first 96 bytes.
    """
    limit = min(len(data) - 4, 96)
    for i in range(limit):
        if data[i] != TAG_ARRAY:
            continue
        qty = data[i + 1]
        if qty == 0 or qty > 200:
            continue
        if i + 3 < len(data) and data[i + 2] == TAG_STRUCTURE and data[i + 3] == 7:
            return i
    return None


ONLINE_STATUS_BYTE = 0x6F  # 2nd array element: online when this value, else offline


def meter_record_to_ui_row(r: MeterRecord) -> dict:
    """
    Map MeterRecord → meter-download table (order matches DCU response structure):

    0. Octet string — comm addr (meter_id)
    1. UInt8 — online if 0x6F, else offline
    2. UInt8 — success rate (shown as % when 0..100)
    3. UInt16 — sent frame count
    4. UInt16 — received frame count
    5. UInt8 — relay level
    6. UInt8 — node phase (1=A, 2=B, 3=C when applicable)
    """
    node_status = "Online" if r.field1 == ONLINE_STATUS_BYTE else "Offline"

    if 0 <= r.field2 <= 100:
        success_rate = f"{r.field2}%"
    else:
        success_rate = str(r.field2)

    phase_map = {0: "—", 1: "A", 2: "B", 3: "C"}
    node_phase = phase_map.get(r.status2, f"0x{r.status2:02X}")

    comm_key = _norm_comm(r.meter_id)

    return {
        "comm_addr": r.meter_id,
        "comm_key": comm_key,
        "node_status": node_status,
        "node_success_rate": success_rate,
        "send_frame_count": str(r.value_a),
        "receive_frame_count": str(r.value_b),
        "relay_level": str(r.status1),
        "node_phase": node_phase,
    }


def parse_communication_quality_response(response: bytes) -> tuple[list[dict], str | None]:
    """
    Returns (rows_for_ui, error_or_warning).

    Tries FrameParser at offset 12, then auto-detected array offset.
    """
    if not response:
        return [], "Empty response"

    data = _strip_hdlc_if_present(response)
    hex_str = data.hex()

    offsets_to_try: list[int] = []
    if len(data) >= FrameParser.FRAME_HEADER_LEN + 4:
        offsets_to_try.append(FrameParser.FRAME_HEADER_LEN)
    found = _find_array_offset(data)
    if found is not None and found not in offsets_to_try:
        offsets_to_try.insert(0, found)

    last_err: Optional[str] = None
    for start in offsets_to_try:
        try:
            parser = FrameParser(hex_str)
            records = parser.parse_from_offset(start)
            rows = [meter_record_to_ui_row(r) for r in records]
            if rows:
                return rows, None
        except (ValueError, struct.error, IndexError) as e:
            last_err = str(e)
            continue

    return [], last_err or "Could not parse communication-quality payload"
