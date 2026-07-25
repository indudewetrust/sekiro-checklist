"""Filesystem locations that work both from source and from a PyInstaller exe.

When frozen into a one-file exe, bundled read-only data (checklist.json,
flag_blocks.json) is unpacked to sys._MEIPASS, while writable output (the
working copy of the save, report.html) must go next to the exe. Running from
source, both live in the repo root.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent


def _frozen() -> bool:
    return getattr(sys, "frozen", False)


def data_dir() -> Path:
    """Read-only bundled data (checklist.json, flag_blocks.json)."""
    if _frozen():
        return Path(sys._MEIPASS) / "data"  # type: ignore[attr-defined]
    return _PKG_ROOT / "data"


def app_dir() -> Path:
    """Writable location for work/ copies and report.html."""
    if _frozen():
        return Path(sys.executable).resolve().parent
    return _PKG_ROOT
