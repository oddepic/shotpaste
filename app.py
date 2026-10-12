"""Shotpaste: double-click tray app. Print Screen shots become Explorer-pastable files."""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

import clip

try:
    from winotify import Notification, audio
    HAS_TOAST = True
except Exception:
    HAS_TOAST = False

try:
    import pystray
    from pystray import MenuItem as item
    HAS_TRAY = True
except Exception:
    HAS_TRAY = False

APP_NAME = "Shotpaste"
CONFIG_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / APP_NAME
SETTINGS_FILE = CONFIG_DIR / "settings.json"
LOG_FILE = CONFIG_DIR / "shotpaste.log"


def log(msg: str):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except Exception:
        pass
    try:
        print(msg, flush=True)
    except Exception:
        pass


def default_save_dir() -> Path:
    return Path.home() / "Pictures" / "Shotpaste"


def load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"settings load failed: {e}")
    return {}


def save_settings(data: dict):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"settings save failed: {e}")


def startup_folder() -> Path:
    return Path(os.getenv("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_shortcut() -> Path:
    return startup_folder() / "Shotpaste.lnk"


def current_exe() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()


def is_run_at_startup() -> bool:
    return startup_shortcut().exists()


def set_run_at_startup(enable: bool) -> bool:
    lnk = startup_shortcut()
    try:
        if not enable:
            if lnk.exists():
                lnk.unlink()
            return True
        lnk.parent.mkdir(parents=True, exist_ok=True)
        target = str(current_exe())
        try:
            from win32com.client import Dispatch

            shell = Dispatch("WScript.Shell")
            sc = shell.CreateShortCut(str(lnk))
            sc.Targetpath = target
            sc.WorkingDirectory = str(Path(target).parent)
            sc.IconLocation = target
            sc.save()
            return True
        except Exception:
            # fallback: plain batch in startup that launches the exe
            fallback = lnk.with_suffix(".bat")
            fallback.write_text(f'start "" "{target}"\n', encoding="utf-8")
            return True
    except Exception as e:
        log(f"startup toggle failed: {e}")
        return False


def ensure_single_instance():
    try:
        import win32event
        import win32api
        from winerror import ERROR_ALREADY_EXISTS

        mutex = win32event.CreateMutex(None, False, "ShotpasteSingleInstance")
        if win32api.GetLastError() == ERROR_ALREADY_EXISTS:
            log("another Shotpaste is already running, exiting")
            sys.exit(0)
        return mutex
    except SystemExit:
        raise
    except Exception as e:
        log(f"single instance check skipped: {e}")
        return None


def make_icon_image(size: int = 64):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (size, size), (37, 99, 235))
    d = ImageDraw.Draw(img)
    d.rectangle([size * 0.22, size * 0.28, size * 0.78, size * 0.72], outline="white", width=max(2, size // 20))
    d.line([size * 0.22, size * 0.44, size * 0.78, size * 0.44], fill="white", width=max(2, size // 32))
    d.ellipse([size * 0.44, size * 0.12, size * 0.56, size * 0.25], fill="white")
    return img


def ensure_icon_files(base: Path):
    try:
        png = base / "icon.png"
        ico = base / "icon.ico"
        if not png.exists() or not ico.exists():
            make_icon_image(256).save(png, "PNG")
            make_icon_image(256).save(ico, "ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except Exception as e:
        log(f"icon build failed: {e}")


def show_toast(title: str, msg: str, folder: Path):
    if not HAS_TOAST:
        return
    try:
        toast = Notification(app_id="Shotpaste", title=title, msg=msg, duration="short")
        toast.set_audio(audio.Default, loop=False)
        toast.add_actions(label="Open folder", launch=str(folder))
        toast.show()
    except Exception as e:
        log(f"toast failed: {e}")


def open_folder(folder: Path):
    try:
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(folder)])
    except Exception as e:
        log(f"could not open folder: {e}")


def pick_folder(current: Path) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(initialdir=str(current), title="Where should screenshots be saved?")
        root.destroy()
        if chosen:
            return Path(chosen)
        return None
    except Exception as e:
        log(f"folder picker failed: {e}")
        return None


def save_screenshot(image: Image.Image, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = folder / f"screenshot-{stamp}.png"
    i = 1
    while path.exists():
        i += 1
        path = folder / f"screenshot-{stamp}-{i}.png"
    image.save(path, "PNG")
    return path


class Watcher:
    def __init__(self, folder: Path, poll_ms: int = 500):
        self.folder = folder
        self.poll = poll_ms / 1000.0
        self.last_hash = None
        self.last_file = None
        self.running = True
        self.paused = False

    def check_once(self) -> Path | None:
        image = clip.get_clipboard_image()
        if image is None:
            return None
        h = clip.image_hash(image)
        if h == self.last_hash:
            return None
        self.last_hash = h
        path = save_screenshot(image, self.folder)
        try:
            clip.set_clipboard_image_and_files(image, [path])
        except Exception as e:
            log(f"clipboard convert failed, file saved anyway: {e}")
        self.last_file = path
        log(f"saved {path.name}, ready to paste in Explorer")
        show_toast("Screenshot ready to paste", f"{path.name} - Ctrl+V works in File Explorer now", self.folder)
        return path

    def loop(self):
        log(f"watching clipboard, saving to {self.folder}")
        while self.running:
            if not self.paused:
                try:
                    self.check_once()
                except Exception as e:
                    log(f"watch error: {e}")
            time.sleep(self.poll)


def run_tray(watcher: Watcher, settings: dict):
    if not HAS_TRAY:
        log("tray unavailable, running headless")
        watcher.loop()
        return

    state = {"paused": False}

    def on_open(icon, _):
        open_folder(watcher.folder)

    def on_change_folder(icon, _):
        picked = pick_folder(watcher.folder)
        if picked:
            watcher.folder = picked
            settings["folder"] = str(picked)
            save_settings(settings)
            log(f"save folder changed to {picked}")
            show_toast("Shotpaste", f"Saving to {picked}", picked)

    def on_pause(icon, _):
        watcher.paused = not watcher.paused
        state["paused"] = watcher.paused
        log("paused" if watcher.paused else "resumed")

    def on_startup(icon, _):
        enable = not is_run_at_startup()
        if set_run_at_startup(enable):
            log(f"run at startup: {enable}")
        icon.update_menu()

    def on_quit(icon, _):
        watcher.running = False
        icon.stop()

    t = threading.Thread(target=watcher.loop, daemon=True)
    t.start()

    show_toast("Shotpaste is running", "Print Screen a shot, then Ctrl+V it in any folder", watcher.folder)

    icon = pystray.Icon(
        "shotpaste",
        make_icon_image(),
        "Shotpaste - Ctrl+V shots in Explorer",
        menu=pystray.Menu(
            item("Open screenshots folder", on_open, default=True),
            item("Change save folder...", on_change_folder),
            item("Start with Windows", on_startup, checked=lambda _: is_run_at_startup()),
            item("Pause", on_pause, checked=lambda _: state["paused"]),
            item("Quit", on_quit),
        ),
    )
    icon.run()


def main():
    import argparse

    ensure_single_instance()
    ensure_icon_files(Path(__file__).parent if not getattr(sys, "frozen", False) else Path(sys.executable).parent)

    ap = argparse.ArgumentParser(description="Shotpaste - paste screenshots as files")
    ap.add_argument("--folder", default=None)
    ap.add_argument("--poll", type=int, default=500)
    ap.add_argument("--no-toast", action="store_true")
    ap.add_argument("--no-tray", action="store_true")
    args, _ = ap.parse_known_args()

    if args.no_toast:
        global HAS_TOAST
        HAS_TOAST = False

    settings = load_settings()
    folder = Path(args.folder) if args.folder else Path(settings.get("folder", str(default_save_dir())))
    folder.mkdir(parents=True, exist_ok=True)

    watcher = Watcher(folder, poll_ms=args.poll)

    if args.no_tray or not HAS_TRAY:
        try:
            watcher.loop()
        except KeyboardInterrupt:
            pass
        return 0
    run_tray(watcher, settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
