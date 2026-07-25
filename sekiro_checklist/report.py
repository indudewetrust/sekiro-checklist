"""Render the collectible checklist for one or more save slots as HTML."""
from __future__ import annotations

import html
import json
from datetime import datetime

from .paths import data_dir

DATA_DIR = data_dir()

# Categories whose flags persist across NG+ (lifetime-accurate on any save).
# Everything else resets each NG+ cycle and is labelled as current-cycle.
LIFETIME = {"Prayer Beads", "Gourd Seeds", "Prosthetic Tools",
            "Esoteric Texts", "Ninjutsu"}

# categories whose items have distinct meaningful names (shown before the desc);
# beads/seeds/carp scales are all one item, bosses already name themselves
NAMED = {"Prosthetic Tools", "Key Items", "Ninjutsu",
         "Esoteric Texts", "Mask Fragments"}

DEFAULT_ORDER = [
    "Prayer Beads", "Gourd Seeds", "Prosthetic Tools", "Esoteric Texts",
    "Ninjutsu", "Mask Fragments", "Key Items", "Treasure Carp Scales",
    "Bosses & Memories", "Minibosses",
]

CSS = """
:root { --bg:#14100d; --panel:#1e1813; --ink:#e8ddcb; --dim:#8d8272;
        --gold:#c9a45c; --red:#9c2b23; --green:#5a7d4a; --line:#352c22;
        --blue:#4a6d8d; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.5 Georgia, 'Times New Roman', serif; }
.wrap { max-width:900px; margin:0 auto; padding:24px 16px 80px; }
h1 { font-size:26px; letter-spacing:2px; color:var(--gold);
     border-bottom:2px solid var(--gold); padding-bottom:10px; }
h1 small { color:var(--dim); font-size:14px; letter-spacing:0; }
.tabs { display:flex; gap:8px; margin:18px 0; flex-wrap:wrap; }
.tab { padding:7px 16px; background:var(--panel); border:1px solid var(--line);
       color:var(--ink); cursor:pointer; font:inherit; }
.tab.active { border-color:var(--gold); color:var(--gold); }
.ngplus { background:rgba(74,109,141,.15); border:1px solid var(--blue);
          padding:10px 14px; margin:6px 0 18px; font-size:13.5px; color:var(--ink); }
.ngplus b { color:var(--blue); }
.obox { border:1px solid var(--line); padding:10px 14px; margin:0 0 18px;
        font-size:13.5px; background:var(--panel); }
.obox.live { border-color:var(--gold); }
.obox.live b { color:var(--gold); }
.obox.pending, .obox.empty { color:var(--dim); }
.obox ul { margin:6px 0 0; padding-left:22px; }
.obox li { margin:2px 0; }
.summary { display:flex; gap:10px; flex-wrap:wrap; margin:14px 0 22px; }
.stat { background:var(--panel); border:1px solid var(--line);
        padding:10px 14px; min-width:150px; flex:1; }
.stat b { display:block; font-size:13px; color:var(--dim); font-weight:normal; }
.stat span { font-size:20px; color:var(--gold); }
.bar { height:5px; background:var(--line); margin-top:7px; }
.bar i { display:block; height:100%; background:var(--gold); }
.controls { margin:10px 0 18px; color:var(--dim); display:flex;
            align-items:center; gap:14px; flex-wrap:wrap; }
.controls label { cursor:pointer; user-select:none; }
.refresh { font:inherit; background:var(--gold); color:#14100d; border:none;
           padding:7px 16px; cursor:pointer; border-radius:3px; font-weight:bold; }
.refresh:hover { filter:brightness(1.12); }
.livehint { color:var(--dim); font-size:12.5px; }
details { background:var(--panel); border:1px solid var(--line); margin:10px 0; }
summary { padding:10px 14px; cursor:pointer; font-size:17px; color:var(--gold);
          display:flex; justify-content:space-between; align-items:center; gap:10px; }
summary .cat { display:flex; align-items:baseline; gap:10px; }
summary .cyc { font-size:11px; color:var(--blue); letter-spacing:.5px;
               border:1px solid var(--blue); padding:1px 6px; border-radius:3px; }
summary .count { font-size:13px; color:var(--dim); }
summary .count.done { color:var(--green); }
table { width:100%; border-collapse:collapse; }
td { padding:7px 12px; border-top:1px solid var(--line); vertical-align:top; }
td.mark { width:30px; text-align:center; font-size:16px; }
tr.have td.mark { color:var(--green); }
tr.miss td.mark { color:var(--red); }
tr.have td { color:var(--dim); }
tr.unknown td.mark { color:var(--dim); }
td.area { width:170px; color:var(--dim); font-size:13px; }
td.desc { font-size:13.5px; }
.iname { color:var(--gold); font-weight:600; }
.dive { color:var(--blue); font-size:12px; white-space:nowrap; }
tr.have td.desc, tr.have td.area { opacity:.6; }
body.missing-only tr.have { display:none; }
.foot { margin-top:30px; color:var(--dim); font-size:12.5px;
        border-top:1px solid var(--line); padding-top:12px; }
"""

JS = """
function showSlot(n) {
  document.querySelectorAll('.slotview').forEach(d => d.style.display='none');
  document.getElementById('slot'+n).style.display='';
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab'+n).classList.add('active');
}
function toggleMissing(cb) {
  document.body.classList.toggle('missing-only', cb.checked);
}
"""


def load_checklist() -> dict:
    """Return the full checklist data (items plus meta like offering_box)."""
    return json.loads((DATA_DIR / "checklist.json").read_text(encoding="utf-8"))


def _category_order() -> list[str]:
    data = json.loads((DATA_DIR / "checklist.json").read_text(encoding="utf-8"))
    return data.get("category_order", DEFAULT_ORDER)


def _is_ngplus(results: list[dict]) -> bool:
    """Heuristic: near-complete lifetime collectibles but almost no boss kills
    this cycle => New Game Plus. (A first playthrough can't reach ~all the
    permanent pickups without having killed most bosses, so high-lifetime +
    low-bosses is a reliable NG+ signature and won't fire on early saves.)"""
    life = sum(1 for r in results if r["category"] in LIFETIME and r["have"])
    life_total = sum(1 for r in results if r["category"] in LIFETIME)
    bosses = sum(1 for r in results
                 if r["category"] == "Bosses & Memories" and r["have"])
    if not life_total:
        return False
    return life / life_total >= 0.8 and bosses <= 3


def _stat(label: str, h: int, t: int) -> str:
    pct = round(100 * h / t) if t else 0
    return (f'<div class="stat"><b>{label}</b><span>{h} / {t}</span>'
            f'<div class="bar"><i style="width:{pct}%"></i></div></div>')


def _offering_box(box: dict | None) -> str:
    """Render the Offering Box panel: what missed miniboss drops are buyable."""
    if not box or not box.get("invaded"):
        return ('<div class="obox pending">&#128220; <b>Offering Box</b> opens '
                'at the Dilapidated Temple after the Ashina invasion.</div>')
    avail = box.get("available") or []
    if not avail:
        return ('<div class="obox empty">&#128220; <b>Offering Box</b> is open. '
                'Nothing left to buy, you collected every miniboss drop.</div>')
    rows = "".join(f"<li>{html.escape(a)}</li>" for a in avail)
    return (f'<div class="obox live">&#128220; <b>Offering Box</b> (Dilapidated '
            f'Temple), buy the drops you skipped:<ul>{rows}</ul></div>')


def _slot_view(slot_index: int, results: list[dict], order: list[str],
               box: dict | None, visible: bool) -> str:
    cats: dict[str, list[dict]] = {}
    for r in results:
        cats.setdefault(r["category"], []).append(r)

    life = [r for r in results if r["category"] in LIFETIME]
    life_have = sum(1 for r in life if r["have"])
    beads = cats.get("Prayer Beads", [])
    beads_have = sum(1 for r in beads if r["have"])

    out = [f'<div class="slotview" id="slot{slot_index}"'
           f'{"" if visible else " style=\"display:none\""}>']

    if _is_ngplus(results):
        out.append(
            '<div class="ngplus"><b>New Game Plus detected.</b> Lifetime '
            'collectibles (beads, gourd seeds, prosthetic tools, texts, '
            'ninjutsu) carry over and are accurate. Categories marked '
            '<span class="cyc">THIS CYCLE</span> reset every NG+: bosses, '
            'key items, mask fragments and carp-scale pickups will show what '
            'you’ve done since entering this cycle, not lifetime.</div>')

    out.append('<div class="summary">')
    out.append(_stat("Lifetime collectibles", life_have, len(life)))
    out.append(_stat("Prayer Beads", beads_have, len(beads)))
    out.append('</div>')

    out.append(_offering_box(box))

    for cat in order:
        rows = cats.get(cat)
        if not rows:
            continue
        h = sum(1 for r in rows if r["have"])
        done = " done" if h == len(rows) else ""
        cyc = "" if cat in LIFETIME else '<span class="cyc">THIS CYCLE</span>'
        out.append(
            f'<details open><summary><span class="cat">{html.escape(cat)}{cyc}'
            f'</span><span class="count{done}">{h} / {len(rows)}</span></summary>')
        out.append('<table>')
        for r in rows:
            if r["have"] is None:
                cls, mark = "unknown", "?"
            elif r["have"]:
                cls, mark = "have", "&#10003;"
            else:
                cls, mark = "miss", "&#10007;"
            dive = ('<span class="dive">&#128658; needs diving</span>'
                    if r.get("requires") else "")
            name = (f'<b class="iname">{html.escape(r["name"])}:</b> '
                    if r["category"] in NAMED else "")
            out.append(
                f'<tr class="{cls}"><td class="mark">{mark}</td>'
                f'<td class="area">{html.escape(r["area"])}</td>'
                f'<td class="desc">{name}{html.escape(r["desc"])} {dive}</td></tr>')
        out.append('</table></details>')
    out.append('</div>')
    return "".join(out)


def render(slot_results: dict[int, list[dict]], save_path: str,
           live: bool = False, box_status: dict | None = None) -> str:
    """slot_results: {slot_index: [{category,name,flag,desc,area,requires,have}]}

    live=True adds an in-page Refresh button (for --serve mode, where reloading
    re-reads the save) and a reminder that the game only saves at idols.
    """
    order = _category_order()
    slots = sorted(slot_results)
    tabs, views = [], []
    for n, s in enumerate(slots):
        results = slot_results[s]
        life = sum(1 for r in results if r["category"] in LIFETIME and r["have"])
        life_t = sum(1 for r in results if r["category"] in LIFETIME)
        tabs.append(f'<button class="tab{" active" if n == 0 else ""}" '
                    f'id="tab{s}" onclick="showSlot({s})">'
                    f'Save slot {s + 1} &nbsp;({life}/{life_t})</button>')
        box = (box_status or {}).get(s)
        views.append(_slot_view(s, results, order, box, visible=n == 0))

    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    refresh = (
        '<button class="refresh" onclick="location.reload()">&#8635; Refresh</button>'
        '<span class="livehint">Rest at a Sculptor\'s Idol (or quit to menu) to '
        'save your game, then hit Refresh.</span>' if live else
        '<span class="livehint">(slot totals count lifetime collectibles)</span>')
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sekiro Completion Checklist</title>
<style>{CSS}</style></head>
<body>
<div class="wrap">
<h1>SEKIRO Completion Checklist<br>
<small>{html.escape(save_path)} &middot; generated {when}</small></h1>
<div class="tabs">{''.join(tabs)}</div>
<div class="controls">{refresh}
<label><input type="checkbox" onchange="toggleMissing(this)">
 Show missing only</label></div>
{''.join(views)}
<div class="foot">Read from your save file, read-only. &#10003; obtained &middot;
&#10007; missing &middot; &#128658; requires Mibu Breathing Technique (diving).<br>
Reads Sekiro's event-flag data directly from the save.</div>
</div>
<script>{JS}</script>
</body></html>"""
