"""Sekiro completion checker.

Usage:
    python -m sekiro_checklist [SAVE] [--out report.html] [--no-open]
    python -m sekiro_checklist [SAVE] --serve [PORT]

Finds your save (default: newest S0000.sl2 under %APPDATA%\\Sekiro), copies it
to a working folder (never touches the original), reads the event flags of
every occupied character slot, and produces an HTML checklist of everything
obtained and missing.

Default mode writes report.html once. --serve starts a local web page that
re-reads your save every time you refresh, so you can rest at an idol and hit
Refresh to see updated progress.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import sl2
from .flags import FlagReader
from .inventory import item_counts
from .paths import app_dir, data_dir
from .report import load_checklist, render

ROOT = app_dir()
WORK = ROOT / "work"
DEFAULT_PORT = 8765


def find_save() -> Path | None:
    """Auto-detect the newest S0000.sl2 under %APPDATA%\\Sekiro."""
    sekiro_dir = Path(os.environ.get("APPDATA", "")) / "Sekiro"
    candidates = sorted(sekiro_dir.glob("*/S0000.sl2"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _config_path() -> Path:
    return ROOT / "config.json"


def _remembered_save() -> Path | None:
    p = _config_path()
    if p.exists():
        try:
            sp = Path(json.loads(p.read_text(encoding="utf-8")).get("save_path", ""))
            if sp.exists():
                return sp
        except Exception:
            pass
    return None


def _remember_save(path: Path) -> None:
    try:
        _config_path().write_text(json.dumps({"save_path": str(path)}),
                                  encoding="utf-8")
    except Exception:
        pass


def _pick_save_dialog() -> Path | None:
    """Native 'open file' dialog fallback when auto-detect finds nothing."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        start = Path(os.environ.get("APPDATA", "")) / "Sekiro"
        chosen = filedialog.askopenfilename(
            title="Select your Sekiro save file (S0000.sl2)",
            initialdir=str(start) if start.exists() else str(Path.home()),
            filetypes=[("Sekiro save", "S0000.sl2 *.sl2"), ("All files", "*.*")])
        root.destroy()
        return Path(chosen) if chosen else None
    except Exception:
        return None


def resolve_save(cli_arg: str | None) -> Path | None:
    """Find the save: explicit arg, then a remembered choice, then auto-detect,
    then a file-picker fallback (remembering whatever the user picks)."""
    if cli_arg:
        p = Path(cli_arg)
        return p if p.exists() else None
    for candidate in (_remembered_save(), find_save()):
        if candidate:
            return candidate
    picked = _pick_save_dialog()
    if picked and picked.exists():
        _remember_save(picked)
        return picked
    return None


def generate_html(src: Path, live: bool, log=lambda *a: None) -> str:
    """Copy the save, read every occupied slot, return the report HTML."""
    WORK.mkdir(exist_ok=True)
    copy = WORK / "current-S0000.sl2"  # fixed working copy; overwritten each read
    shutil.copy2(src, copy)

    save = sl2.load(copy)
    bad = [e.name for e in save.entries if not e.checksum_ok]
    if bad:
        log(f"warning: checksum mismatch in {bad}")
    log(f"steam id {save.steam_id}, occupied slots: "
        f"{[s + 1 for s in save.occupied_slots]}")

    data = load_checklist()
    checklist = data["items"]
    invasion_flag = data.get("invasion_flag")
    offering_box = data.get("offering_box", [])

    slot_results, box_status = {}, {}
    for i in save.occupied_slots:
        reader = FlagReader(sl2.flag_section(save.slot(i)))
        inv = item_counts(save.slot(i))
        results = []
        for item in checklist:
            # items with an inventory good id read ownership from the held bag
            # (survives NG+); everything else reads its event flag
            if "item" in item:
                have = inv.get(item["item"], 0) > 0
            else:
                have = reader.get(item["flag"])
            results.append({**item, "have": have})
        have = sum(1 for r in results if r["have"])
        log(f"slot {i + 1}: {have}/{len(results)} obtained")
        slot_results[i] = results

        # Offering Box: after the invasion, missed miniboss drops are buyable
        invaded = bool(reader.get(invasion_flag)) if invasion_flag else False
        avail = [f"{b['name']} ({b['source']})" for b in offering_box
                 if not reader.get(b["flag"])]
        box_status[i] = {"invaded": invaded, "available": avail}

    return render(slot_results, str(src), live=live, box_status=box_status)


def serve(src: Path, port: int) -> int:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] not in ("/", "/index.html"):
                self.send_error(404)
                return
            try:
                body = generate_html(src, live=True).encode("utf-8")
            except Exception as exc:  # keep the server alive on a bad read
                self.send_error(500, f"Could not read save: {exc}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence per-request console spam
            pass

    try:
        httpd = HTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        print(f"Couldn't start on port {port}: {exc}. Try a different --serve PORT.")
        return 1
    url = f"http://127.0.0.1:{port}/"
    print(f"Live checklist running at {url}")
    print("Leave this window open. Rest at an idol, then hit Refresh in the page.")
    print("Close this window (or Ctrl+C) to stop.")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save", nargs="?", help="path to S0000.sl2 (default: auto-detect)")
    ap.add_argument("--out", default=str(ROOT / "report.html"), help="output HTML path")
    ap.add_argument("--no-open", action="store_true", help="don't open the report")
    ap.add_argument("--serve", nargs="?", type=int, const=DEFAULT_PORT, default=None,
                    metavar="PORT",
                    help="run a live page that refreshes from the save (default port 8765)")
    args = ap.parse_args(argv)

    src = resolve_save(args.save)
    if src is None or not src.exists():
        print("No Sekiro save found or selected. Expected it under "
              "%APPDATA%\\Sekiro\\<steamid>\\S0000.sl2, or pick it when prompted.")
        return 1
    if not (data_dir() / "flag_blocks.json").exists():
        print("flag_blocks.json is missing - run tools/build_flag_map.py once "
              "while Sekiro is running to calibrate (see README).")
        return 1

    if args.serve is not None:
        return serve(src, args.serve)

    out = Path(args.out)
    out.write_text(generate_html(src, live=False, log=print), encoding="utf-8")
    print(f"report: {out}")
    if not args.no_open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
