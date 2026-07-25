# Sekiro Completion Checklist

Point it at your **Sekiro: Shadows Die Twice** save and it shows exactly which
collectibles each of your characters has and which they're still missing -
including *where* to find each one. Prayer Beads, Gourd Seeds, Prosthetic Tools,
Esoteric Texts, Ninjutsu, Mask Fragments, Key Items, Treasure Carp Scales,
bosses, and minibosses. 172 tracked items across all 10 categories.

**It only ever reads your save**, from a copy - it never modifies the save or
the game. It's a save-file reader, not a game mod: nothing gets installed into
Sekiro, and it touches nothing while the game runs.

### [Download the latest release](../../releases/latest)

Just want to use it? Grab the exe from the link above. No Python, no install.

## Download & run

1. Grab **`Sekiro Checklist.exe`** from the [Releases](../../releases) page.
2. Double-click it. Your browser opens with the checklist; a small console
   window stays open to keep it live.
3. Play. When you **rest at a Sculptor's Idol** (or quit to the menu) the game
   saves - then hit **↻ Refresh** in the page to see updated progress.

No Python, no install. The exe finds your save automatically under
`%APPDATA%\Sekiro\<steamid>\S0000.sl2`.

> **Why trust it?** The whole thing is open source (this repo). It opens your
> save read-only, works on a *copy* in a `work\` folder, and never writes to the
> save or the game. The one-time calibration tool reads the game's memory with
> `PROCESS_VM_READ` only. Windows SmartScreen may warn about the unsigned exe
> (normal for indie tools) - "More info > Run anyway", or build it yourself
> below.

## Run from source

Pure Python 3, standard library only - no `pip install` needed to run:

```
python -m sekiro_checklist --serve        # live page; Refresh re-reads the save
python -m sekiro_checklist                # write report.html once and open it
python -m sekiro_checklist path\to\S0000.sl2 --out mylist.html --no-open
python -m sekiro_checklist --serve 9000    # live page on a specific port
```

The report has one tab per character slot, a "show missing only" toggle,
per-category counts, and 🤿 tags on pickups that need Mibu Breathing Technique
(diving).

## A note on New Game Plus

Only some flags carry across NG+, so the report labels categories accordingly:

- **Lifetime** (accurate on any save): Prayer Beads, Gourd Seeds, Prosthetic
  Tools, Esoteric Texts, Ninjutsu.
- **This cycle** (reset each NG+): bosses, minibosses, key items, mask
  fragments, and carp-scale *pickups* - the game genuinely strips those items /
  resets those flags when you start a new cycle.

The report auto-detects NG+ characters and shows a banner so the "this cycle"
numbers aren't mistaken for lifetime totals. (Treasure Carp Scales are a
currency that carries over as a count, but the game keeps no per-location record
of them, so the location list is lifetime-accurate only on a first playthrough.)

## How it works

- Sekiro saves are plain **BND4** archives - *not* encrypted (unlike DS2/DS3).
  Each character slot holds a serialized event-flag bitfield (0x80-byte blocks)
  starting at payload offset `0x34`, in the same block order as the game's
  in-memory flag arena.
- A flag id like `9301` or `11100310` maps to a block via its decimal digits and
  a map-region lookup in the game's `EventFlagMan` / `FieldArea` structures.
  `tools/build_flag_map.py` reads that once from a running game into
  `data/flag_blocks.json`; after that the checker works fully offline, for any
  save, on any machine. `tools/extend_flag_map.py` can extend that map to new
  flags without relaunching the game.
- Within a block the game uses a byte-swapped 32-bit layout:
  `byte = block*0x80 + (L>>5)*4 + (3-((L>>3)&3))`, `bit = 7-(L&7)`, `L = flag%1000`.
- Every collectible has a unique acquisition flag, so the checker reports
  *which* ones you're missing, not just how many.

`data/flag_blocks.json` ships with the tool (it's identical for every v1.06
save), so end users never run the calibration. To regenerate it: launch Sekiro
v1.06 in-world and run `python tools\build_flag_map.py`.

## Rebuilding the checklist data (`data/checklist.json`)

`tools/build_checklist.py` regenerates the item list. It reads flag ids, areas,
and enemy names (facts) from the [SoulsRandomizers](https://github.com/thefifthmatt/SoulsRandomizers)
annotations and writes them with **our own descriptions**. That source repo is
not freely licensed and is **not** included here - clone it into `vendor/`
yourself if you want to rebuild. The generated `data/checklist.json` is this
project's own data and ships with the tool.

## Build the exe yourself

```
pip install pyinstaller
pyinstaller --onefile --name "Sekiro Checklist" --add-data "data;data" run.py
```

Output lands in `dist\`.

## Credits

- BND4 save container: [SL2Bonfire](https://github.com/mi5hmash/SL2Bonfire)
  (mi5hmash) and [DS3SaveUnpacker](https://github.com/tremwil/DS3SaveUnpacker).
- Flag-system layout reference: The Grand Archives
  [Elden Ring CT](https://github.com/The-Grand-Archives/Elden-Ring-CT-TGA);
  the exact Sekiro offsets and the digit/FieldArea mapping here were
  reverse-engineered from `GetEventFlag` in the running game.
- `EventFlagMan` / `FieldArea` addresses and boss/idol flag ids:
  [Sekiro-Practice-CT](https://github.com/ElaDiDu/Sekiro-Practice-CT) (ElaDiDu).
- Collectible flag ids and locations cross-referenced from
  [SoulsRandomizers](https://github.com/thefifthmatt/SoulsRandomizers)
  (thefifthmatt); descriptions are original.

## License

MIT - see [LICENSE](LICENSE).
