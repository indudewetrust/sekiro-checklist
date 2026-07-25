"""Sekiro S0000.sl2 (BND4) save archive parsing.

Format (confirmed against a real 1.06 save):
  - BND4 header (0x40 bytes): entry count at 0x0C, unicode flag at 0x30.
  - Entry headers (0x20 bytes each) from 0x40: size, data offset, name offset.
  - 12 entries: USER_DATA000..009 (character slots, 1 MiB each),
    USER_DATA010 (profile: steam id, slot occupancy), USER_DATA011.
  - Each entry's data = 16-byte MD5 of payload + payload. No encryption.

Character slot payload starts with the serialized event flag structure:
  +0x00 u32 0xFFFFFFFF
  +0x04 u32 divisor (1000)
  +0x08 u32 unknown
  +0x0C u32 section size (= buffer size + 0x10)
  +0x30 u32 flag buffer size
  +0x34 flag buffer (block_count * 0x80 bytes)

The flag buffer block ordering matches the game's in-memory flag arena
exactly (verified block-for-block), so a block index computed from live memory
applies directly to a saved slot.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from pathlib import Path

SLOT_COUNT = 10
PROFILE_ENTRY = 10
OCCUPANCY_OFFSET = 212  # in USER_DATA010 payload (from SL2Bonfire profile)
STEAMID_OFFSET = 36


@dataclass
class Entry:
    name: str
    data: bytes  # payload with MD5 prefix stripped
    checksum_ok: bool


@dataclass
class SaveFile:
    path: Path
    entries: list[Entry] = field(default_factory=list)

    @property
    def steam_id(self) -> int:
        return struct.unpack_from("<Q", self.entries[PROFILE_ENTRY].data, STEAMID_OFFSET)[0]

    @property
    def occupied_slots(self) -> list[int]:
        occ = self.entries[PROFILE_ENTRY].data[OCCUPANCY_OFFSET:OCCUPANCY_OFFSET + SLOT_COUNT]
        return [i for i, b in enumerate(occ) if b == 1]

    def slot(self, index: int) -> bytes:
        return self.entries[index].data


def load(path: str | Path) -> SaveFile:
    path = Path(path)
    data = path.read_bytes()
    if data[:4] != b"BND4":
        raise ValueError(f"{path} is not a BND4 archive (Sekiro .sl2 save)")

    file_count, = struct.unpack_from("<I", data, 0x0C)
    save = SaveFile(path=path)
    pos = 0x40
    for _ in range(file_count):
        padding, size, _, doff, noff, _, _ = struct.unpack_from("<QIIIIII", data, pos)
        if padding != 0xFFFFFFFF00000050:
            raise ValueError("bad BND4 entry header")
        pos += 0x20

        end = noff
        while data[end:end + 2] != b"\x00\x00":
            end += 2
        name = data[noff:end].decode("utf-16-le")

        raw = data[doff:doff + size]
        checksum, payload = raw[:16], raw[16:]
        ok = hashlib.md5(payload).digest() == checksum
        save.entries.append(Entry(name=name, data=payload, checksum_ok=ok))
    return save


@dataclass
class FlagSection:
    divisor: int
    buffer: bytes


def flag_section(slot_payload: bytes) -> FlagSection:
    marker, divisor = struct.unpack_from("<II", slot_payload, 0)
    if marker != 0xFFFFFFFF or divisor == 0 or divisor > 100000:
        raise ValueError("slot does not start with an event flag section")
    buf_size, = struct.unpack_from("<I", slot_payload, 0x30)
    buf = slot_payload[0x34:0x34 + buf_size]
    if len(buf) != buf_size:
        raise ValueError("flag buffer truncated")
    return FlagSection(divisor=divisor, buffer=buf)
