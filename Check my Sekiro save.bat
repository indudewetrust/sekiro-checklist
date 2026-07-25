@echo off
REM Double-click launcher for the Sekiro completion checker.
REM Opens a live page in your browser. Rest at a Sculptor's Idol (or quit to
REM the menu) to save your game, then hit Refresh in the page to update.
REM Keep this window open while you use it; close it to stop.
cd /d "%~dp0"
python -m sekiro_checklist --serve
if errorlevel 1 (
  echo.
  echo Something went wrong. Make sure Python 3 is installed and on your PATH.
  pause
)
