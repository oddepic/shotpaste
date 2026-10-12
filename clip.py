"""Clipboard helpers for Shotpaste.

Reads screenshot images from the Windows clipboard and writes back
a file reference (CF_HDROP) so Ctrl+V works in File Explorer.
Optionally keeps the image (CF_DIB) so Paint and Word still accept a paste.
"""

import ctypes
from ctypes import wintypes
import io
import struct
from pathlib import Path

from PIL import ImageGrab

CF_HDROP = 15
CF_DIB = 8
GHND = 0x0042

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.restype = wintypes.BOOL
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
user32.CloseClipboard.restype = wintypes.BOOL


def get_clipboard_image():
    """Return a PIL Image if the clipboard holds one, else None."""
    try:
        data = ImageGrab.grabclipboard()
    except Exception:
        return None
    # grabclipboard can return a list of filenames, an Image, or None
    if data is None:
        return None
    if isinstance(data, list):
        return None
    # PIL Image has .tobytes; DIB data also lands here as Image
    if hasattr(data, "tobytes"):
        return data
    return None


def image_hash(image) -> str:
    """Fast hash to detect a new screenshot without comparing full pixels."""
    import hashlib

    thumb = image.copy().convert("RGB").resize((32, 32))
    h = hashlib.md5()
    h.update(str(image.size).encode())
    h.update(thumb.tobytes())
    return h.hexdigest()


def image_to_dib(image) -> bytes:
    """Convert PIL Image to CF_DIB bytes (BMP without the 14 byte header)."""
    out = io.BytesIO()
    image.convert("RGB").save(out, "BMP")
    return out.getvalue()[14:]


def _alloc_moveable(data: bytes):
    size = len(data)
    hmem = kernel32.GlobalAlloc(GHND, size)
    if not hmem:
        raise MemoryError("GlobalAlloc failed")
    locked = kernel32.GlobalLock(hmem)
    if not locked:
        raise MemoryError("GlobalLock failed")
    ctypes.memmove(locked, data, size)
    kernel32.GlobalUnlock(hmem)
    return hmem


def _open_clipboard_retry(tries: int = 10, delay_ms: int = 50) -> None:
    import time

    for i in range(tries):
        if user32.OpenClipboard(None):
            return
        time.sleep(delay_ms / 1000.0)
    raise RuntimeError("Could not open clipboard")


def set_clipboard_files(paths) -> None:
    """Replace clipboard contents with a file list for Explorer pasting."""
    set_clipboard_image_and_files(None, paths)


def set_clipboard_image_and_files(image, paths) -> None:
    """Put CF_HDROP and optionally CF_DIB on the clipboard in one open."""
    abs_paths = [str(Path(p).resolve()) for p in paths]
    file_list = "\0".join(abs_paths) + "\0\0"
    file_bytes = file_list.encode("utf-16-le")

    dropfiles = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    hdrop_blob = dropfiles + file_bytes
    hdrop_mem = _alloc_moveable(hdrop_blob)

    dib_mem = None
    if image is not None:
        dib_mem = _alloc_moveable(image_to_dib(image))

    _open_clipboard_retry()
    try:
        user32.EmptyClipboard()
        if dib_mem:
            if not user32.SetClipboardData(CF_DIB, dib_mem):
                kernel32.GlobalFree(dib_mem)
            else:
                dib_mem = None  # system owns it now
        if not user32.SetClipboardData(CF_HDROP, hdrop_mem):
            raise RuntimeError("SetClipboardData CF_HDROP failed")
        hdrop_mem = None  # system owns it now
    finally:
        user32.CloseClipboard()
        # free only on failure, success memory belongs to the OS
        if hdrop_mem:
            kernel32.GlobalFree(hdrop_mem)
        if dib_mem:
            kernel32.GlobalFree(dib_mem)
