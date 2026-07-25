"""Build data/flag_blocks.json from Sekiro's live flag structures (read-only).

Run while Sekiro v1.06 is running with a character loaded in the game world.

How the mapping is derived (all reverse-engineered from GetEventFlag at
sekiro.exe+0x6c3e60 and its resolver at +0x6c63f0, verified on a real save):

A flag id decomposes into decimal digit groups:
    c      = (flag // 1e7) % 10     -> category   (index into flagMan+0x218)
    region = (flag // 1e5) % 100    -> map region
    sub2   = (flag // 1e4) % 10     -> map sub-index
    s      = (flag // 1000) % 10    -> sub-descriptor within a block
    L      =  flag % 1000           -> bit within the 0x80-byte block

(region, sub2) -> block index b comes from the FieldArea singleton
(sekiro.exe+0x3d5c0a0): obj = *(FieldArea+0x18); an array of 0x38-byte parent
entries {region@+0xb, subCount@+0x20, subArray@+0x28}; each 0xb0-byte
sub-entry has {sub2@+0xa, region@+0xb, blockIndex@+0x20}. Regions with no
entry resolve to b=0 (this is correct for category 0, which holds a single
block: system flags, boss-defeat flags 9xxx, item-acquire flags 6xxx).

The descriptor (c, b, s) -> arena byte offset is read straight from the block
pointer arrays hanging off flagMan+0x218, so we never reproduce the arena
allocation. Within a block, GetEventFlag reads dword[L>>5] bit (31-(L&31)),
i.e. a byte-swapped 32-bit layout:
    byte = offset + (L>>5)*4 + (3 - ((L>>3) & 3));  bit = 7 - (L & 7)

Output data/flag_blocks.json is version-stable and lets the checker run fully
offline afterwards.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from meminfo import Mem, find_pid, module_base, PROCESS_NAME  # noqa: E402
from sekiro_checklist import sl2  # noqa: E402

OUT = ROOT / "data" / "flag_blocks.json"
BLOCK = 0x80
EVENTFLAGMAN = 0x3D55FE8
FIELDAREA = 0x3D5C0A0
TRUTH_TRUE = [11100000]  # Dilapidated Temple idol: set for any post-intro save


def read_layout(mem: Mem, base: int):
    vmf = mem.u64(base + EVENTFLAGMAN)
    arena = mem.u64(vmf + 0x00)
    arena_size = mem.u32(vmf + 0x10)
    cat_array = mem.u64(vmf + 0x218)
    layout, counts = {}, {}
    for c in range(10):
        ptr = mem.u64(cat_array + c * 0x18)
        count = mem.u64(cat_array + c * 0x18 + 8)
        if not ptr or not (0 < count <= 1000):
            continue
        counts[c] = count
        for b in range(count):
            raw = mem.read(ptr + b * 0xA8, 0xA0)
            for s in range(10):
                sp, _ = struct.unpack_from("<QQ", raw, s * 0x10)
                if arena <= sp < arena + arena_size:
                    layout[(c, b, s)] = (sp - arena) // BLOCK
    return arena_size, layout, counts


def read_fieldarea(mem: Mem, base: int):
    fa = mem.u64(base + FIELDAREA)
    obj = mem.u64(fa + 0x18)
    count = mem.u32(obj + 8)
    arr = mem.u64(obj + 0x10)
    table = {}
    if not (0 < count < 1000):
        return table
    for i in range(count):
        e = mem.read(arr + i * 0x38, 0x38)
        subcount = struct.unpack_from("<I", e, 0x20)[0]
        subarr = struct.unpack_from("<Q", e, 0x28)[0]
        if not (0 < subcount < 100) or not subarr:
            continue
        for sidx in range(subcount):
            sub = mem.read(subarr + sidx * 0xB0, 0x24)
            sub2 = sub[0x0A]
            region = sub[0x0B]
            blockidx = struct.unpack_from("<i", sub, 0x20)[0]
            table[(region, sub2)] = blockidx
    return table


def decompose(flag: int):
    c = (flag // 10**7) % 10
    region = (flag // 10**5) % 100
    sub2 = (flag // 10**4) % 10
    s = (flag // 1000) % 10
    return c, region, sub2, s


def bit_in_block(buf: bytes, block_index: int, local: int):
    byte = block_index * BLOCK + (local >> 5) * 4 + (3 - ((local >> 3) & 3))
    if byte >= len(buf):
        return None
    return bool(buf[byte] >> (7 - (local & 7)) & 1)


def resolve_b(table, region, sub2):
    """Block index within a category. Matches Sekiro's resolver:
    region-0 / unmatched flags (category 0: system, boss 9xxx, item 6xxx) use
    block 0; matched flags use the FieldArea block index + 1 (the ceremony
    path increments it)."""
    blockidx = table.get((region, sub2))
    return 0 if blockidx is None else blockidx + 1


def build_blocks(layout, table, block_ids):
    blocks, unmapped = {}, []
    for bid in sorted(block_ids):
        flag = bid * 1000
        c, region, sub2, s = decompose(flag)
        b = resolve_b(table, region, sub2)
        idx = layout.get((c, b, s))
        if idx is None:
            unmapped.append(bid)
        else:
            blocks[bid] = idx
    return blocks, unmapped


def known_block_ids():
    items = json.loads(
        (ROOT / "data" / "checklist.json").read_text(encoding="utf-8"))["items"]
    ids = {it["flag"] // 1000 for it in items}
    ids.update(t // 1000 for t in TRUTH_TRUE)
    return ids


def find_save() -> Path:
    """A save to validate the finished map against: an existing working copy,
    else the newest S0000.sl2 under %APPDATA%\\Sekiro."""
    import os
    work = ROOT / "work"
    for name in ("current-S0000.sl2", "S0000.sl2"):
        if (work / name).exists():
            return work / name
    saves = sorted((Path(os.environ.get("APPDATA", "")) / "Sekiro").glob("*/S0000.sl2"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not saves:
        raise SystemExit("No save found to validate against "
                         "(looked in work/ and %APPDATA%\\Sekiro).")
    return saves[0]


def main() -> int:
    pid = find_pid(PROCESS_NAME)
    if pid is None:
        print("Sekiro is not running. Load a character into the world first.")
        return 1
    mem = Mem(pid)
    base, _ = module_base(pid, PROCESS_NAME)

    arena_size, layout, counts = read_layout(mem, base)
    table = read_fieldarea(mem, base)
    print(f"categories: {counts}")
    print(f"descriptors: {len(layout)}  fieldarea entries: {len(table)}")

    block_ids = known_block_ids()
    blocks, unmapped = build_blocks(layout, table, block_ids)
    print(f"mapped {len(blocks)}/{len(block_ids)} block ids; unmapped: {sorted(unmapped)}")

    save = sl2.load(find_save())
    ok = True
    for slot in save.occupied_slots:
        buf = sl2.flag_section(save.slot(slot)).buffer
        for f in TRUTH_TRUE:
            idx = blocks.get(f // 1000)
            val = bit_in_block(buf, idx, f % 1000) if idx is not None else None
            print(f"  slot {slot + 1}: idol flag {f} = {val}")
            ok = ok and bool(val)
    if not ok:
        print("VALIDATION FAILED - not writing map.")
        return 2

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "game": "Sekiro v1.06",
        "divisor": 1000,
        "block_size": BLOCK,
        "layout": "byteswap: byte=(L>>5)*4+(3-((L>>3)&3)); bit=7-(L&7)",
        "region_sub2_to_block": {f"{r},{s}": b for (r, s), b in sorted(table.items())},
        "blocks": {str(k): v for k, v in sorted(blocks.items())},
    }, indent=0), encoding="utf-8")
    print(f"wrote {OUT} ({len(blocks)} blocks) - validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
