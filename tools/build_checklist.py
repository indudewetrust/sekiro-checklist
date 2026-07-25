"""Build data/checklist.json - the collectible list the checker reports on.

Design note on data provenance: the *flag ids*, *area names*, *source enemy
names*, and the *needs-diving* fact are extracted from the SoulsRandomizers
annotations (a build-time source in vendor/), because those are facts about the
game. The human-readable descriptions written into checklist.json are generated
here in our own words from that structured data - the annotations' prose is
never copied. The resulting checklist.json is therefore self-contained and
ours to distribute; regenerate it with this script if the source data changes.

Every acquisition flag is independently verified against real saves by the
checker (see the report), so we are not relying on the source being correct.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS = ROOT / "vendor" / "SoulsRandomizers" / "dists" / "Base" / "annotations.txt"
OUT = ROOT / "data" / "checklist.json"

# Ability that gates going underwater; its acquisition flag lets the report say
# "you can't dive for this yet". Corrupted Monk drop.
DIVING_FLAG = 50002050
DIVING_ABILITY = "Mibu Breathing Technique"

# Ashina (Interior Ministry) invasion trigger. After it, miniboss drops you
# skipped become buyable from the Offering Box at the Dilapidated Temple; each
# item below is in the box now if its acquisition flag is still unset.
INVASION_FLAG = 8301
OFFERING_BOX = [
    {"flag": 6723, "name": "Gourd Seed", "source": "General Naomori Kawarada"},
    {"flag": 6760, "name": "Prayer Bead", "source": "General Naomori Kawarada"},
    {"flag": 6762, "name": "Prayer Bead", "source": "General Tenzen Yamauchi"},
    {"flag": 6769, "name": "Prayer Bead", "source": "Seven Ashina Spears - Shikibu"},
    {"flag": 6766, "name": "Prayer Bead", "source": "General Kuranosuke Matsumoto"},
    {"flag": 6767, "name": "Prayer Bead", "source": "Ashina Elite Jinsuke Saze"},
    {"flag": 6780, "name": "Prayer Bead", "source": "Lone Shadow Masanaga the Spear-Bearer"},
]

# Items whose "have" status is read from held inventory (goods id) instead of a
# give-event flag, because the flag resets in NG+ but the item is kept. Esoteric
# texts unlock skill trees and stay in the inventory.
ESOTERIC_GOOD_IDS = {
    "Shinobi Esoteric Text": 2920, "Prosthetic Esoteric Text": 2921,
    "Ashina Esoteric Text": 2922, "Senpou Esoteric Text": 2923,
    "Mushin Esoteric Text": 2924,
}

# item name -> checklist category. Order here also orders the report.
ITEM_CATEGORIES = {
    # --- collectibles ---
    "Prayer Bead": "Prayer Beads",
    "Gourd Seed": "Gourd Seeds",
    "Mask Fragment: Right": "Mask Fragments",
    "Mask Fragment: Left": "Mask Fragments",
    "Mask Fragment: Dragon": "Mask Fragments",
    "Treasure Carp Scale": "Treasure Carp Scales",
    "Sakura Droplet": "Key Items",  # one-time final gourd upgrade
    # --- prosthetic tools ---
    "Shuriken Wheel": "Prosthetic Tools",
    "Robert's Firecrackers": "Prosthetic Tools",
    "Flame Barrel": "Prosthetic Tools",
    "Shinobi Axe of the Monkey": "Prosthetic Tools",
    "Mist Raven's Feathers": "Prosthetic Tools",
    "Sabimaru": "Prosthetic Tools",
    "Iron Fortress": "Prosthetic Tools",
    "Large Fan": "Prosthetic Tools",
    "Slender Finger": "Prosthetic Tools",
    "Gyoubu's Broken Horn": "Prosthetic Tools",
    "Mechanical Barrel": "Prosthetic Tools",
    # --- skills / arts ---
    "Shinobi Esoteric Text": "Esoteric Texts",
    "Prosthetic Esoteric Text": "Esoteric Texts",
    "Ashina Esoteric Text": "Esoteric Texts",
    "Senpou Esoteric Text": "Esoteric Texts",
    "Mushin Esoteric Text": "Esoteric Texts",
    "Bloodsmoke Ninjutsu": "Ninjutsu",
    "Puppeteer Ninjutsu": "Ninjutsu",
    "Bestowal Ninjutsu": "Ninjutsu",
    # --- key items ---
    "Mortal Blade": "Key Items",
    "Aromatic Branch": "Key Items",
    "Shelter Stone": "Key Items",
    "Lotus of the Palace": "Key Items",
    "Divine Dragon's Tears": "Key Items",
    "Young Lord's Bell Charm": "Key Items",
    "Father's Bell Charm": "Key Items",
    "Mibu Breathing Technique": "Key Items",
    "Gatehouse Key": "Key Items",
    "Hidden Temple Key": "Key Items",
    "Secret Passage Key": "Key Items",
    "Gun Fort Shrine Key": "Key Items",
    "Shinobi Prosthetic": "Key Items",
    "Kusabimaru": "Key Items",
}

CATEGORY_ORDER = [
    "Prayer Beads", "Gourd Seeds", "Prosthetic Tools", "Esoteric Texts",
    "Ninjutsu", "Key Items", "Mask Fragments",
    "Treasure Carp Scales", "Bosses & Memories", "Minibosses",
]

# Rough game-progression order; items within a category sort by this so the
# list reads top-to-bottom as you travel.
# Hand-written concise location hints (our own wording) for world pickups that
# would otherwise get a generic "Chest/Pickup in <area>" stub. Keyed by flag.
LOCATION_HINTS = {
    # Prayer Beads
    6788: "Chest on the top floor of the building up the stairs past Gyoubu",
    6789: "Chest behind the shinobi door before the Audience Chamber",
    6790: "Chest past the shinobi door in the Upper Tower map room (two fencers)",
    6795: "On a shrine on the upper floor of the Head Priest's house",
    6796: "Chest at the bottom of the Mibu Village pond",
    6792: "Backtrack from the Under-Shrine Valley idol toward the Headless cave",
    6793: "Deep in the caves under Giraffe's room - grapple up the ravine to the skull, then the centipede pit",
    6794: "Grapple left before the burrow drop, wall-jump to the cliff over Poison Pool, then the statue's head",
    6791: "Underwater in the Temple Grounds pond",
    6797: "In the chest guarded by the two underwater Headless",
    # Gourd Seeds
    6725: "Left room of the lookout building after the Chained Ogre",
    6726: "Chest just before the Upper Tower Antechamber",
    6728: "By the tree in the underground villagers' area",
    6724: "In Under-Shrine Valley, after two branch grapples climb the wall on the left instead of heading to the idol",
    6727: "Main room of the cricket building, before the Infested Seeker",
    6729: "Chest in the Palace Grounds building",
    # Prosthetic Tools
    71102230: "On the 2nd floor of the building by the Gate Path idol (or Offering Box after the invasion)",
    71101650: "From the Sculptor after you find the Sabimaru",
    6502: "By the bandits' bonfire",
    6504: "In the Three-Story Pagoda, guarded by a Lone Shadow",
    6503: "In the shrine where bandits argue about looting it",
    71111500: "Sold by Blackhat Badger; left behind when he leaves for Senpou, or his Offering Box if killed",
    6505: "Chest in the Upper Tower basement",
    71102240: "Chest in the Ashina Reservoir Gate House",
    6507: "In Giraffe's room, in front of the statue",
    # Esoteric Texts
    50006244: "From Tengu after you kill the rats (or his Ashina Castle spot if refused, after Divine Dragon)",
    6706: "From the Sculptor after you collect 3 prosthetic tools",
    6705: "From the Sculptor after your first skill point",
    50006246: "From Isshin/Emma once you max out any one combat art tree (learn Shadowrush, Living Force, Ashina Cross, or High Monk)",
    6708: "Inside the pagoda past the cave near the Main Hall side entrance",
    # Key Items
    50003060: "Given when you first reach the Dilapidated Temple",
    50006160: "Given by Inosuke's Mother",
    50006120: "From the dying Owl in the courtyard up Bamboo Thicket Slope",
    50006232: "From Emma after the eavesdrop chain (Castle Lookout, Old Grave, Dilapidated Temple)",
    51110860: "In Kuro's Room library - opens after you ask Isshin about the Mortal Blade",
    50006236: "From Emma in Kuro's Room after Divine Dragon",
    51500050: "On the cave altar",
    51700000: "After the Guardian Ape fight",
    50006224: "Given by the Divine Child",
    # Mask Fragments
    71001020: "From Pot Noble Harunaga (Hirata), or Koremori in Fountainhead with Truly Precious Bait",
    72501000: "From Pot Noble Koremori (Fountainhead), or Harunaga in Hirata with Truly Precious Bait",
    # Treasure Carp Scales
    51000280: "Behind a rock on the shore before the first bridge",
    51110460: "Underwater in the moat below the Ashina Castle idol",
    51500230: "End of the river by the Mibu Village idol, guarded by a Lone Shadow",
    51700920: "Underwater in the Great Serpent's lake, just before the Riven Cave",
    50006250: "From the Master's Chamberlain after one Precious Bait (or the end of his quest)",
    50006251: "From the Master's Chamberlain after two Precious Baits (or the end of his quest)",
    52500100: "Across the floor hole in Mibu Manor, before the Flower Viewing Stage idol",
    52500120: "Across the floor hole in Mibu Manor, before the Flower Viewing Stage idol",
    52500570: "Across the floor hole in Mibu Manor, before the Flower Viewing Stage idol",
    52500440: "In the submerged building along the right lake wall from Vermilion Bridge",
    52500450: "In the submerged building along the right lake wall from Vermilion Bridge",
    52500460: "In the submerged building along the right lake wall from Vermilion Bridge",
    52500480: "Near the chest guarded by the two underwater Headless",
    52500490: "Near the chest guarded by the two underwater Headless",
}

AREA_ORDER = [
    "Ashina Outskirts", "Hirata Estate", "Ashina Castle", "Ashina Reservoir",
    "Abandoned Dungeon", "Hidden Forest", "Mibu Village", "Ashina Depths",
    "Sunken Valley", "Senpou Temple", "Fountainhead Palace",
    # post-invasion / later-memory world states sort after the normal areas
    "Hirata Estate (Father's Memory)", "Ashina Outskirts (Invasion)",
    "Ashina Castle (Invasion)", "Ashina Reservoir (Invasion)",
]
AREA_INDEX = {name: i for i, name in enumerate(AREA_ORDER)}


def area_rank(area: str) -> int:
    if area in AREA_INDEX:
        return AREA_INDEX[area]
    # fall back to the longest base-area prefix (e.g. "Sunken Valley / ...")
    for name in sorted(AREA_ORDER, key=len, reverse=True):
        if area.startswith(name):
            return AREA_INDEX[name]
    return len(AREA_ORDER)  # unknown areas sort last

# Boss / miniboss defeat flags (author-written from the Sekiro Practice CT's
# flag list; names are ours).
BOSSES = [
    ("Gyoubu Masataka Oniwa", 9301, "Ashina Outskirts"),
    ("Lady Butterfly", 9302, "Hirata Estate"),
    ("Genichiro Ashina", 9303, "Ashina Castle"),
    ("Guardian Ape", 9304, "Sunken Valley"),
    ("Folding Screen Monkeys", 9305, "Senpou Temple"),
    ("Corrupted Monk (Illusion)", 9306, "Mibu Village"),
    ("Great Shinobi - Owl", 9308, "Ashina Castle (Invasion)"),
    ("True Corrupted Monk", 9309, "Fountainhead Palace"),
    ("Divine Dragon", 9310, "Fountainhead Palace"),
    ("Isshin, the Sword Saint", 9312, "Ashina Castle (Invasion)"),
    ("Demon of Hatred", 9313, "Ashina Outskirts (Invasion)"),
    ("Headless Ape", 9314, "Ashina Depths"),
    ("Isshin Ashina", 9316, "Ashina Castle"),
    ("Owl (Father)", 9317, "Hirata Estate (Father's Memory)"),
]
MINIBOSSES = [
    ("Juzou the Drunkard", 11000300, "Hirata Estate"),
    ("Juzou the Drunkard (Revisited)", 11000301, "Hirata Estate (Father's Memory)"),
    ("Shinobi Hunter Enshin of Misen", 11000330, "Hirata Estate"),
    ("Lone Shadow Masanaga the Spear-Bearer (Hirata)", 11000353, "Hirata Estate (Father's Memory)"),
    ("General Naomori Kawarada", 11100300, "Ashina Outskirts"),
    ("Chained Ogre (Outskirts)", 11100310, "Ashina Outskirts"),
    ("General Tenzen Yamauchi", 11100301, "Ashina Outskirts"),
    ("Headless (Ako)", 11100330, "Ashina Outskirts"),
    ("Shigekichi of the Red Guard", 11100480, "Ashina Outskirts (Invasion)"),
    ("Blazing Bull", 11110440, "Ashina Castle"),
    ("General Kuranosuke Matsumoto", 20005340, "Ashina Castle"),
    ("Ashina Elite - Jinsuke Saze", 11110504, "Ashina Castle"),
    ("Chained Ogre (Castle)", 11110620, "Ashina Castle (Invasion)"),
    ("Lone Shadow Masanaga the Spear-Bearer (Castle)", 11110316, "Ashina Castle (Invasion)"),
    ("Lone Shadow Vilehand", 11110305, "Ashina Castle (Invasion)"),
    ("Headless (Ungo)", 11110660, "Ashina Castle"),
    ("Ashina Elite - Ujinari Mizuo", 11110511, "Ashina Castle (Invasion)"),
    ("Leader Shigenori Yamauchi", 11120390, "Ashina Reservoir"),
    ("Seven Ashina Spears - Shikibu Toshikatsu Yamauchi", 11120530, "Ashina Reservoir"),
    ("Seven Ashina Spears - Shume Masaji Oniwa", 11120521, "Ashina Reservoir (Invasion)"),
    ("Lone Shadow Longswordsman", 11120450, "Ashina Reservoir"),
    ("Shichimen Warrior (Abandoned Dungeon)", 11300200, "Abandoned Dungeon"),
    ("Mist Noble", 11500200, "Hidden Forest"),
    ("Headless (Gachiin)", 11500680, "Hidden Forest"),
    ("Tokujiro the Glutton", 11500490, "Ashina Depths"),
    ("O'Rin of the Water", 11500690, "Mibu Village"),
    ("Snake Eyes Shirafuji", 11700200, "Sunken Valley"),
    ("Snake Eyes Shirahagi", 11700201, "Ashina Depths"),
    ("Headless (Gokan)", 11700500, "Sunken Valley"),
    ("Long-arm Centipede Giraffe", 11700425, "Sunken Valley"),
    ("Shichimen Warrior (Guardian Ape's Burrow)", 11700520, "Ashina Depths"),
    ("Armored Warrior", 12000400, "Senpou Temple"),
    ("Long-arm Centipede Sen-Un", 12000279, "Senpou Temple"),
    ("Okami Leader Shizu", 12500406, "Fountainhead Palace"),
    ("Shichimen Warrior (Fountainhead)", 12500580, "Fountainhead Palace"),
    ("Headless (Yashariku)", 12500550, "Fountainhead Palace"),
    ("Sakura Bull of the Palace", 12500570, "Fountainhead Palace"),
]

AREA_NAMES = {
    "ashinaoutskirts": "Ashina Outskirts", "ashinacastle": "Ashina Castle",
    "ashinareservoir": "Ashina Reservoir", "hirata": "Hirata Estate",
    "dungeon": "Abandoned Dungeon", "mibuvillage": "Mibu Village",
    "hiddenforest": "Hidden Forest", "ashinadepths": "Ashina Depths",
    "sunkenvalley": "Sunken Valley", "senpou": "Senpou Temple",
    "fountainhead": "Fountainhead Palace",
}


def pretty_area(raw: str) -> str:
    if not raw:
        return "Unknown"
    # later-memory / post-invasion world states get an explicit label so their
    # drops group separately from the normal-state area
    if raw in ("hirata_courtyard2", "hirata_temple2"):
        return "Hirata Estate (Father's Memory)"
    if "_invasion" in raw:
        base = raw.split("_")[0]
        return f"{AREA_NAMES.get(base, base)} (Invasion)"
    base = raw.replace("_underwater", "").split("_")[0]
    for key, name in AREA_NAMES.items():
        if base.startswith(key):
            return name
    return raw


def make_desc(name: str, debug_line: str, text: str, area_raw: str, diving: bool) -> str:
    """Write an original short description from structured facts only.

    Boss/enemy drops keep the (factual) enemy name; everything else gets a
    generic source+area stub. The annotations' navigation prose is not copied.
    The diving requirement is carried by the `requires` field, not the text, so
    the report can render it as a tag without duplicating it here.
    """
    # source name = text before the first "(" inside the DebugText bracket
    sm = re.search(r"\[([A-Za-z' \-]+?)\s*\(", debug_line)
    source = sm.group(1).strip() if sm else ""
    area = pretty_area(area_raw)
    # 1) explicit "Dropped by X" - the real enemy name (fact)
    dm = re.match(r"Dropped by ([^,.;]+)", text)
    if dm:
        return f"Dropped by {dm.group(1).strip()}"
    # 2) world pickups, identified by the source token (takes precedence over a
    #    stray "for N Sen" from an alternate itemlot on the same line)
    if source in ("Treasure Carp", "Man-eating Carp"):
        return f"Treasure Carp in {area}"
    if source in ("Treasure", "Shiny Treasure", "Chest"):
        return f"{'Chest' if source == 'Chest' else 'Pickup'} in {area}"
    # 3) genuine shop stock: "Merchant (N) for <Sen> Sen"
    if "for " in debug_line and "Sen" in debug_line:
        qm = re.search(r"\((\d+)\)\s*for ", debug_line)
        qty = int(qm.group(1)) if qm else 1
        stack = f" (sells {qty})" if qty > 1 else ""
        return f"From the {source} in {area}{stack}" if source else \
            f"Bought from a merchant in {area}{stack}"
    return f"Found in {area}"


def item_flag(key: str, debug_line: str) -> int | None:
    """Prefer the event flag in the item's own line (shop/purchase items); fall
    back to the slot Key's acquisition flag (world pickups)."""
    evts = re.findall(r"event (7\d{7})", debug_line)
    if evts:
        return int(evts[0])
    parts = key.split(":")
    if len(parts) >= 2:
        try:
            f = int(parts[1])
            if f >= 0:
                return f
        except ValueError:
            pass
    return None


def main() -> None:
    doc = yaml.safe_load(ANNOTATIONS.read_text(encoding="utf-8"))
    slots = doc.get("Slots", [])
    items = []
    seen = set()
    for slot in slots:
        key = slot.get("Key", "")
        debug = slot.get("DebugText") or []
        tags = (slot.get("Tags") or "").split()
        if "unused" in tags or "ng+" in tags:
            continue
        area_raw = slot.get("Area", "")
        text = slot.get("Text", "")
        diving = "_underwater" in area_raw or (
            "nderwater" in text and "surface" not in text)
        # a slot may list several tracked items (e.g. a shop) - emit each once
        for line in debug:
            m = re.match(r"^\s*'?\"?(.*?)'?\"?\s+-\s+\d", line)
            if not m:
                continue
            name = m.group(1).strip().strip("'\"")
            if name not in ITEM_CATEGORIES:
                continue
            flag = item_flag(key, line)
            if flag is None:
                continue
            dedup = (name, flag)
            if dedup in seen:
                continue
            seen.add(dedup)
            items.append({
                "category": ITEM_CATEGORIES[name],
                "name": name,
                "flag": flag,
                "desc": make_desc(name, line, text, area_raw, diving),
                "area": pretty_area(area_raw),
                "requires": DIVING_ABILITY if diving else "",
            })

    for name, flag, area in BOSSES:
        items.append({"category": "Bosses & Memories", "name": name, "flag": flag,
                      "desc": f"Defeat {name}", "area": area, "requires": ""})
    for name, flag, area in MINIBOSSES:
        items.append({"category": "Minibosses", "name": name, "flag": flag,
                      "desc": f"Defeat {name}", "area": area, "requires": ""})

    # apply hand-written location hints over the generic pickup stubs, and mark
    # items whose ownership should be read from inventory (persists across NG+)
    # rather than a give-event flag that resets. Esoteric texts are held items.
    for it in items:
        if it["flag"] in LOCATION_HINTS:
            it["desc"] = LOCATION_HINTS[it["flag"]]
        if it["name"] in ESOTERIC_GOOD_IDS:
            it["item"] = ESOTERIC_GOOD_IDS[it["name"]]

    # order: by category, then game-progression area, then name
    cat_rank = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    items.sort(key=lambda it: (cat_rank.get(it["category"], 99),
                               area_rank(it["area"]), it["name"]))

    counts = {}
    for it in items:
        counts[it["category"]] = counts.get(it["category"], 0) + 1
    print("category counts:")
    for c in CATEGORY_ORDER:
        if c in counts:
            print(f"  {c}: {counts[c]}")
    diving_ct = sum(1 for it in items if it["requires"])
    print(f"total items: {len(items)}  (diving-gated: {diving_ct})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "diving_flag": DIVING_FLAG,
        "diving_ability": DIVING_ABILITY,
        "invasion_flag": INVASION_FLAG,
        "offering_box": OFFERING_BOX,
        "category_order": CATEGORY_ORDER,
        "items": items,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
