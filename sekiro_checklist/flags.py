"""Event flag lookup within a save slot's flag buffer.

The mapping from flag id to a byte/bit in the buffer was reverse-engineered
from Sekiro's GetEventFlag (see tools/build_flag_map.py). data/flag_blocks.json
holds, per flag id // 1000 (the "block id"), the block's index in the flag
buffer; that table is produced once from live game memory and is identical for
every save of the same game version.

Within a block, the game reads dword[L>>5] bit (31-(L&31)) where L = flag %
1000 - a byte-swapped 32-bit layout:
    byte = block_index*0x80 + (L>>5)*4 + (3 - ((L>>3) & 3))
    bit  = 7 - (L & 7)
"""
from __future__ import annotations

import json

from .paths import data_dir
from .sl2 import FlagSection

DATA_DIR = data_dir()
BLOCK = 0x80


class FlagReader:
    def __init__(self, section: FlagSection, flag_map: dict | None = None):
        if flag_map is None:
            flag_map = json.loads(
                (DATA_DIR / "flag_blocks.json").read_text(encoding="utf-8"))
        self.divisor = flag_map.get("divisor", 1000)
        self.blocks = {int(k): v for k, v in flag_map["blocks"].items()}
        self.buffer = section.buffer
        if section.divisor != self.divisor:
            raise ValueError(
                f"save divisor {section.divisor} != map divisor {self.divisor}")

    def get(self, flag_id: int) -> bool | None:
        """True/False if the flag's block is known, None otherwise."""
        block_id, local = divmod(flag_id, self.divisor)
        index = self.blocks.get(block_id)
        if index is None:
            return None
        byte = index * BLOCK + (local >> 5) * 4 + (3 - ((local >> 3) & 3))
        if byte >= len(self.buffer):
            return None
        return bool(self.buffer[byte] >> (7 - (local & 7)) & 1)
