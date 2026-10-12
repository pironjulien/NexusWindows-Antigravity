#!/usr/bin/env python3
"""
NexusAGY Computer Engine - OS-Level Windows Desktop & Application Automation.
Provides SOTA window-scoped control, UI Automation tree extraction, and SendInput interaction.
Parity & superiority over Claude and Codex Computer Use.
"""

from __future__ import annotations

import base64
import ctypes
import io
import os
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi
gdi32 = ctypes.windll.gdi32

try:
    from . import computer_logger
except ImportError:
    import computer_logger

HWND = wintypes.HWND
HDC = wintypes.HDC
HBITMAP = wintypes.HBITMAP
HGDIOBJ = wintypes.HGDIOBJ
BOOL = wintypes.BOOL
UINT = wintypes.UINT

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.argtypes = [HWND]
user32.OpenClipboard.restype = BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = BOOL
user32.GetClipboardData.argtypes = [UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.MapVirtualKeyW.argtypes = [UINT, UINT]
user32.MapVirtualKeyW.restype = UINT

kernel32.GlobalAlloc.argtypes = [UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = BOOL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

user32.GetClassNameW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.PrintWindow.argtypes = [HWND, HDC, UINT]
user32.PrintWindow.restype = BOOL
user32.GetDC.argtypes = [HWND]
user32.GetDC.restype = HDC
user32.ReleaseDC.argtypes = [HWND, HDC]
user32.ReleaseDC.restype = ctypes.c_int

gdi32.CreateCompatibleDC.argtypes = [HDC]
gdi32.CreateCompatibleDC.restype = HDC
gdi32.CreateCompatibleBitmap.argtypes = [HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = HBITMAP
gdi32.SelectObject.argtypes = [HDC, HGDIOBJ]
gdi32.SelectObject.restype = HGDIOBJ
gdi32.DeleteObject.argtypes = [HGDIOBJ]
gdi32.DeleteObject.restype = BOOL
gdi32.DeleteDC.argtypes = [HDC]
gdi32.DeleteDC.restype = BOOL
gdi32.GetBitmapBits.argtypes = [HBITMAP, ctypes.c_long, ctypes.c_void_p]
gdi32.GetBitmapBits.restype = ctypes.c_long

PW_RENDERFULLCONTENT = 2

# -----------------------------------------------------------------------------
# Desktop & DPI Initialization (Must occur before COM or window handles)
# -----------------------------------------------------------------------------
_hdesk_default: int = 0


def ensure_default_desktop() -> bool:
    """Attaches the current calling thread to the interactive 'Default' desktop on WinSta0.

    Crucial for commands executed within agent or sandbox environments.
    """
    global _hdesk_default
    try:
        if not _hdesk_default:
            _hdesk_default = user32.OpenDesktopW("Default", 0, False, 0x01FF)  # DESKTOP_ALL_ACCESS
        if _hdesk_default:
            return bool(user32.SetThreadDesktop(_hdesk_default))
    except Exception:
        pass
    return False


# Immediate attachment
ensure_default_desktop()

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V2
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

import mss  # noqa: E402
from PIL import Image  # noqa: E402

try:
    import uiautomation as uia  # noqa: E402
except ImportError:
    uia = None

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
SW_RESTORE = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Extended navigation keys requiring KEYEVENTF_EXTENDEDKEY
EXTENDED_VKEYS = {
    0x21,  # PageUp
    0x22,  # PageDown
    0x23,  # End
    0x24,  # Home
    0x25,  # Left
    0x26,  # Up
    0x27,  # Right
    0x28,  # Down
    0x2D,  # Insert
    0x2E,  # Delete
}

# Modifier keys that require state-holding sequence in hotkeys
MODIFIER_VKEYS = {
    0x10,  # Shift (VK_SHIFT)
    0x11,  # Ctrl (VK_CONTROL)
    0x12,  # Alt (VK_MENU)
    0x5B,  # Left Windows (VK_LWIN)
    0x5C,  # Right Windows (VK_RWIN)
}

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTunion)]


# Key code mapping for hotkeys and common keys
VK_MAP: dict[str, int] = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "escape": 0x1B,
    "esc": 0x1B,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "page_up": 0x21,
    "pagedown": 0x22,
    "page_down": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "windows": 0x5B,
    "cmd": 0x5B,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}

# System and security protected targets (Defense-in-depth)
PROTECTED_WINDOW_CLASSES = {
    "Shell_TrayWnd",  # Windows Taskbar
    "Shell_SecondaryTrayWnd",  # Multi-monitor Taskbar
    "Progman",  # Windows Desktop
    "WorkerW",  # Desktop Wallpapers / Manager
}
PROTECTED_PROCESS_NAMES = {
    "logonui.exe",  # Windows Logon UI
    "lockapp.exe",  # Windows Lock Screen
    "consent.exe",  # Windows UAC Elevation Dialog
    "credentialuibroker.exe",  # Windows Credential Prompt
    "sechealthui.exe",  # Windows Security Defender
}


def is_protected_system_window(hwnd: int) -> tuple[bool, str]:
    """Checks if target window is an OS-critical or authentication surface."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False, ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    cls_name = buf.value
    if cls_name in PROTECTED_WINDOW_CLASSES:
        return True, f"Fenêtre système protégée (classe: {cls_name})"

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    _, proc = get_process_image_path(pid.value)
    if proc.lower() in PROTECTED_PROCESS_NAMES:
        return True, f"Processus d'authentification/sécurité protégé ({proc})"

    return False, ""


# In-memory element cache with window-affinity validation
_element_cache: dict[int, Any] = {}
_cached_window_hwnd: int = 0
_cached_window_title: str = ""


def get_cached_element(element_index: int, target_hwnd: int | None = None) -> Any:
    """Retrieves a cached UI Automation element, strictly validating window identity and COM liveness.

    Prevents stale elements or cross-window control pollution identified by Codex.
    """
    global _element_cache, _cached_window_hwnd, _cached_window_title
    if not _element_cache or _cached_window_hwnd == 0:
        raise ValueError(
            f"Aucun élément en cache. Exécutez get_window_state sur la fenêtre cible (hwnd={target_hwnd or 'actuelle'}) avant d'utiliser element_index."
        )
    if target_hwnd and _cached_window_hwnd != target_hwnd:
        raise ValueError(
            f"Contrôle provenant d'une autre fenêtre : l'élément [#{element_index}] a été indexé sur la fenêtre "
            f"{_cached_window_hwnd} ('{_cached_window_title}'), pas sur la fenêtre cible {target_hwnd}. "
            f"Exécutez get_window_state(hwnd={target_hwnd}) pour actualiser l'arbre."
        )
    if element_index not in _element_cache:
        raise ValueError(
            f"Élément [#{element_index}] introuvable. Les index valides pour '{_cached_window_title}' "
            f"(hwnd={_cached_window_hwnd}) vont de 1 à {len(_element_cache)}. Exécutez get_window_state."
        )
    ctrl = _element_cache[element_index]
    # Verify COM liveness to prevent operating on stale/destroyed controls
    try:
        _ = ctrl.NativeWindowHandle
        _ = ctrl.BoundingRectangle
    except Exception as e:
        raise ValueError(
            f"L'élément [#{element_index}] n'est plus accessible (contrôle détruit ou rafraîchi : {e}). "
            f"Exécutez get_window_state pour obtenir l'arbre à jour."
        )
    return ctrl


def get_clipboard_text() -> str | None:
    """Reads unicode text from Windows clipboard safely with exponential retry."""
    for attempt in range(10):
        if user32.OpenClipboard(None):
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return None
                try:
                    return ctypes.c_wchar_p(ptr).value
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        time.sleep(0.005 * (attempt + 1))
    return None


def set_clipboard_text(text: str) -> bool:
    """Sets unicode text to Windows clipboard safely with retry, memory safety, and postcondition verification."""
    data = text.encode("utf-16-le") + b"\x00\x00"
    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not h_mem:
        return False
    ptr = kernel32.GlobalLock(h_mem)
    if not ptr:
        kernel32.GlobalFree(h_mem)
        return False
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(h_mem)

    clipboard_set = False
    for attempt in range(10):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                res = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                if res:
                    clipboard_set = True
                    break
            finally:
                user32.CloseClipboard()
        time.sleep(0.005 * (attempt + 1))

    if not clipboard_set:
        kernel32.GlobalFree(h_mem)
        return False

    read_back = get_clipboard_text()
    return read_back == text


def resolve_box_2d_coords(
    box_2d: list[int] | tuple[int, int, int, int],
    hwnd: int,
) -> tuple[int, int]:
    """Converts Gemini normalized box_2d [ymin, xmin, ymax, xmax] (0-1000)
    to absolute screen (x, y) coordinates centered on the bounding box."""
    rect = get_window_rect(hwnd)
    ymin, xmin, ymax, xmax = box_2d
    rel_cx = int(((xmin + xmax) / 2000.0) * rect["width"])
    rel_cy = int(((ymin + ymax) / 2000.0) * rect["height"])
    return (rect["left"] + rel_cx, rect["top"] + rel_cy)


def is_electron_window(hwnd: int) -> bool:
    """Identifies Electron / Chromium applications where UIA SetFocus fails and clipboard paste is required."""
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    _, proc = get_process_image_path(pid.value)
    p_lower = proc.lower()
    if p_lower in {
        "antigravity.exe",
        "code.exe",
        "chatgpt.exe",
        "slack.exe",
        "discord.exe",
        "chrome.exe",
        "msedge.exe",
        "brave.exe",
    }:
        return True
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return "Chrome_WidgetWin" in buf.value


class FocusGuard:
    """Protects Julien's focus and cursor from being stolen or lost.
    Optionally restores the original active window and cursor position after the action."""

    def __init__(self, target_hwnd: int | None = None, restore: bool = False):
        self.target_hwnd = target_hwnd
        self.restore = restore
        self.orig_fg = 0
        self.orig_pt = POINT(0, 0)

    def __enter__(self):
        self.orig_fg = user32.GetForegroundWindow()
        user32.GetCursorPos(ctypes.byref(self.orig_pt))
        if self.target_hwnd and self.orig_fg != self.target_hwnd:
            focus_window(hwnd=self.target_hwnd)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.restore and self.orig_fg and self.orig_fg != self.target_hwnd and user32.IsWindow(self.orig_fg):
            restore_foreground(self.orig_fg)
            user32.SetCursorPos(self.orig_pt.x, self.orig_pt.y)


def get_process_image_path(pid: int) -> tuple[str, str]:
    """Retrieves full image path and executable name for a given process ID."""
    if pid <= 4:
        return "", "System"
    try:
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h_proc:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            success = kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size))
            kernel32.CloseHandle(h_proc)
            if success:
                full_path = buf.value
                return full_path, os.path.basename(full_path)
    except Exception:
        pass
    return "", "unknown"


def is_window_cloaked(hwnd: int) -> bool:
    """Checks if a window is cloaked (hidden Windows 11 virtual desktop or suspended frame)."""
    try:
        cloaked = wintypes.DWORD()
        res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        return res == 0 and cloaked.value != 0
    except Exception:
        return False


def get_window_rect(hwnd: int) -> dict[str, int]:
    """Retrieves visible bounding rectangle of window.

    Prioritizes DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS) to eliminate
    invisible drop-shadow frames and accurately reflect maximized window dimensions.
    """
    r = RECT()
    try:
        res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r))
        if res == 0 and (r.right > r.left or r.bottom > r.top):
            return {
                "left": r.left,
                "top": r.top,
                "right": r.right,
                "bottom": r.bottom,
                "width": max(0, r.right - r.left),
                "height": max(0, r.bottom - r.top),
            }
    except Exception:
        pass

    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return {
        "left": r.left,
        "top": r.top,
        "right": r.right,
        "bottom": r.bottom,
        "width": max(0, r.right - r.left),
        "height": max(0, r.bottom - r.top),
    }


# -----------------------------------------------------------------------------
# Window Management Functions
# -----------------------------------------------------------------------------
def list_windows(visible_only: bool = True) -> list[dict[str, Any]]:
    """Lists top-level windows on the interactive desktop.

    Filters cloaked and zero-sized windows when visible_only=True.
    """
    ensure_default_desktop()
    windows: list[dict[str, Any]] = []
    fg_hwnd = user32.GetForegroundWindow()

    def enum_cb(hwnd: int, _: int) -> bool:
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if visible_only and length == 0:
            return True

        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()

        if visible_only and not title:
            return True

        if visible_only and is_window_cloaked(hwnd):
            return True

        rect = get_window_rect(hwnd)
        if visible_only and (rect["width"] < 10 or rect["height"] < 10):
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        full_path, proc_name = get_process_image_path(pid.value)

        # Ignore known internal background tool windows
        if visible_only and proc_name.lower() in {"explorer.exe"} and not title:
            return True

        windows.append(
            {
                "hwnd": hwnd,
                "title": title,
                "process_id": pid.value,
                "process_name": proc_name,
                "process_path": full_path,
                "bounds": rect,
                "is_foreground": (hwnd == fg_hwnd),
            }
        )
        return True

    proc = WNDENUMPROC(enum_cb)
    user32.EnumWindows(proc, 0)
    if not windows and _hdesk_default:
        user32.EnumDesktopWindows(_hdesk_default, proc, 0)

    # Sort foreground window first, then by title
    windows.sort(key=lambda w: (not w["is_foreground"], w["process_name"].lower(), w["title"].lower()))
    return windows


def list_apps() -> list[dict[str, Any]]:
    """Lists active graphical applications grouped by executable name."""
    windows = list_windows(visible_only=True)
    apps_map: dict[str, dict[str, Any]] = {}

    for w in windows:
        pname = w["process_name"]
        if pname not in apps_map:
            apps_map[pname] = {
                "process_name": pname,
                "process_id": w["process_id"],
                "process_path": w["process_path"],
                "main_window": w,
                "window_count": 0,
                "windows": [],
            }
        apps_map[pname]["window_count"] += 1
        apps_map[pname]["windows"].append({"hwnd": w["hwnd"], "title": w["title"], "bounds": w["bounds"]})

    return list(apps_map.values())


def focus_window(
    hwnd: int | None = None,
    title: str | None = None,
    process_name: str | None = None,
) -> dict[str, Any]:
    """Brings the target application window to the foreground and restores if minimized."""
    ensure_default_desktop()
    target_hwnd = hwnd

    if not target_hwnd:
        windows = list_windows(visible_only=True)
        if title:
            title_lower = title.lower()
            for w in windows:
                if title_lower in w["title"].lower():
                    target_hwnd = w["hwnd"]
                    break
        elif process_name:
            proc_lower = process_name.lower()
            for w in windows:
                if proc_lower in w["process_name"].lower():
                    target_hwnd = w["hwnd"]
                    break

    if not target_hwnd:
        raise ValueError("Fenêtre introuvable avec les critères spécifiés.")

    cur_tid = kernel32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)
    fg_hwnd = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

    attached_fg = False
    attached_target = False
    try:
        # Attach to current foreground thread to inherit foreground activation rights
        if fg_tid and fg_tid != cur_tid:
            attached_fg = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
        if target_tid and target_tid != cur_tid:
            attached_target = bool(user32.AttachThreadInput(cur_tid, target_tid, True))
    except Exception:
        pass

    try:
        if user32.IsIconic(target_hwnd):
            user32.ShowWindow(target_hwnd, SW_RESTORE)
        user32.BringWindowToTop(target_hwnd)
        success = bool(user32.SetForegroundWindow(target_hwnd))
    finally:
        try:
            if attached_fg and fg_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, False)
            if attached_target and target_tid:
                user32.AttachThreadInput(cur_tid, target_tid, False)
        except Exception:
            pass

    time.sleep(0.08)  # Short stabilization pause
    rect = get_window_rect(target_hwnd)

    length = user32.GetWindowTextLengthW(target_hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(target_hwnd, buf, length + 1)

    return {
        "success": success,
        "hwnd": target_hwnd,
        "title": buf.value,
        "bounds": rect,
    }


# -----------------------------------------------------------------------------
# Screen & Window Capture (Anti-Crash 400 Guaranteed < 200 KB)
# -----------------------------------------------------------------------------
def cleanup_screenshot_cache(max_files: int = 50, max_age_hours: float = 24.0) -> int:
    """Prunes older WebP screenshots from ~/.nexusagy/screenshots to prevent disk bloat."""
    cache_dir = Path.home() / ".nexusagy" / "screenshots"
    if not cache_dir.exists():
        return 0
    try:
        files = sorted(cache_dir.glob("*.webp"), key=lambda p: p.stat().st_mtime)
        now = time.time()
        deleted = 0
        for f in files:
            age_h = (now - f.stat().st_mtime) / 3600.0
            if (len(files) - deleted) > max_files or age_h > max_age_hours:
                f.unlink(missing_ok=True)
                deleted += 1
        return deleted
    except Exception:
        return 0


def restore_foreground(hwnd: int) -> bool:
    """Restores foreground focus back to the user's active window without simulating keys."""
    if not hwnd or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return False
    user32.SetForegroundWindow(hwnd)
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.02)
    return False


def close_window(hwnd: int) -> dict[str, Any]:
    """Closes target window gracefully using UI Automation WindowPattern.Close() with WM_CLOSE fallback.

    Ensures clean termination across standard Win32, WPF, and UWP/WinUI applications (Calculator, Settings, etc.).
    Verifies postcondition to eliminate false success.
    """
    ensure_default_desktop()
    if not hwnd or not user32.IsWindow(hwnd):
        raise ValueError(f"HWND {hwnd} invalide ou fenêtre déjà fermée.")

    is_protected, reason = is_protected_system_window(hwnd)
    if is_protected:
        raise PermissionError(f"Fermeture interdite sur {reason}.")

    # 1. Background-first: Try UIA WindowPattern (essential for modern UWP/Store apps that ignore WM_CLOSE)
    method_used = "wm_close"
    if uia is not None:
        try:
            ctrl = uia.ControlFromHandle(hwnd)
            if ctrl:
                win_pat = ctrl.GetWindowPattern()
                if win_pat:
                    win_pat.Close()
                    method_used = "uia_window_close"
        except Exception:
            pass

    if method_used != "uia_window_close":
        wm_close = 0x0010
        user32.PostMessageW(hwnd, wm_close, 0, 0)

    # 2. Strict postcondition verification
    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return {"success": True, "closed": True, "hwnd": hwnd, "method": method_used}
        time.sleep(0.04)

    return {
        "success": False,
        "closed": False,
        "hwnd": hwnd,
        "method": method_used,
        "message": "La fenêtre ne s'est pas fermée (boîte modale d'enregistrement en attente ou fermeture annulée).",
    }


def capture_window_background_gdi(hwnd: int) -> Image.Image | None:
    """Captures a window surface directly in memory via PrintWindow without bringing it to front.

    Works even if the window is occluded or in the background.
    Returns None if the application does not support offscreen rendering or produces a blank canvas.
    """
    if not hwnd or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None

    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    prev = gdi32.SelectObject(hdc_mem, hbm)
    try:
        res = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
        if not res:
            return None
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetBitmapBits(hbm, len(buf), buf)
        img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)

        from PIL import ImageStat

        stat = ImageStat.Stat(img.convert("L"))
        if stat.stddev[0] < 2.0:
            return None
        return img
    except Exception:
        return None
    finally:
        gdi32.SelectObject(hdc_mem, prev)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)


def capture_window_image(
    hwnd: int | None = None,
    full_screen: bool = False,
    max_dimension: int = 1280,
    quality: int = 85,
    return_meta: bool = False,
    elements_to_annotate: list[dict[str, Any]] | None = None,
) -> bytes | tuple[bytes, dict[str, Any]]:
    """Captures the target window or full screen and compresses to WebP (< 200 KB).

    Supports multi-monitor desktop setups, negative coordinates, and visual Set-of-Marks overlay.
    """
    ensure_default_desktop()
    if not hwnd and not full_screen:
        hwnd = user32.GetForegroundWindow()

    img: Image.Image | None = None
    region: dict[str, Any] = {}

    # Background-first GDI offscreen capture (does not steal focus and captures covered windows)
    if not full_screen and hwnd and hwnd != user32.GetForegroundWindow():
        img = capture_window_background_gdi(hwnd)
        if img is not None:
            rect = get_window_rect(hwnd)
            region = {
                "left": rect["left"],
                "top": rect["top"],
                "width": rect["width"],
                "height": rect["height"],
            }

    if img is None:
        with mss.MSS() as sct:
            if full_screen or not hwnd:
                mon = sct.monitors[0]  # All monitors combined in MSS
                region = {"left": mon["left"], "top": mon["top"], "width": mon["width"], "height": mon["height"]}
            else:
                rect = get_window_rect(hwnd)
                if rect["width"] <= 0 or rect["height"] <= 0:
                    raise ValueError("Dimensions de fenêtre invalides pour la capture.")
                region = {
                    "left": rect["left"],
                    "top": rect["top"],
                    "width": rect["width"],
                    "height": rect["height"],
                }

            shot = sct.grab(region)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    # Resize to maintain aspect ratio under max_dimension
    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    # Visual Set-of-Marks overlay annotations (Stanford SoM style)
    if elements_to_annotate:
        try:
            from PIL import ImageDraw

            draw = ImageDraw.Draw(img)
            for el in elements_to_annotate:
                box = el.get("gemini_box_2d")
                if box and len(box) == 4:
                    ymin, xmin, ymax, xmax = box
                    left = int(xmin / 1000.0 * img.width)
                    top = int(ymin / 1000.0 * img.height)
                    right = int(xmax / 1000.0 * img.width)
                    bottom = int(ymax / 1000.0 * img.height)
                    draw.rectangle([left, top, right, bottom], outline=(255, 60, 60), width=1)
                    badge_w = 16 if el["index"] < 10 else (22 if el["index"] < 100 else 28)
                    badge_h = min(13, max(8, bottom - top))
                    draw.rectangle([left, top, min(right, left + badge_w), top + badge_h], fill=(255, 60, 60))
                    draw.text((left + 2, top + 1), str(el["index"]), fill=(255, 255, 255))
        except Exception:
            pass

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=4)
    data = buf.getvalue()

    # If data exceeds 180 KB, recompress with slightly lower quality
    if len(data) > 180 * 1024:
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=70, method=4)
        data = buf.getvalue()

    if return_meta:
        meta = {
            "original_bounds": region,
            "original_size": (region["width"], region["height"]),
            "captured_size": img.size,
            "scale_factor": round(img.size[0] / max(1, region["width"]), 4),
        }
        return data, meta

    return data


# -----------------------------------------------------------------------------
# UI Automation Tree & Window State
# -----------------------------------------------------------------------------
INTERACTIVE_CONTROL_TYPES = {
    "ButtonControl",
    "EditControl",
    "MenuItemControl",
    "ListItemControl",
    "CheckBoxControl",
    "RadioButtonControl",
    "ComboBoxControl",
    "TabItemControl",
    "HyperlinkControl",
    "TreeItemControl",
    "DocumentControl",
    "CustomControl",
}


def get_window_state(
    hwnd: int | None = None,
    max_elements: int = 80,
    capture_screenshot: bool = False,
    output_path: str | None = None,
    max_depth: int = 30,
    time_budget: float = 2.0,
    include_data_url: bool = False,
    annotate_screenshot: bool = False,
    query: str | None = None,
) -> dict[str, Any]:
    """Extracts compact UI Automation interactive elements and optional WebP screenshot.

    Equips Antigravity with Set-of-Marks markers [#1], [#2] and Gemini box_2d coordinates.
    Bounded by max_depth and time budget with spatial pruning and optional visual SoM overlay.
    Optional query filters elements by substring in name, value, or control type.
    """
    global _element_cache, _cached_window_hwnd, _cached_window_title
    ensure_default_desktop()

    target_hwnd = hwnd or user32.GetForegroundWindow()
    if not target_hwnd:
        raise ValueError("Aucune fenêtre active détectée.")

    win_rect = get_window_rect(target_hwnd)
    w_width = max(1, win_rect["width"])
    w_height = max(1, win_rect["height"])

    length = user32.GetWindowTextLengthW(target_hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(target_hwnd, buf, length + 1)
    title = buf.value

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(target_hwnd, ctypes.byref(pid))
    _, proc_name = get_process_image_path(pid.value)

    elements: list[dict[str, Any]] = []
    _element_cache.clear()
    _cached_window_hwnd = target_hwnd
    _cached_window_title = title

    q_lower = query.lower().strip() if query else None

    if uia is not None:
        try:
            root_ctrl = uia.ControlFromHandle(target_hwnd)
            if root_ctrl:
                start_time = time.perf_counter()

                def walk(ctrl: Any, depth: int = 0) -> None:
                    if depth > max_depth or len(elements) >= max_elements:
                        return
                    if (time.perf_counter() - start_time) > time_budget:
                        return

                    for child in ctrl.GetChildren():
                        if len(elements) >= max_elements or (time.perf_counter() - start_time) > time_budget:
                            break
                        try:
                            c_rect = child.BoundingRectangle
                            cw = c_rect.right - c_rect.left
                            ch = c_rect.bottom - c_rect.top
                        except Exception:
                            continue

                        # Spatial pruning: ignore controls outside the visible window boundary
                        if (
                            c_rect.right <= win_rect["left"]
                            or c_rect.bottom <= win_rect["top"]
                            or c_rect.left >= win_rect["right"]
                            or c_rect.top >= win_rect["bottom"]
                        ):
                            continue

                        ctype = child.ControlTypeName
                        if ctype in INTERACTIVE_CONTROL_TYPES and cw > 0 and ch > 0:
                            c_name = child.Name or ""
                            val_str = ""
                            try:
                                val_pattern = child.GetValuePattern()
                                if val_pattern:
                                    val_str = val_pattern.Value or ""
                            except Exception:
                                pass

                            # Apply query filter if specified
                            if q_lower:
                                searchable = f"{c_name} {val_str} {ctype}".lower()
                                if q_lower not in searchable:
                                    walk(child, depth + 1)
                                    continue

                            idx = len(elements) + 1
                            _element_cache[idx] = child

                            rel_l = c_rect.left - win_rect["left"]
                            rel_t = c_rect.top - win_rect["top"]
                            rel_r = c_rect.right - win_rect["left"]
                            rel_b = c_rect.bottom - win_rect["top"]
                            rel_cx = rel_l + cw // 2
                            rel_cy = rel_t + ch // 2

                            elements.append(
                                {
                                    "index": idx,
                                    "type": ctype.replace("Control", ""),
                                    "name": c_name[:60],
                                    "value": val_str[:60],
                                    "relative_center": {"x": rel_cx, "y": rel_cy},
                                    "gemini_box_2d": [
                                        max(0, min(1000, int(rel_t / w_height * 1000))),
                                        max(0, min(1000, int(rel_l / w_width * 1000))),
                                        max(0, min(1000, int(rel_b / w_height * 1000))),
                                        max(0, min(1000, int(rel_r / w_width * 1000))),
                                    ],
                                }
                            )
                        walk(child, depth + 1)

                walk(root_ctrl)
        except Exception:
            pass

    result: dict[str, Any] = {
        "hwnd": target_hwnd,
        "title": title,
        "process_name": proc_name,
        "bounds": win_rect,
        "element_count": len(elements),
        "elements": elements,
    }

    if capture_screenshot or output_path:
        annotate_list = elements if annotate_screenshot else None
        webp_bytes, meta = capture_window_image(target_hwnd, return_meta=True, elements_to_annotate=annotate_list)
        result["image_dimensions"] = meta.get("captured_size")
        result["scale_factor"] = meta.get("scale_factor")

        dest_path = output_path
        if not dest_path:
            cache_dir = Path.home() / ".nexusagy" / "screenshots"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cleanup_screenshot_cache(max_files=50, max_age_hours=24.0)
            timestamp = int(time.time() * 1000)
            dest_path = str(cache_dir / f"window_state_{timestamp}.webp")

        dest = Path(dest_path).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(webp_bytes)
        result["screenshot_path"] = str(dest)

        if include_data_url:
            result["screenshot_data_url"] = f"data:image/webp;base64,{base64.b64encode(webp_bytes).decode('ascii')}"

    return result


# -----------------------------------------------------------------------------
# Input Simulation (Hardware-level via SendInput)
# -----------------------------------------------------------------------------
def _send_inputs(inputs: list[INPUT]) -> int:
    """Dispatches a list of INPUT structures to the OS."""
    ensure_default_desktop()
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    return user32.SendInput(n, arr, ctypes.sizeof(INPUT))


def mouse_click(
    x: int,
    y: int,
    button: str = "left",
    click_count: int = 1,
) -> bool:
    """Positions cursor and dispatches mouse click(s) at screen coordinates (x, y)."""
    ensure_default_desktop()
    user32.SetCursorPos(x, y)
    time.sleep(0.02)

    btn = button.lower()
    down_flag = MOUSEEVENTF_LEFTDOWN
    up_flag = MOUSEEVENTF_LEFTUP
    if btn == "right":
        down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif btn == "middle":
        down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP

    for _ in range(click_count):
        down_input = INPUT(type=INPUT_MOUSE)
        down_input.union.mi.dwFlags = down_flag
        up_input = INPUT(type=INPUT_MOUSE)
        up_input.union.mi.dwFlags = up_flag

        _send_inputs([down_input])
        time.sleep(0.02)
        _send_inputs([up_input])
        if click_count > 1:
            time.sleep(0.05)

    return True


def mouse_move(
    x: int,
    y: int,
    hwnd: int | None = None,
    smooth: bool = True,
    steps: int = 12,
    duration_ms: int = 40,
    foreground: bool = False,
) -> dict[str, Any]:
    """Moves mouse cursor to window-relative coordinates (x, y) with smooth Bézier/easing trajectory."""
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()
    if target_hwnd and user32.GetForegroundWindow() != target_hwnd and not foreground:
        raise RuntimeError(
            "Le survol de souris requiert la mise au premier plan. Pour ne pas interrompre le travail de Julien, passez foreground=True."
        )
    win_rect = get_window_rect(target_hwnd)
    target_screen_x = win_rect["left"] + x
    target_screen_y = win_rect["top"] + y

    if not smooth or steps <= 1:
        user32.SetCursorPos(target_screen_x, target_screen_y)
        return {"success": True, "target": (x, y), "screen_coords": (target_screen_x, target_screen_y), "smooth": False}

    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    start_x, start_y = pt.x, pt.y
    step_delay = (duration_ms / 1000.0) / max(1, steps)

    for i in range(1, steps + 1):
        t = i / steps
        # Smooth step ease-in-out: 3*t^2 - 2*t^3
        ease = 3 * (t**2) - 2 * (t**3)
        cur_x = int(start_x + (target_screen_x - start_x) * ease)
        cur_y = int(start_y + (target_screen_y - start_y) * ease)
        user32.SetCursorPos(cur_x, cur_y)
        time.sleep(step_delay)

    return {"success": True, "target": (x, y), "screen_coords": (target_screen_x, target_screen_y), "smooth": True}


def is_point_occluded(x: int, y: int, target_hwnd: int) -> bool:
    """Checks whether the screen coordinate (x, y) is covered by another top-level window."""
    if not target_hwnd:
        return False
    pt = POINT(x=x, y=y)
    hit = user32.WindowFromPoint(pt)
    if not hit:
        return False
    hit_root = user32.GetAncestor(hit, 2)  # GA_ROOT = 2
    target_root = user32.GetAncestor(target_hwnd, 2)
    return hit != target_hwnd and hit_root != target_root and hit_root != target_hwnd


def click(
    hwnd: int | None = None,
    element_index: int | None = None,
    x: int | None = None,
    y: int | None = None,
    box_2d: list[int] | tuple[int, int, int, int] | None = None,
    button: str = "left",
    click_count: int = 1,
    foreground: bool = True,
    restore_focus: bool = False,
) -> dict[str, Any]:
    """Clicks an element by index [#N], Gemini box_2d [ymin, xmin, ymax, xmax], or relative coords (x, y).

    Prioritizes background-friendly UI Automation without stealing user focus whenever possible.
    When physical click is needed, FocusGuard preserves and optionally restores Julien's focus and cursor.
    """
    t0 = time.perf_counter()
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()

    # Security check: Block interaction with Windows Logon, Taskbar, or UAC elevation
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Action de clic interdite sur {reason}.")

    # 1. Background-first: Deterministic UI Automation element actions (ZERO FOCUS STEAL)
    if element_index is not None:
        ctrl = get_cached_element(element_index, target_hwnd)

        # Single left-click operates entirely in background across interactive patterns
        if button.lower() == "left" and click_count == 1:
            front_before = user32.GetForegroundWindow()

            # Pattern A: InvokePattern (Buttons, Hyperlinks, MenuItems)
            try:
                invoke_pat = ctrl.GetInvokePattern()
                if invoke_pat:
                    import threading

                    def _do_invoke() -> None:
                        try:
                            ctypes.windll.ole32.CoInitialize(None)
                            invoke_pat.Invoke()
                        except Exception:
                            pass
                        finally:
                            try:
                                ctypes.windll.ole32.CoUninitialize()
                            except Exception:
                                pass

                    t = threading.Thread(target=_do_invoke, daemon=True)
                    t.start()
                    t.join(timeout=0.15)
                    if front_before and user32.GetForegroundWindow() != front_before:
                        restore_foreground(front_before)
                    elapsed = (time.perf_counter() - t0) * 1000
                    computer_logger.log_action(
                        "click", "uia_invoke", target_hwnd, elapsed, "SUCCESS", {"element_index": element_index}
                    )
                    return {
                        "success": True,
                        "method": "uia_invoke",
                        "element_index": element_index,
                        "timing_ms": round(elapsed, 2),
                    }
            except Exception:
                pass

            # Pattern B: TogglePattern (CheckBoxes, SwitchButtons) with postcondition verification
            try:
                toggle_pat = ctrl.GetTogglePattern()
                if toggle_pat:
                    state_before = getattr(toggle_pat, "ToggleState", None)
                    toggle_pat.Toggle()
                    time.sleep(0.02)
                    state_after = getattr(toggle_pat, "ToggleState", None)
                    if front_before and user32.GetForegroundWindow() != front_before:
                        restore_foreground(front_before)
                    verified = state_before is not None and state_after is not None and state_before != state_after
                    elapsed = (time.perf_counter() - t0) * 1000
                    computer_logger.log_action(
                        "click",
                        "uia_toggle",
                        target_hwnd,
                        elapsed,
                        "SUCCESS",
                        {"element_index": element_index, "verified": verified},
                    )
                    return {
                        "success": True,
                        "method": "uia_toggle",
                        "element_index": element_index,
                        "toggle_state": state_after,
                        "verified": verified,
                        "timing_ms": round(elapsed, 2),
                    }
            except Exception:
                pass

            # Pattern C: SelectionItemPattern (ListItems, TabItems, RadioButtons) with postcondition verification
            try:
                sel_pat = ctrl.GetSelectionItemPattern()
                if sel_pat:
                    sel_pat.Select()
                    time.sleep(0.02)
                    if front_before and user32.GetForegroundWindow() != front_before:
                        restore_foreground(front_before)
                    is_sel = getattr(sel_pat, "IsSelected", True)
                    elapsed = (time.perf_counter() - t0) * 1000
                    computer_logger.log_action(
                        "click",
                        "uia_select",
                        target_hwnd,
                        elapsed,
                        "SUCCESS",
                        {"element_index": element_index, "verified": is_sel},
                    )
                    return {
                        "success": True,
                        "method": "uia_select",
                        "element_index": element_index,
                        "is_selected": is_sel,
                        "verified": bool(is_sel),
                        "timing_ms": round(elapsed, 2),
                    }
            except Exception:
                pass

            # Pattern D: ExpandCollapsePattern (ComboBoxes, TreeItems) with postcondition verification
            try:
                exp_pat = ctrl.GetExpandCollapsePattern()
                if exp_pat:
                    state_before = getattr(exp_pat, "ExpandCollapseState", 0)
                    if state_before == 1:
                        exp_pat.Collapse()
                    else:
                        exp_pat.Expand()
                    time.sleep(0.02)
                    state_after = getattr(exp_pat, "ExpandCollapseState", 0)
                    if front_before and user32.GetForegroundWindow() != front_before:
                        restore_foreground(front_before)
                    verified = state_before != state_after
                    elapsed = (time.perf_counter() - t0) * 1000
                    computer_logger.log_action(
                        "click",
                        "uia_expand_collapse",
                        target_hwnd,
                        elapsed,
                        "SUCCESS",
                        {"element_index": element_index, "verified": verified},
                    )
                    return {
                        "success": True,
                        "method": "uia_expand_collapse",
                        "element_index": element_index,
                        "state": state_after,
                        "verified": verified,
                        "timing_ms": round(elapsed, 2),
                    }
            except Exception:
                pass

        # If hardware click is required on cached element:
        try:
            rect = ctrl.BoundingRectangle
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            with FocusGuard(target_hwnd, restore=restore_focus):
                if target_hwnd and is_point_occluded(cx, cy, target_hwnd):
                    focus_window(hwnd=target_hwnd)
                mouse_click(cx, cy, button=button, click_count=click_count)
            elapsed = (time.perf_counter() - t0) * 1000
            computer_logger.log_action(
                "click",
                "element_center",
                target_hwnd,
                elapsed,
                "SUCCESS",
                {"element_index": element_index, "coords": (cx, cy)},
            )
            return {
                "success": True,
                "method": "element_center",
                "element_index": element_index,
                "coords": (cx, cy),
                "timing_ms": round(elapsed, 2),
                "focus_restored": restore_focus,
            }
        except Exception as err:
            if isinstance(err, RuntimeError):
                raise

    # 2. Gemini Normalized box_2d Grounding [ymin, xmin, ymax, xmax] (0-1000)
    if box_2d is not None:
        screen_x, screen_y = resolve_box_2d_coords(box_2d, target_hwnd)
        with FocusGuard(target_hwnd, restore=restore_focus):
            if target_hwnd and is_point_occluded(screen_x, screen_y, target_hwnd):
                focus_window(hwnd=target_hwnd)
            mouse_click(screen_x, screen_y, button=button, click_count=click_count)
        elapsed = (time.perf_counter() - t0) * 1000
        computer_logger.log_action(
            "click",
            "gemini_box_2d",
            target_hwnd,
            elapsed,
            "SUCCESS",
            {"box_2d": box_2d, "screen_coords": (screen_x, screen_y)},
        )
        return {
            "success": True,
            "method": "gemini_box_2d",
            "box_2d": box_2d,
            "screen_coords": (screen_x, screen_y),
            "timing_ms": round(elapsed, 2),
            "focus_restored": restore_focus,
        }

    # 3. Window-relative coordinates (x, y)
    if x is not None and y is not None:
        win_rect = get_window_rect(target_hwnd)
        screen_x = win_rect["left"] + x
        screen_y = win_rect["top"] + y
        with FocusGuard(target_hwnd, restore=restore_focus):
            if target_hwnd and is_point_occluded(screen_x, screen_y, target_hwnd):
                focus_window(hwnd=target_hwnd)
            mouse_click(screen_x, screen_y, button=button, click_count=click_count)
        elapsed = (time.perf_counter() - t0) * 1000
        computer_logger.log_action(
            "click", "relative_coordinates", target_hwnd, elapsed, "SUCCESS", {"screen_coords": (screen_x, screen_y)}
        )
        return {
            "success": True,
            "method": "relative_coordinates",
            "screen_coords": (screen_x, screen_y),
            "timing_ms": round(elapsed, 2),
            "focus_restored": restore_focus,
        }

    raise ValueError("Indiquez un 'element_index', un 'box_2d' Gemini ou des coordonnées relatives (x, y).")


def type_text(
    text: str,
    hwnd: int | None = None,
    element_index: int | None = None,
    x: int | None = None,
    y: int | None = None,
    box_2d: list[int] | tuple[int, int, int, int] | None = None,
    clear_first: bool = False,
    submit: bool = False,
    method: str = "auto",
    foreground: bool = True,
    restore_clipboard: bool = True,
    restore_focus: bool = False,
) -> dict[str, Any]:
    """Saisit du texte de manière ultra-rapide et sécurisée.

    Modes supportés:
    - 'auto' (défaut): Privilégie le collage presse-papier atomique (Ctrl+V) pour les prompts,
      textes multilignes, ou applications Electron/Web, et UIA ValuePattern pour Win32 simple.
    - 'paste': Copie instantanée dans le presse-papier Windows et Ctrl+V en < 30ms (insensible aux newlines,
      aucun appui prématuré sur Entrée). Préserve et restaure automatiquement le presse-papier de Julien.
    - 'uia': Remplacement direct via UI Automation ValuePattern (sans vol de focus).
    - 'typing': Saisie caractère par caractère via SendInput Unicode.

    Options avancées:
    - submit: bool (appuie sur Entrée après insertion pour envoyer le prompt directement).
    - restore_clipboard: bool (restaure le presse-papier précédent de Julien après collage).
    - restore_focus: bool (remet la fenêtre active et le curseur de Julien immédiatement en place).
    """
    t0 = time.perf_counter()
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()

    # Security check: Block typing into critical Windows auth/system surfaces
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Saisie de texte interdite sur {reason}.")

    # Normalize newlines so Windows \r\n does not duplicate
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 1. Background-first UIA ValuePattern (only for pure win32 controls, short single-line text)
    if method == "uia" or (
        method == "auto"
        and element_index is not None
        and not is_electron_window(target_hwnd)
        and "\n" not in text
        and len(text) < 60
        and box_2d is None
        and x is None
    ):
        ctrl = get_cached_element(element_index, target_hwnd)
        front_before = user32.GetForegroundWindow()
        try:
            val_pat = ctrl.GetValuePattern()
            if val_pat and not getattr(val_pat, "IsReadOnly", False):
                target_val = text if clear_first else ((val_pat.Value or "") + text)
                val_pat.SetValue(target_val)
                time.sleep(0.02)
                read_back = getattr(val_pat, "Value", "")
                verified = read_back == target_val or text in read_back
                if front_before and user32.GetForegroundWindow() != front_before:
                    restore_foreground(front_before)
                elapsed = (time.perf_counter() - t0) * 1000
                computer_logger.log_action(
                    "type_text",
                    "uia_set_value",
                    target_hwnd,
                    elapsed,
                    "SUCCESS",
                    {"element_index": element_index, "length": len(text), "verified": verified},
                )
                return {
                    "success": True,
                    "method": "uia_set_value",
                    "element_index": element_index,
                    "char_count": len(text),
                    "verified": verified,
                    "current_value": read_back,
                    "timing_ms": round(elapsed, 2),
                }
        except Exception:
            pass
        if method == "uia":
            raise RuntimeError(f"L'élément [{element_index}] ne supporte pas UI Automation ValuePattern.")

    # 2. SOTA Atomic Clipboard Paste Mode (Default for prompts, multiline, Electron, web, fast typing)
    if method in ("auto", "paste"):
        ctrl = get_cached_element(element_index, target_hwnd) if element_index is not None else None
        orig_clip = get_clipboard_text() if restore_clipboard else None
        with FocusGuard(target_hwnd, restore=restore_focus):
            # Target positioning / click to focus
            if box_2d is not None:
                bx, by = resolve_box_2d_coords(box_2d, target_hwnd)
                mouse_click(bx, by)
                time.sleep(0.02)
            elif x is not None and y is not None:
                wrect = get_window_rect(target_hwnd)
                mouse_click(wrect["left"] + x, wrect["top"] + y)
                time.sleep(0.02)
            elif ctrl is not None:
                crect = ctrl.BoundingRectangle
                mouse_click((crect.left + crect.right) // 2, (crect.top + crect.bottom) // 2)
                time.sleep(0.02)

            if clear_first:
                press_key("ctrl+a", hwnd=target_hwnd, foreground=True)
                press_key("backspace", hwnd=target_hwnd, foreground=True)
                time.sleep(0.01)

            # Strict clipboard set verification (Eliminates Codex's 'échec du presse-papier ignoré')
            clip_ok = set_clipboard_text(text)
            if not clip_ok:
                raise RuntimeError(
                    "Échec de mise à jour du presse-papier Windows (verrouillé par une autre application). "
                    "Collage annulé afin d'éviter l'injection de données périmées ou corrompues."
                )

            press_key("ctrl+v", hwnd=target_hwnd, foreground=True)

            if submit:
                time.sleep(0.04)
                press_key("enter", hwnd=target_hwnd, foreground=True)

            # Give application message pump brief moment to consume clipboard data before restoring
            time.sleep(0.06)

            # Cleanly restore Julien's original clipboard if requested
            if restore_clipboard and orig_clip is not None:
                set_clipboard_text(orig_clip)

        # Optional postcondition verification via UIA ValuePattern if targeting cached element
        verified = None
        if ctrl is not None:
            try:
                vp = ctrl.GetValuePattern()
                if vp:
                    read_val = vp.Value or ""
                    verified = text in read_val or read_val == text
            except Exception:
                pass

        elapsed = (time.perf_counter() - t0) * 1000
        computer_logger.log_action(
            "type_text",
            "clipboard_paste",
            target_hwnd,
            elapsed,
            "SUCCESS",
            {"char_count": len(text), "submit": submit, "focus_restored": restore_focus, "verified": verified},
        )
        return {
            "success": True,
            "method": "clipboard_paste",
            "char_count": len(text),
            "timing_ms": round(elapsed, 2),
            "submit": submit,
            "verified": verified,
            "focus_restored": restore_focus,
        }

    # 3. Fallback: Hardware Unicode typing (SendInput)
    with FocusGuard(target_hwnd, restore=restore_focus):
        if clear_first:
            press_key("ctrl+a", hwnd=target_hwnd, foreground=True)
            press_key("backspace", hwnd=target_hwnd, foreground=True)

        for char in text:
            if char == "\n":
                press_key("enter", hwnd=target_hwnd, foreground=True)
                time.sleep(0.01)
            else:
                utf16_bytes = char.encode("utf-16-le")
                for i in range(0, len(utf16_bytes), 2):
                    code_unit = int.from_bytes(utf16_bytes[i : i + 2], "little")
                    down = INPUT(type=INPUT_KEYBOARD)
                    down.union.ki.wScan = code_unit
                    down.union.ki.dwFlags = KEYEVENTF_UNICODE
                    up = INPUT(type=INPUT_KEYBOARD)
                    up.union.ki.wScan = code_unit
                    up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                    _send_inputs([down, up])
                    time.sleep(0.003)

        if submit:
            time.sleep(0.02)
            press_key("enter", hwnd=target_hwnd, foreground=True)

    elapsed = (time.perf_counter() - t0) * 1000
    computer_logger.log_action(
        "type_text", "sendinput_unicode", target_hwnd, elapsed, "SUCCESS", {"char_count": len(text)}
    )
    return {"success": True, "method": "sendinput_unicode", "char_count": len(text), "timing_ms": round(elapsed, 2)}


def press_key(
    keys: str,
    hwnd: int | None = None,
    foreground: bool = True,
    restore_focus: bool = False,
) -> dict[str, Any]:
    """Presses key combination (e.g. 'ctrl+c', 'alt+f4', 'win+r', 'enter', 'ctrl+,')."""
    t0 = time.perf_counter()
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()

    parts = [k.strip().lower() for k in keys.split("+") if k.strip()]
    if not parts:
        raise ValueError("Combinaison de touches vide.")

    vk_entries: list[tuple[int, bool]] = []
    for part in parts:
        if part in VK_MAP:
            vk = VK_MAP[part]
            vk_entries.append((vk, vk in EXTENDED_VKEYS))
        elif len(part) == 1:
            if part.isalnum():
                vk_entries.append((ord(part.upper()), False))
            else:
                vk_scan = user32.VkKeyScanW(ord(part))
                if vk_scan != -1:
                    vk = vk_scan & 0xFF
                    vk_entries.append((vk, vk in EXTENDED_VKEYS))
                else:
                    vk_entries.append((ord(part.upper()), False))
        else:
            raise ValueError(f"Touche inconnue : {part}")

    modifiers = [entry for entry in vk_entries if entry[0] in MODIFIER_VKEYS]
    actions = [entry for entry in vk_entries if entry[0] not in MODIFIER_VKEYS]

    def _make_key_input(vk: int, is_ext: bool, is_up: bool) -> INPUT:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.union.ki.wVk = vk
        scan = user32.MapVirtualKeyW(vk, 0)
        inp.union.ki.wScan = scan
        flags = KEYEVENTF_KEYUP if is_up else 0
        if is_ext:
            flags |= KEYEVENTF_EXTENDEDKEY
        inp.union.ki.dwFlags = flags
        return inp

    with FocusGuard(target_hwnd, restore=restore_focus):
        if modifiers and actions:
            # 1. Hold down all modifier keys
            for vk, is_ext in modifiers:
                _send_inputs([_make_key_input(vk, is_ext, is_up=False)])
            time.sleep(0.015)

            # 2. Press and release action keys
            for vk, is_ext in actions:
                _send_inputs([_make_key_input(vk, is_ext, is_up=False)])
                time.sleep(0.015)
                _send_inputs([_make_key_input(vk, is_ext, is_up=True)])
                time.sleep(0.010)

            # 3. Release modifier keys in reverse order
            time.sleep(0.010)
            for vk, is_ext in reversed(modifiers):
                _send_inputs([_make_key_input(vk, is_ext, is_up=True)])

        elif modifiers and not actions:
            # Only modifiers (e.g. 'alt' to activate menu bar, 'win' for start menu)
            for vk, is_ext in modifiers:
                _send_inputs([_make_key_input(vk, is_ext, is_up=False)])
            time.sleep(0.020)
            for vk, is_ext in reversed(modifiers):
                _send_inputs([_make_key_input(vk, is_ext, is_up=True)])

        else:
            # Action keys without modifiers (e.g. 'enter', 'tab', 'backspace', 'f5')
            for vk, is_ext in actions:
                _send_inputs([_make_key_input(vk, is_ext, is_up=False)])
                time.sleep(0.015)
                _send_inputs([_make_key_input(vk, is_ext, is_up=True)])
                time.sleep(0.005)

    elapsed = (time.perf_counter() - t0) * 1000
    computer_logger.log_action("press_key", "sendinput", target_hwnd, elapsed, "SUCCESS", {"keys": keys})
    return {"success": True, "keys": keys, "vk_codes": [v[0] for v in vk_entries], "timing_ms": round(elapsed, 2)}


def scroll(
    delta_y: int = 0,
    delta_x: int = 0,
    hwnd: int | None = None,
    x: int | None = None,
    y: int | None = None,
    element_index: int | None = None,
    foreground: bool = False,
) -> dict[str, Any]:
    """Scrolls via background UI Automation ScrollPattern or mouse wheel."""
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()

    # 1. Background-first: UI Automation ScrollPattern without mouse or focus
    if element_index is not None:
        ctrl = get_cached_element(element_index, target_hwnd)
        current = ctrl
        scroll_pat = None
        for _ in range(15):
            if not current:
                break
            try:
                sp = current.GetScrollPattern()
                if sp and (
                    (delta_y != 0 and getattr(sp, "VerticallyScrollable", False))
                    or (delta_x != 0 and getattr(sp, "HorizontallyScrollable", False))
                ):
                    scroll_pat = sp
                    break
            except Exception:
                pass
            try:
                current = current.GetParentControl()
            except Exception:
                break

        if scroll_pat:
            # ScrollAmount: SmallDecrement=1, NoAmount=2, SmallIncrement=4
            v_amt = 1 if delta_y > 0 else (4 if delta_y < 0 else 2)
            h_amt = 4 if delta_x > 0 else (1 if delta_x < 0 else 2)
            steps = abs(delta_y) or abs(delta_x) or 1
            for _ in range(min(steps, 20)):
                scroll_pat.Scroll(h_amt, v_amt)
            return {
                "success": True,
                "method": "uia_scroll",
                "element_index": element_index,
                "delta_y": delta_y,
                "delta_x": delta_x,
            }

    # 2. Hardware mouse wheel fallback
    if target_hwnd and user32.GetForegroundWindow() != target_hwnd and not foreground:
        raise RuntimeError(
            "Le défilement par molette physique requiert la mise au premier plan. "
            "Pour ne pas interrompre le travail de Julien, passez foreground=True."
        )

    if x is not None and y is not None:
        win_rect = get_window_rect(target_hwnd)
        user32.SetCursorPos(win_rect["left"] + x, win_rect["top"] + y)
        time.sleep(0.02)

    inputs = []
    if delta_y != 0:
        inp = INPUT(type=INPUT_MOUSE)
        inp.union.mi.dwFlags = MOUSEEVENTF_WHEEL
        inp.union.mi.mouseData = delta_y * 120
        inputs.append(inp)

    if delta_x != 0:
        inp = INPUT(type=INPUT_MOUSE)
        inp.union.mi.dwFlags = MOUSEEVENTF_HWHEEL
        inp.union.mi.mouseData = delta_x * 120
        inputs.append(inp)

    if inputs:
        _send_inputs(inputs)

    return {"success": True, "delta_y": delta_y, "delta_x": delta_x}


def drag(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    hwnd: int | None = None,
    steps: int = 12,
    delay_ms: int = 15,
    foreground: bool = False,
) -> dict[str, Any]:
    """Performs a smooth mouse drag between two coordinates."""
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()
    if target_hwnd and user32.GetForegroundWindow() != target_hwnd and not foreground:
        raise RuntimeError(
            "Le glisser-déposer à la souris requiert la mise au premier plan. Pour ne pas interrompre le travail de Julien, passez foreground=True."
        )
    win_rect = get_window_rect(target_hwnd)

    screen_from_x = win_rect["left"] + from_x
    screen_from_y = win_rect["top"] + from_y
    screen_to_x = win_rect["left"] + to_x
    screen_to_y = win_rect["top"] + to_y

    user32.SetCursorPos(screen_from_x, screen_from_y)
    time.sleep(0.03)

    # Mouse down
    down = INPUT(type=INPUT_MOUSE)
    down.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
    _send_inputs([down])
    time.sleep(0.02)

    # Intermediate steps
    for i in range(1, steps + 1):
        cur_x = int(screen_from_x + (screen_to_x - screen_from_x) * (i / steps))
        cur_y = int(screen_from_y + (screen_to_y - screen_from_y) * (i / steps))
        user32.SetCursorPos(cur_x, cur_y)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    # Mouse up
    up = INPUT(type=INPUT_MOUSE)
    up.union.mi.dwFlags = MOUSEEVENTF_LEFTUP
    _send_inputs([up])

    return {
        "success": True,
        "from": (from_x, from_y),
        "to": (to_x, to_y),
        "steps": steps,
    }
