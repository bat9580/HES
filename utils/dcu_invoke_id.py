"""
Per-DCU DLMS invoke-id / priority byte (0x40–0x4F) for requests sent to a DCU.

Each new request frame uses the next value; after 0x4F wraps to 0x40.
The byte immediately follows a service tag (c001, c002, c003, c101, c301) in the hex PDU.
"""

from __future__ import annotations

import threading

_LOCK = threading.Lock()
_NEXT: dict[str, int] = {}

INVOKE_MIN = 0x40
INVOKE_MAX = 0x4F

# Longer / more specific tags first; each is 4 hex chars + 1-byte invoke id.
_SERVICE_PREFIXES = ("c301", "c101", "c003", "c002", "c001")


def _norm_key(dcu_key: str | int) -> str:
    return str(dcu_key).strip()


def next_dcu_invoke_hex(dcu_key: str | int) -> str:
    """Return next invoke id as two lowercase hex digits; rotates 40–4F then 40."""
    k = _norm_key(dcu_key)
    with _LOCK:
        cur = _NEXT.get(k, INVOKE_MIN)
        out = f"{cur:02x}"
        if cur >= INVOKE_MAX:
            _NEXT[k] = INVOKE_MIN
        else:
            _NEXT[k] = cur + 1
        return out


def with_dcu_invoke(hex_frame: str, dcu_key: str | int) -> str:
    """
    Replace the invoke byte after the first matching service tag.
    If no tag matches, returns the frame unchanged (e.g. ACK / AARQ).
    """
    h = hex_frame.strip().lower().replace(" ", "")
    for svc in _SERVICE_PREFIXES:
        idx = h.find(svc)
        if idx == -1:
            continue
        if len(h) < idx + 6:
            return hex_frame
        before = h[: idx + 4]
        after = h[idx + 6 :]
        return before + next_dcu_invoke_hex(dcu_key) + after
    return hex_frame


def migrate_dcu_invoke_session(peer_key: str | int, dcu_key: str | int) -> None:
    """After TCP handshake, move counter from peer-scoped key to DCU id key."""
    pk = _norm_key(peer_key)
    dk = _norm_key(dcu_key)
    if pk == dk:
        return
    with _LOCK:
        if pk not in _NEXT:
            return
        _NEXT[dk] = _NEXT.pop(pk)
