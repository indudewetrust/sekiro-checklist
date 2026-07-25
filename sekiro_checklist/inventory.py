"""Read held-item quantities from a Sekiro character-slot payload.

Inventory is stored as 16-byte entries: [handle u32, itemId u32, quantity u32,
sortId u32], where for a goods item of id G the handle is 0xB0000000|G and the
itemId is 0x40000000|G. Scanning for that handle/itemId pair (at 4-byte
alignment) reliably finds real inventory entries and skips look-alike values in
other structures. A save can hold the same item in more than one list (held
bag + storage box); we sum them, which answers "do I have / how many".
"""
from __future__ import annotations

import struct

GOODS = 0x40000000
HANDLE = 0xB0000000
CATEGORY_MASK = 0xF0000000
ID_MASK = 0x0FFFFFFF


def item_counts(payload: bytes) -> dict[int, int]:
    """Map goods item id -> total quantity held in the slot."""
    counts: dict[int, int] = {}
    for off in range(0, len(payload) - 12, 4):
        item, = struct.unpack_from("<I", payload, off)
        if item & CATEGORY_MASK != GOODS:
            continue
        gid = item & ID_MASK
        handle, = struct.unpack_from("<I", payload, off - 4) if off >= 4 else (0,)
        if handle != (HANDLE | gid):
            continue
        qty, = struct.unpack_from("<I", payload, off + 4)
        if qty == 0 or qty > 0x00FFFFFF:
            continue
        counts[gid] = counts.get(gid, 0) + qty
    return counts


def count(payload: bytes, good_id: int) -> int:
    return item_counts(payload).get(good_id, 0)
