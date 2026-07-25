"""Extend data/flag_blocks.json to cover all current checklist flags - offline.

The flag arena is a contiguous run of 0x80 blocks grouped by category (verified
from live memory during the original calibration). Given the FieldArea region
table already saved in flag_blocks.json, the arena index of any flag block is:

    arena_index(c, b, s) = cat_base[c] + b*10 + s
        c      = (flag // 1e7) % 10
        region = (flag // 1e5) % 100 ; sub2 = (flag // 1e4) % 10 ; s = (flag//1000)%10
        b      = 0 if (region,sub2) not in table else table[(region,sub2)] + 1

cat_base comes from the fixed category layout (category 0 holds 1 block, the
rest 33 each, in arena order 0,1,2,5,6,7). This reproduces all 16 blocks the
live-memory calibration produced (asserted below), so extending it to new flags
needs no running game.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sekiro_checklist import sl2  # noqa: E402
from sekiro_checklist.flags import FlagReader  # noqa: E402

MAP = ROOT / "data" / "flag_blocks.json"
CHECKLIST = ROOT / "data" / "checklist.json"

# Fixed arena layout for Sekiro v1.06 (category, block count), in arena order.
CATEGORY_LAYOUT = [(0, 1), (1, 33), (2, 33), (5, 33), (6, 33), (7, 33)]

# World-state / system flag blocks the checklist doesn't reference directly but
# the report needs (block 8 holds the 83xx invasion/burn flags).
SYSTEM_BLOCK_IDS = {8}


def cat_bases() -> dict[int, int]:
    base, out = 0, {}
    for c, count in CATEGORY_LAYOUT:
        out[c] = base
        base += count * 10
    return out


def decompose(flag: int):
    c = (flag // 10**7) % 10
    region = (flag // 10**5) % 100
    sub2 = (flag // 10**4) % 10
    s = (flag // 1000) % 10
    return c, region, sub2, s


def main() -> int:
    fm = json.loads(MAP.read_text(encoding="utf-8"))
    table = {tuple(int(x) for x in k.split(",")): v
             for k, v in fm["region_sub2_to_block"].items()}
    bases = cat_bases()
    existing = {int(k): v for k, v in fm["blocks"].items()}

    def arena_index(block_id: int):
        flag = block_id * 1000
        c, region, sub2, s = decompose(flag)
        if c not in bases:
            return None
        b = table.get((region, sub2))
        b = 0 if b is None else b + 1
        return bases[c] + b * 10 + s

    # 1) reproduce every previously calibrated block exactly
    for bid, idx in existing.items():
        got = arena_index(bid)
        assert got == idx, f"reconstruction mismatch for block {bid}: {got} != {idx}"
    print(f"reconstruction reproduces all {len(existing)} calibrated blocks - OK")

    # 2) compute blocks for every checklist flag
    items = json.loads(CHECKLIST.read_text(encoding="utf-8"))["items"]
    block_ids = {it["flag"] // 1000 for it in items} | SYSTEM_BLOCK_IDS
    blocks, unmapped = dict(existing), []
    for bid in sorted(block_ids):
        idx = arena_index(bid)
        if idx is None or idx * 0x80 >= 0x33e00:
            unmapped.append(bid)
        else:
            blocks[bid] = idx
    print(f"checklist block ids: {len(block_ids)}; total mapped: {len(blocks)}; "
          f"unmapped: {sorted(unmapped)}")

    fm["blocks"] = {str(k): v for k, v in sorted(blocks.items())}
    MAP.write_text(json.dumps(fm, indent=0), encoding="utf-8")

    # 3) validate against the real save: idol True, a nonexistent-region flag
    #    behaves, and print new-category coverage on the NG+ completionist slot
    work = ROOT / "work"
    src = next((p for p in (work / "current-S0000.sl2", work / "S0000.sl2")
                if p.exists()), None)
    save = sl2.load(src)
    reader = FlagReader(sl2.flag_section(save.slot(3)))  # slot 4 (NG+)
    idol = reader.get(11100000)
    mibu = reader.get(50002050)
    print(f"\nslot 4 checks: Dilapidated Temple idol={idol}  Mibu Breathing={mibu}")
    assert idol, "idol validation failed"

    from collections import defaultdict
    cov = defaultdict(lambda: [0, 0, 0])  # have, known, unknown
    for it in items:
        v = reader.get(it["flag"])
        c = cov[it["category"]]
        if v is None:
            c[2] += 1
        else:
            c[1] += 1
            c[0] += v
    print("slot 4 coverage by category (have/known, unknown-block):")
    for cat, (h, k, u) in cov.items():
        extra = f"  [{u} unmapped]" if u else ""
        print(f"  {cat}: {h}/{k}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
