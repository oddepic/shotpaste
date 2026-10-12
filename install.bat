@echo off
REM Install Shotpaste for the current user: copy exe to LocalAppData + Startup shortcut.
cd /d %~dp0
set APPDIR=%LOCALAPPDATA%\Shotpaste
mkdir "%APPDIR%" 2>nul
if exist "dist\Shotpaste.exe" (
  copy /y "dist\Shotpaste.exe" "%APPDIR%\Shotpaste.exe" >nul
  echo Installed to %APPDIR%\Shotpaste.exe
) else (
  echo dist\Shotpaste.exe not found. Run build.bat first.
  pause
  exit /b 1
)
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:APPDATA+'\Microsoft\Windows\Start Menu\Programs\Startup\Shotpaste.lnk'); $s.TargetPath=$env:LOCALAPPDATA+'\Shotpaste\Shotpaste.exe'; $s.WorkingDirectory=$env:LOCALAPPDATA+'\Shotpaste'; $s.Save()"
echo Startup shortcut created. Shotpaste will run when you log in.
echo Starting it now...
start "" "%APPDIR%\Shotpaste.exe"
echo Done. Check the system tray for the blue icon.
pause
