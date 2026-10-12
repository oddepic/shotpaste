# Shotpaste

## Summary

Shotpaste watches the Windows clipboard for screenshots and makes them pastable as files in File Explorer with Ctrl+V.

## Install

Download (recommended, no terminal):

1. Get `Shotpaste.exe` from the latest release.
2. Double-click it. The blue icon appears in the system tray.

Or run once at login with `install.bat` from the repo.

From source (Python 3.12 or newer, Windows 10 or 11 64-bit):

```powershell
pip install -r requirements.txt
python app.py
```

## Usage

Smallest check that it works:

```powershell
python app.py --no-tray
```

Then press Print Screen, wait for the toast, and press Ctrl+V in any folder.

Main flow:

1. Double-click `Shotpaste.exe`.
2. Take a shot with Print Screen or Win+Shift+S.
3. Wait for the "Screenshot ready to paste" toast.
4. Open any folder and press Ctrl+V. The PNG is also saved in `Pictures\Shotpaste`.

## How it works

1. The app polls the clipboard for images every 500 ms.
2. A new image hash means a new screenshot, so it saves a PNG.
3. It writes a file reference plus the image back to the clipboard.
4. Explorer accepts the file drop, Paint and Word still accept the image.
5. A toast confirms the file name, the tray icon stays available.

## Stack

| Piece | Choice |
|-------|--------|
| Language | Python 3.12 |
| Clipboard | Pillow, pywin32, ctypes |
| Tray | pystray |
| Toasts | winotify |
| Build | PyInstaller, single file, no console |

## Local run

```powershell
pip install -r requirements.txt
python app.py
```

Options: `--folder` to change the save dir, `--poll` for the interval in ms, `--no-tray` for console mode.

## Structure

```text
app.py        # watcher, tray, toasts, settings
clip.py       # clipboard image read and file drop write
build.bat     # builds dist\Shotpaste.exe
install.bat   # copies exe and adds a Startup shortcut
icon.ico      # app and exe icon
```

## License

MIT, see LICENSE.
