@echo off
REM Build Shotpaste.exe, no console window, double-click ready.
cd /d %~dp0
pip install -r requirements.txt
python -c "from app import ensure_icon_files; from pathlib import Path; ensure_icon_files(Path('.'))"
pyinstaller --noconfirm --onefile --noconsole --name Shotpaste --icon icon.ico --add-data "clip.py;." app.py
echo.
echo Built: dist\Shotpaste.exe
echo Double-click it to run. Look for the blue icon in the system tray.
pause
