"""PyInstaller entry point. Builds to a single console exe.

    pyinstaller --onefile --name "Sekiro Checklist" --add-data "data;data" run.py

Running the exe with no arguments starts the live server (see __main__.serve).
"""
import sys

from sekiro_checklist.__main__ import main

if __name__ == "__main__":
    # default the bare exe to live-server mode (the double-click experience)
    if len(sys.argv) == 1:
        sys.argv.append("--serve")
    sys.exit(main())
