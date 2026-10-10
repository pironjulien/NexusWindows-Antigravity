"""Windows desktop engine for Claude: window-scoped capture, UI Automation and SendInput.

Every coordinate exchanged with the model is a pixel of the image returned for the current
target (a window's visible frame, or the whole virtual screen). The engine converts those
pixels to physical screen coordinates itself, so the point read on a screenshot is the point
that gets clicked, whatever the DPI scaling, the window position or its maximized state.
"""

from __future__ import annotations

import contextlib
import ctypes
import io
import math
import os
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")


def _proto(dll: ctypes.WinDLL, name: str, restype: Any, *argtypes: Any) -> Any:
    function = getattr(dll, name)
    function.restype = restype
    function.argtypes = list(argtypes)
    return function


# Physical pixels everywhere: this must precede any window, capture or UI Automation call.
_proto(user32, "SetProcessDpiAwarenessContext", wintypes.BOOL, ctypes.c_void_p)(ctypes.c_void_p(-4))

import mss  # noqa: E402
import uiautomation as uia  # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageStat  # noqa: E402

HWND = wintypes.HWND
HANDLE = wintypes.HANDLE
DWORD = wintypes.DWORD
ULONG_PTR = ctypes.c_size_t
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", DWORD), ("u", _INPUTUNION)]

    @property
    def union(self) -> _INPUTUNION:
        return self.u


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", DWORD)]


WINEVENTPROC = ctypes.WINFUNCTYPE(None, HANDLE, DWORD, HWND, wintypes.LONG, wintypes.LONG, DWORD, DWORD)


GetForegroundWindow = _proto(user32, "GetForegroundWindow", HWND)
SetForegroundWindow = _proto(user32, "SetForegroundWindow", wintypes.BOOL, HWND)
BringWindowToTop = _proto(user32, "BringWindowToTop", wintypes.BOOL, HWND)
ShowWindow = _proto(user32, "ShowWindow", wintypes.BOOL, HWND, ctypes.c_int)
IsIconic = _proto(user32, "IsIconic", wintypes.BOOL, HWND)
IsZoomed = _proto(user32, "IsZoomed", wintypes.BOOL, HWND)
IsWindow = _proto(user32, "IsWindow", wintypes.BOOL, HWND)
IsWindowVisible = _proto(user32, "IsWindowVisible", wintypes.BOOL, HWND)
GetWindowTextLengthW = _proto(user32, "GetWindowTextLengthW", ctypes.c_int, HWND)
GetWindowTextW = _proto(user32, "GetWindowTextW", ctypes.c_int, HWND, wintypes.LPWSTR, ctypes.c_int)
GetClassNameW = _proto(user32, "GetClassNameW", ctypes.c_int, HWND, wintypes.LPWSTR, ctypes.c_int)
GetWindowThreadProcessId = _proto(user32, "GetWindowThreadProcessId", DWORD, HWND, ctypes.POINTER(DWORD))
AttachThreadInput = _proto(user32, "AttachThreadInput", wintypes.BOOL, DWORD, DWORD, wintypes.BOOL)
EnumWindows = _proto(user32, "EnumWindows", wintypes.BOOL, WNDENUMPROC, wintypes.LPARAM)
EnumDesktopWindows = _proto(user32, "EnumDesktopWindows", wintypes.BOOL, HANDLE, WNDENUMPROC, wintypes.LPARAM)
OpenDesktopW = _proto(user32, "OpenDesktopW", HANDLE, wintypes.LPCWSTR, DWORD, wintypes.BOOL, DWORD)
SetThreadDesktop = _proto(user32, "SetThreadDesktop", wintypes.BOOL, HANDLE)
DESKTOP_ALL_ACCESS = 0x01FF
_hdesk_default = None


def ensure_default_desktop() -> bool:
    """Attaches calling thread to interactive 'Default' desktop on WinSta0."""
    global _hdesk_default
    try:
        if not _hdesk_default:
            _hdesk_default = OpenDesktopW("Default", 0, False, DESKTOP_ALL_ACCESS)
        if _hdesk_default:
            return bool(SetThreadDesktop(_hdesk_default))
    except Exception:
        pass
    return False

GetWindowRect = _proto(user32, "GetWindowRect", wintypes.BOOL, HWND, ctypes.POINTER(RECT))
GetWindowLongPtrW = _proto(user32, "GetWindowLongPtrW", ctypes.c_ssize_t, HWND, ctypes.c_int)
WindowFromPoint = _proto(user32, "WindowFromPoint", HWND, POINT)
GetAncestor = _proto(user32, "GetAncestor", HWND, HWND, wintypes.UINT)
SetCursorPos = _proto(user32, "SetCursorPos", wintypes.BOOL, ctypes.c_int, ctypes.c_int)
SendInput = _proto(user32, "SendInput", wintypes.UINT, wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
VkKeyScanW = _proto(user32, "VkKeyScanW", wintypes.SHORT, wintypes.WCHAR)
MapVirtualKeyW = _proto(user32, "MapVirtualKeyW", wintypes.UINT, wintypes.UINT, wintypes.UINT)
GetSystemMetrics = _proto(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
GetWindow =_proto(user32, "GetWindow", HWND, HWND, wintypes.UINT)
SetWindowPos = _proto(
    user32, "SetWindowPos", wintypes.BOOL, HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
)
GetLastInputInfo = _proto(user32, "GetLastInputInfo", wintypes.BOOL, ctypes.POINTER(LASTINPUTINFO))
SetWinEventHook = _proto(
    user32, "SetWinEventHook", HANDLE, DWORD, DWORD, wintypes.HMODULE, WINEVENTPROC, DWORD, DWORD, DWORD
)
UnhookWinEvent = _proto(user32, "UnhookWinEvent", wintypes.BOOL, HANDLE)
MsgWaitForMultipleObjects = _proto(
    user32, "MsgWaitForMultipleObjects", DWORD, DWORD, ctypes.c_void_p, wintypes.BOOL, DWORD, DWORD
)
PeekMessageW = _proto(
    user32, "PeekMessageW", wintypes.BOOL, ctypes.POINTER(wintypes.MSG), HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT
)
TranslateMessage = _proto(user32, "TranslateMessage", wintypes.BOOL, ctypes.POINTER(wintypes.MSG))
DispatchMessageW = _proto(user32, "DispatchMessageW", ctypes.c_ssize_t, ctypes.POINTER(wintypes.MSG))
PostThreadMessageW = _proto(user32, "PostThreadMessageW", wintypes.BOOL, DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
GetCurrentThreadId = _proto(kernel32, "GetCurrentThreadId", DWORD)
GetTickCount = _proto(kernel32, "GetTickCount", DWORD)
OpenProcess = _proto(kernel32, "OpenProcess", HANDLE, DWORD, wintypes.BOOL, DWORD)
CloseHandle = _proto(kernel32, "CloseHandle", wintypes.BOOL, HANDLE)
CreateMutexW = _proto(kernel32, "CreateMutexW", HANDLE, ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
WaitForSingleObject = _proto(kernel32, "WaitForSingleObject", DWORD, HANDLE, DWORD)
ReleaseMutex = _proto(kernel32, "ReleaseMutex", wintypes.BOOL, HANDLE)

WAIT_ABANDONED = 0x00000080
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102


@contextlib.contextmanager
def input_lock(timeout_ms: int = 5000):
    """Win32 named mutex 'Local\\nexus-computer-input' guaranteeing cross-agent

    and user-safe serialization of physical hardware inputs (mouse, keyboard, foreground switches).
    """
    mutex_name = "Local\\nexus-computer-input"
    h_mutex = CreateMutexW(None, False, mutex_name)
    if not h_mutex:
        raise ComputerError("Impossible d'initialiser le mutex système Local\\nexus-computer-input.")
    acquired = False
    try:
        res = WaitForSingleObject(h_mutex, timeout_ms)
        if res in (WAIT_OBJECT_0, WAIT_ABANDONED):
            acquired = True
            yield
        else:
            raise ComputerError(
                f"INPUT_BUSY: Le sous-système d'entrées physiques est occupé par un autre processus après {timeout_ms}ms (code={res})."
            )
    finally:
        if acquired:
            ReleaseMutex(h_mutex)
        CloseHandle(h_mutex)

QueryFullProcessImageNameW = _proto(
    kernel32, "QueryFullProcessImageNameW", wintypes.BOOL, HANDLE, DWORD, wintypes.LPWSTR, ctypes.POINTER(DWORD)
)
OpenProcessToken = _proto(advapi32, "OpenProcessToken", wintypes.BOOL, HANDLE, DWORD, ctypes.POINTER(HANDLE))
GetTokenInformation = _proto(
    advapi32, "GetTokenInformation", wintypes.BOOL, HANDLE, ctypes.c_int, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD)
)
DwmGetWindowAttribute = _proto(dwmapi, "DwmGetWindowAttribute", ctypes.c_long, HWND, DWORD, ctypes.c_void_p, DWORD)

gdi32 = ctypes.WinDLL("gdi32")
GetDC = _proto(user32, "GetDC", wintypes.HDC, HWND)
ReleaseDC = _proto(user32, "ReleaseDC", ctypes.c_int, HWND, wintypes.HDC)
PrintWindow = _proto(user32, "PrintWindow", wintypes.BOOL, HWND, wintypes.HDC, wintypes.UINT)
CreateCompatibleDC = _proto(gdi32, "CreateCompatibleDC", wintypes.HDC, wintypes.HDC)
CreateCompatibleBitmap = _proto(gdi32, "CreateCompatibleBitmap", wintypes.HBITMAP, wintypes.HDC, ctypes.c_int, ctypes.c_int)
SelectObject = _proto(gdi32, "SelectObject", wintypes.HGDIOBJ, wintypes.HDC, wintypes.HGDIOBJ)
DeleteObject = _proto(gdi32, "DeleteObject", wintypes.BOOL, wintypes.HGDIOBJ)
DeleteDC = _proto(gdi32, "DeleteDC", wintypes.BOOL, wintypes.HDC)
GetBitmapBits = _proto(gdi32, "GetBitmapBits", ctypes.c_long, wintypes.HBITMAP, ctypes.c_long, ctypes.c_void_p)
PW_RENDERFULLCONTENT = 2

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004
WHEEL_DELTA = 120
SW_RESTORE = 9
GA_ROOT = 2
GW_HWNDPREV = 3
GWL_EXSTYLE = -20
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000008, 0x00000080, 0x00040000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_ASYNCWINDOWPOS = 0x0001, 0x0002, 0x0010, 0x4000
EVENT_SYSTEM_FOREGROUND, WINEVENT_OUTOFCONTEXT = 0x0003, 0x0000
QS_ALLINPUT, PM_REMOVE, WM_NULL = 0x04FF, 0x0001, 0x0000
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION = 20

SCREEN = 0  # Target id of the whole virtual screen.

# Images stay under the size the model sees without resampling, so its pixels are the click space.
MAX_LONG_EDGE = 1568
MAX_PIXELS = 1_150_000

_BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

VK_SHIFT, VK_CONTROL, VK_MENU, VK_RETURN, VK_TAB = 0x10, 0x11, 0x12, 0x0D, 0x09
_KEY_NAMES: dict[str, int] = {
    "enter": VK_RETURN, "return": VK_RETURN, "tab": VK_TAB, "space": 0x20, "backspace": 0x08,
    "escape": 0x1B, "esc": 0x1B, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "ins": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "page_up": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "page_down": 0x22, "pgdn": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "ctrl": VK_CONTROL, "control": VK_CONTROL, "alt": VK_MENU, "shift": VK_SHIFT,
    "win": 0x5B, "windows": 0x5B, "super": 0x5B, "cmd": 0x5B, "apps": 0x5D, "menu": 0x5D,
    "capslock": 0x14, "numlock": 0x90, "scrolllock": 0x91, "pause": 0x13,
    "printscreen": 0x2C, "prtsc": 0x2C,
    **{f"f{n}": 0x6F + n for n in range(1, 25)},
}  # fmt: skip
_EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F, 0x90}
_MODIFIER_VKS = {VK_SHIFT, VK_CONTROL, VK_MENU, 0x5B}

_INTERACTIVE_TYPES = {
    "ButtonControl", "SplitButtonControl", "EditControl", "DocumentControl", "ComboBoxControl",
    "CheckBoxControl", "RadioButtonControl", "MenuItemControl", "ListItemControl", "TreeItemControl",
    "TabItemControl", "HyperlinkControl", "SliderControl", "SpinnerControl", "DataItemControl",
    "HeaderItemControl", "ScrollBarControl",
}  # fmt: skip
_FOCUSABLE_TYPES = {"CustomControl", "GroupControl", "ImageControl", "TextControl"}
_VALUE_TYPES = {"EditControl", "DocumentControl", "ComboBoxControl", "SpinnerControl"}
MAX_TREE_DEPTH = 40
MAX_SIBLINGS = 500


class ComputerError(Exception):
    """Failure reported to the model as is; nothing was sent to the desktop when it is raised before input."""


# -----------------------------------------------------------------------------
# Windows, processes and geometry
# -----------------------------------------------------------------------------
def _handle(value: Any) -> int:
    return int(value or 0)


def foreground() -> int:
    return _handle(GetForegroundWindow())


def clean(text: str) -> str:
    """Replaces lone UTF-16 surrogates (common in window titles and UIA names), which JSON-RPC cannot encode."""
    return text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def window_title(hwnd: int) -> str:
    length = GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buffer, length + 1)
    return clean(buffer.value)


def window_class(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def window_pid(hwnd: int) -> int:
    pid = DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


_process_names: dict[int, str] = {}
_process_paths: dict[int, str] = {}


def process_name(pid: int) -> str:
    if pid in _process_names:
        return _process_names[pid]
    name = "?"
    path = ""
    process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if process:
        try:
            buffer = ctypes.create_unicode_buffer(1024)
            size = DWORD(1024)
            if QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                path = buffer.value
                name = os.path.basename(path)
        finally:
            CloseHandle(process)
    _process_names[pid] = name
    _process_paths[pid] = path
    return name


def process_path(pid: int) -> str:
    if pid not in _process_paths:
        process_name(pid)
    return _process_paths.get(pid, "")


def process_elevated(pid: int) -> bool | None:
    """True/False when the token can be read, None when Windows refuses to tell."""
    process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return None
    try:
        token = HANDLE()
        if not OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            return None
        try:
            elevation, size = DWORD(), DWORD()
            if not GetTokenInformation(token, TOKEN_ELEVATION, ctypes.byref(elevation), 4, ctypes.byref(size)):
                return None
            return bool(elevation.value)
        finally:
            CloseHandle(token)
    finally:
        CloseHandle(process)


SELF_ELEVATED = bool(process_elevated(os.getpid()))


def is_cloaked(hwnd: int) -> bool:
    cloaked = DWORD()
    result = DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return result == 0 and cloaked.value != 0


def frame_bounds(hwnd: int) -> tuple[int, int, int, int]:
    """Visible frame in physical pixels, without the invisible resize borders of GetWindowRect."""
    rect = RECT()
    if DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def virtual_screen() -> tuple[int, int, int, int]:
    left, top = GetSystemMetrics(SM_XVIRTUALSCREEN), GetSystemMetrics(SM_YVIRTUALSCREEN)
    return left, top, left + GetSystemMetrics(SM_CXVIRTUALSCREEN), top + GetSystemMetrics(SM_CYVIRTUALSCREEN)


def root_window_at(x: int, y: int) -> int:
    child = _handle(WindowFromPoint(POINT(x, y)))
    return _handle(GetAncestor(child, GA_ROOT)) if child else 0


def describe(hwnd: int) -> str:
    if hwnd == SCREEN:
        return "écran entier"
    return f"« {window_title(hwnd)} » ({process_name(window_pid(hwnd))}, hwnd {hwnd})"


class WindowBounds(tuple):
    """Window geometry tuple (left, top, width, height) supporting dict indexing and attribute access."""

    def __new__(cls, left: int = 0, top: int = 0, width: int = 0, height: int = 0) -> WindowBounds:
        return super().__new__(cls, (left, top, width, height))

    @property
    def left(self) -> int:
        return self[0]

    @property
    def top(self) -> int:
        return self[1]

    @property
    def width(self) -> int:
        return self[2]

    @property
    def height(self) -> int:
        return self[3]

    @property
    def right(self) -> int:
        return self[0] + self[2]

    @property
    def bottom(self) -> int:
        return self[1] + self[3]

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if key == "left":
                return self.left
            if key == "top":
                return self.top
            if key == "width":
                return self.width
            if key == "height":
                return self.height
            if key == "right":
                return self.right
            if key == "bottom":
                return self.bottom
            raise KeyError(key)
        return super().__getitem__(key)

    def __contains__(self, key: Any) -> bool:
        if isinstance(key, str):
            return key in ("left", "top", "width", "height", "right", "bottom")
        return super().__contains__(key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default) if key in self else default


def list_windows(visible_only: bool = True) -> list[dict[str, Any]]:
    """Top-level application windows in Z-order (frontmost first)."""
    ensure_default_desktop()
    windows: list[dict[str, Any]] = []
    active = foreground()

    def visit(raw_hwnd: Any, _: Any) -> bool:
        hwnd = _handle(raw_hwnd)
        if visible_only and (not IsWindowVisible(hwnd) or is_cloaked(hwnd)):
            return True
        title = window_title(hwnd)
        style = GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        if visible_only and (not title or (style & WS_EX_TOOLWINDOW and not style & WS_EX_APPWINDOW)):
            return True
        if visible_only and window_class(hwnd) in _SHELL_CLASSES:
            return True
        minimized = bool(IsIconic(hwnd))
        left, top, right, bottom = frame_bounds(hwnd)
        w, h = max(0, right - left), max(0, bottom - top)
        if visible_only and not minimized and (w < 10 or h < 10):
            return True
        pid = window_pid(hwnd)
        pname = process_name(pid)
        ppath = process_path(pid)
        wb = None if minimized else WindowBounds(left, top, w, h)
        windows.append(
            {
                "hwnd": hwnd,
                "title": title,
                "process": pname,
                "process_name": pname,
                "process_path": ppath,
                "pid": pid,
                "process_id": pid,
                "state": "réduite" if minimized else "agrandie" if IsZoomed(hwnd) else "normale",
                "foreground": hwnd == active,
                "is_foreground": hwnd == active,
                "bounds": wb,
            }
        )
        return True

    proc = WNDENUMPROC(visit)
    EnumWindows(proc, 0)
    if not windows and _hdesk_default:
        EnumDesktopWindows(_hdesk_default, proc, 0)
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


def find_window(title: str | None = None, process: str | None = None) -> int:
    title_query, process_query = (title or "").lower(), (process or "").lower()
    if not title_query and not process_query:
        raise ComputerError("Indiquez hwnd, title ou process_name.")
    for window in list_windows():
        if title_query and title_query not in window["title"].lower():
            continue
        if process_query and process_query not in window["process"].lower():
            continue
        return window["hwnd"]
    raise ComputerError(f"Aucune fenêtre ne correspond (title={title!r}, process_name={process!r}).")


# -----------------------------------------------------------------------------
# Frames: the shared coordinate space of screenshots, element boxes and actions
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Frame:
    hwnd: int
    left: int
    top: int
    width: int
    height: int
    image_width: int
    image_height: int

    @classmethod
    def fit(cls, hwnd: int, left: int, top: int, width: int, height: int) -> Frame:
        scale = min(1.0, MAX_LONG_EDGE / max(width, height), math.sqrt(MAX_PIXELS / (width * height)))
        return cls(hwnd, left, top, width, height, max(1, round(width * scale)), max(1, round(height * scale)))

    @property
    def scale(self) -> float:
        return self.image_width / self.width

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        """Centre of image pixel (x, y) in physical screen coordinates."""
        return (
            self.left + math.floor((x + 0.5) * self.width / self.image_width),
            self.top + math.floor((y + 0.5) * self.height / self.image_height),
        )

    def to_image(self, x: float, y: float) -> tuple[int, int]:
        return (
            math.floor((x - self.left) * self.image_width / self.width),
            math.floor((y - self.top) * self.image_height / self.height),
        )

    def check(self, x: float, y: float) -> None:
        """Coordinates come from the image: anything outside it is a mistake, never extrapolated."""
        if not (0 <= x < self.image_width and 0 <= y < self.image_height):
            raise ComputerError(
                f"({x},{y}) est hors de l'image {self.image_width}×{self.image_height} : les coordonnées sont "
                "celles de la dernière capture."
            )

    def summary(self) -> str:
        return (
            f"image {self.image_width}×{self.image_height} px = {self.width}×{self.height} px physiques "
            f"(×{self.scale:.3f}), origine écran ({self.left},{self.top})"
        )


def current_frame(hwnd: int) -> Frame:
    ensure_default_desktop()
    v_left, v_top, v_right, v_bottom = virtual_screen()
    if hwnd == SCREEN:
        return Frame.fit(SCREEN, v_left, v_top, v_right - v_left, v_bottom - v_top)
    if not IsWindow(hwnd):
        raise ComputerError(f"La fenêtre {hwnd} n'existe plus : appelez computer_list_windows.")
    if IsIconic(hwnd):
        raise ComputerError(f"{describe(hwnd)} est réduite : appelez computer_focus_window d'abord.")
    if not IsWindowVisible(hwnd) or is_cloaked(hwnd):
        raise ComputerError(f"{describe(hwnd)} est invisible : une capture montrerait ce qui se trouve derrière.")
    left, top, right, bottom = frame_bounds(hwnd)
    left, top, right, bottom = max(left, v_left), max(top, v_top), min(right, v_right), min(bottom, v_bottom)
    if right - left < 1 or bottom - top < 1:
        raise ComputerError(f"{describe(hwnd)} est hors de l'écran.")
    return Frame.fit(hwnd, left, top, right - left, bottom - top)


@dataclass
class _Session:
    target: int | None = None
    frames: dict[int, Frame] = field(default_factory=dict)  # last frame shown to the model, per target
    elements: dict[int, Any] = field(default_factory=dict)
    elements_hwnd: int | None = None
    marks: list[tuple[int, tuple[int, int, int, int]]] = field(default_factory=list)


SESSION = _Session()


def resolve_target(hwnd: int | None) -> int:
    if hwnd is None:
        if SESSION.target is None:
            raise ComputerError(
                "Aucune cible : appelez computer_list_windows puis passez hwnd (0 = écran entier)."
            )
        hwnd = SESSION.target
    if hwnd != SCREEN and not IsWindow(hwnd):
        raise ComputerError(f"La fenêtre {hwnd} n'existe plus : appelez computer_list_windows.")
    SESSION.target = hwnd
    return hwnd


def action_frame(hwnd: int) -> Frame:
    """Current frame of the target, refused when the model has not seen it at this size."""
    frame = current_frame(hwnd)
    seen = SESSION.frames.get(hwnd)
    if seen is None:
        raise ComputerError(
            f"Aucune capture de {describe(hwnd)} : appelez computer_screenshot ou computer_get_window_state "
            "avant d'utiliser des coordonnées."
        )
    if (seen.width, seen.height) != (frame.width, frame.height):
        raise ComputerError(
            f"{describe(hwnd)} a changé de taille depuis la dernière capture "
            f"({seen.width}×{seen.height} → {frame.width}×{frame.height}) : reprenez une capture."
        )
    return frame


# -----------------------------------------------------------------------------
# Capture
# -----------------------------------------------------------------------------
def _grab(left: int, top: int, width: int, height: int) -> Image.Image:
    with mss.mss() as screen:
        shot = screen.grab({"left": left, "top": top, "width": width, "height": height})
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def covering_windows(frame: Frame) -> list[int]:
    """Windows of other processes that cover part of the target, sampled on a 5×5 grid."""
    if frame.hwnd == SCREEN:
        return []
    pid = window_pid(frame.hwnd)
    covering: dict[int, None] = {}
    for i in range(1, 6):
        for j in range(1, 6):
            hit = root_window_at(frame.left + frame.width * i // 6, frame.top + frame.height * j // 6)
            if hit and window_pid(hit) != pid:
                covering[hit] = None
    return list(covering)


def _badge_spot(box: tuple[int, int, int, int], size: tuple[float, float], taken: list, bounds: tuple[int, int]) -> tuple[float, float]:
    """First badge position that overlaps no other badge: inside top-left, then left of, above, below the element."""
    x1, y1, x2, y2 = box
    width, height = size
    for left, top in ((x1, y1), (x1 - width - 1, y1), (x1, y1 - height - 1), (x1, y2 + 1), (x2 - width, y1)):
        if left < 0 or top < 0 or left + width > bounds[0] or top + height > bounds[1]:
            continue
        if all(left + width <= a or left >= c or top + height <= b or top >= d for a, b, c, d in taken):
            return left, top
    return max(0, x1), max(0, y1)


PHI = (1 + math.sqrt(5)) / 2
MARK_RGB = (230, 30, 90)
BADGE_ALPHA = round(255 / PHI)  # ≈ 158: the element's own text shows through the badge.
CONTAINER_SHARE = 1 / PHI**2  # ≈ 38 %: a box covering more of the image (document, pane) gets no outline.


def _area(box: tuple[int, int, int, int]) -> int:
    return (box[2] - box[0]) * (box[3] - box[1])


def _badge_layout(
    marks: list[tuple[int, tuple[int, int, int, int]]], sizes: dict[int, tuple[float, float]], bounds: tuple[int, int]
) -> dict[int, tuple[float, float]]:
    """Badge position per element; the smallest elements choose first, so a container never pushes a button's away."""
    taken: list[tuple[float, float, float, float]] = []
    spots: dict[int, tuple[float, float]] = {}
    for index, box in sorted(marks, key=lambda mark: _area(mark[1])):
        width, height = sizes[index]
        left, top = _badge_spot(box, (width, height), taken, bounds)
        taken.append((left, top, left + width, top + height))
        spots[index] = (left, top)
    return spots


def _draw_marks(image: Image.Image, marks: list[tuple[int, tuple[int, int, int, int]]]) -> None:
    """Numbered boxes over listed elements, so the model can pick an element_index by sight.

    Badges are translucent and never overlap one another, so neighbouring numbers stay readable and the
    element's own text still shows through. Large containers keep their badge but lose their outline, which
    would only frame the whole window.
    """
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default(size=11)
    container = image.width * image.height * CONTAINER_SHARE
    for _, (x1, y1, x2, y2) in marks:  # All outlines first, so no outline crosses a badge drawn later.
        if _area((x1, y1, x2, y2)) <= container:
            draw.rectangle((x1, y1, max(x1, x2 - 1), max(y1, y2 - 1)), outline=(*MARK_RGB, 255), width=1)
    sizes = {index: (draw.textlength(str(index), font=font) + 6, 13) for index, _ in marks}
    for index, (left, top) in _badge_layout(marks, sizes, image.size).items():
        label, size = str(index), sizes[index]
        draw.rectangle((left, top, left + size[0], top + size[1]), fill=(*MARK_RGB, BADGE_ALPHA))
        # A dark outline keeps the white number legible on any background now that the badge lets it through.
        draw.text((left + 3, top), label, fill=(255, 255, 255, 255), font=font, stroke_width=1, stroke_fill=(80, 0, 25, 255))
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))


def background_grab(hwnd: int, frame: Frame) -> Image.Image | None:
    """The window's own rendering (even when covered), cropped to the frame; None if the app paints nothing."""
    rect = RECT()
    GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    screen_dc = GetDC(None)
    memory_dc = CreateCompatibleDC(screen_dc)
    bitmap = CreateCompatibleBitmap(screen_dc, width, height)
    previous = SelectObject(memory_dc, bitmap)
    try:
        rendered = PrintWindow(hwnd, memory_dc, PW_RENDERFULLCONTENT)
        pixels = ctypes.create_string_buffer(width * height * 4)
        GetBitmapBits(bitmap, len(pixels), pixels)
    finally:
        SelectObject(memory_dc, previous)
        DeleteObject(bitmap)
        DeleteDC(memory_dc)
        ReleaseDC(None, screen_dc)
    if not rendered:
        return None
    image = Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1)
    left, top = frame.left - rect.left, frame.top - rect.top  # GetWindowRect includes the invisible borders.
    image = image.crop((left, top, left + frame.width, top + frame.height))
    if ImageStat.Stat(image.convert("L")).stddev[0] < 2:  # Uniform image: the app does not render off-screen.
        return None
    return image


def screenshot(hwnd: int, marks: list[tuple[int, tuple[int, int, int, int]]] | None = None) -> tuple[Frame, bytes, list[str]]:
    """Captures without bringing anything to the front: covered windows are rendered by themselves."""
    frame = current_frame(hwnd)
    notes = []
    image = None
    if hwnd != SCREEN and (foreground() != hwnd or covering_windows(frame)):
        image = background_grab(hwnd, frame)
        if image is None:
            covering = covering_windows(frame)
            if covering:
                notes.append(
                    "Cette application ne se dessine pas en arrière-plan : la capture montre "
                    + ", ".join(describe(h) for h in covering[:3]) + " par-dessus."
                )
        else:
            notes.append("Capturée en arrière-plan, sans la mettre devant.")
    if image is None:
        image = _grab(frame.left, frame.top, frame.width, frame.height)
    if image.size != (frame.image_width, frame.image_height):
        image = image.resize((frame.image_width, frame.image_height), Image.Resampling.LANCZOS)
    if marks:
        _draw_marks(image, marks)
    SESSION.frames[hwnd] = frame
    return frame, _png(image), notes


def zoom(hwnd: int, x1: float, y1: float, x2: float, y2: float) -> tuple[bytes, str]:
    """Detail of a region of the last capture at up to native resolution; coordinates stay those of the capture."""
    frame = action_frame(hwnd)
    if x2 <= x1 or y2 <= y1:
        raise ComputerError("Région vide : il faut x1 < x2 et y1 < y2.")
    frame.check(x1, y1)
    frame.check(x2 - 1, y2 - 1)
    left, top = frame.to_screen(x1, y1)
    right, bottom = frame.to_screen(x2, y2)
    width, height = max(1, right - left), max(1, bottom - top)
    detail = Frame.fit(hwnd, left, top, width, height)
    whole = background_grab(hwnd, frame) if hwnd != SCREEN and foreground() != hwnd else None
    if whole is not None:
        image = whole.crop((left - frame.left, top - frame.top, right - frame.left, bottom - frame.top))
    else:
        image = _grab(left, top, width, height)
    if image.size != (detail.image_width, detail.image_height):
        image = image.resize((detail.image_width, detail.image_height), Image.Resampling.LANCZOS)
    return _png(image), f"zoom ×{detail.image_width / (x2 - x1):.2f} sur ({x1},{y1})–({x2},{y2})"


# -----------------------------------------------------------------------------
# UI Automation
# -----------------------------------------------------------------------------
def _interactive(control: Any, control_type: str) -> bool:
    if control_type in _INTERACTIVE_TYPES:
        return True
    return control_type in _FOCUSABLE_TYPES and bool(control.Name) and bool(control.IsKeyboardFocusable)


def window_elements(hwnd: int, max_elements: int, budget_s: float = 4.0) -> tuple[Frame, list[str], bool]:
    """Numbered interactive elements of the window, boxes in the frame's image space."""
    if hwnd == SCREEN:
        raise ComputerError("L'arbre UI Automation se lit fenêtre par fenêtre : passez un hwnd.")
    frame = current_frame(hwnd)
    root = uia.ControlFromHandle(hwnd)
    if root is None:
        raise ComputerError(f"UI Automation n'expose pas {describe(hwnd)}.")
    deadline = time.monotonic() + budget_s
    elements: dict[int, Any] = {}
    lines: list[str] = []
    marks: list[tuple[int, tuple[int, int, int, int]]] = []
    exhausted = False

    def children(control: Any):
        """Lazy sibling walk, so the time budget also holds inside very wide nodes."""
        try:
            child = control.GetFirstChildControl()
        except Exception:  # noqa: BLE001 - elements vanish while being walked
            return
        for _ in range(MAX_SIBLINGS):
            if child is None:
                return
            yield child
            try:
                child = child.GetNextSiblingControl()
            except Exception:  # noqa: BLE001
                return

    def visit(control: Any, depth: int) -> None:
        nonlocal exhausted
        if depth > MAX_TREE_DEPTH:
            return
        for child in children(control):
            if len(lines) >= max_elements or time.monotonic() > deadline:
                exhausted = True
                return
            try:
                if child.IsOffscreen:
                    continue
                rect = child.BoundingRectangle
                control_type = child.ControlTypeName
                box = _visible_box(rect, frame)
                # Not in UIA's control view (e.g. a hidden caption button): not listed, its children may be.
                if box is not None and _interactive(child, control_type) and child.IsControlElement:
                    index = len(lines) + 1
                    line = _element_line(index, child, control_type, box)
                    elements[index] = child
                    lines.append(line)
                    marks.append((index, box))
            except Exception:  # noqa: BLE001
                continue
            visit(child, depth + 1)

    visit(root, 0)
    SESSION.elements, SESSION.elements_hwnd, SESSION.marks = elements, hwnd, marks
    SESSION.frames[hwnd] = frame
    return frame, lines, exhausted


def _visible_box(rect: Any, frame: Frame) -> tuple[int, int, int, int] | None:
    """Part of a UIA rectangle inside the frame, in image pixels; None when nothing of it is visible."""
    left, top = max(rect.left, frame.left), max(rect.top, frame.top)
    right, bottom = min(rect.right, frame.left + frame.width), min(rect.bottom, frame.top + frame.height)
    if right <= left or bottom <= top:
        return None
    x1, y1 = frame.to_image(left, top)
    x2, y2 = frame.to_image(right, bottom)
    return x1, y1, max(x1 + 1, x2), max(y1 + 1, y2)


def _quoted(text: str, limit: int = 80) -> str:
    text = clean(text or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").replace('"', "'")
    return f'"{text[:limit]}{"…" if len(text) > limit else ""}"'


def _element_line(index: int, control: Any, control_type: str, box: tuple[int, int, int, int]) -> str:
    x1, y1, x2, y2 = box
    line = f'[{index}] {control_type.removesuffix("Control")} {_quoted(control.Name)} ({(x1 + x2) // 2},{(y1 + y2) // 2}) {x2 - x1}×{y2 - y1}'
    if control_type in _VALUE_TYPES:
        try:
            pattern = control.GetPattern(uia.PatternId.ValuePattern)
            value = _field_value(control, pattern.Value) if pattern is not None else ""
            if value:
                line += f" = {_quoted(value)}"
        except Exception:  # noqa: BLE001
            pass
    if not control.IsEnabled:
        line += " [désactivé]"
    if control.HasKeyboardFocus:
        line += " [focus]"
    return line


def element(hwnd: int, index: int) -> Any:
    if SESSION.elements_hwnd != hwnd or index not in SESSION.elements:
        raise ComputerError(
            f"Élément [{index}] inconnu pour {describe(hwnd)} : relancez computer_get_window_state."
        )
    return SESSION.elements[index]


def element_center(control: Any, frame: Frame) -> tuple[int, int] | None:
    """Centre of the part of the element that is inside the target's visible frame, in physical pixels."""
    try:
        rect = control.BoundingRectangle
        if control.IsOffscreen:
            return None
    except Exception:  # noqa: BLE001
        return None
    left, top = max(rect.left, frame.left), max(rect.top, frame.top)
    right, bottom = min(rect.right, frame.left + frame.width), min(rect.bottom, frame.top + frame.height)
    if right <= left or bottom <= top:
        return None
    return (left + right) // 2, (top + bottom) // 2


def _pattern(control: Any, pattern_id: int) -> Any:
    try:
        return control.GetPattern(pattern_id)
    except Exception:  # noqa: BLE001
        return None


def _run_bounded(action: Any, wait_s: float = 2.0) -> bool:
    """Runs a UIA call on a worker thread; False when it is still running after wait_s (a modal dialog blocks some providers)."""
    errors: list[Exception] = []

    def run() -> None:
        try:
            with uia.UIAutomationInitializerInThread():
                action()
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(wait_s)
    if errors:
        raise ComputerError(f"Action UI Automation refusée : {errors[0]}")
    return not worker.is_alive()


_SELECT_TYPES = {"ListItemControl", "TreeItemControl", "TabItemControl", "RadioButtonControl", "DataItemControl"}
_TOGGLE_STATES = {0: "décoché", 1: "coché", 2: "indéterminé"}


def _read_until(read: Any, accept: Any, timeout_s: float = 0.3) -> Any:
    """Reads a UIA property until accept(value) or timeout: some providers apply a change a moment after the call."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            value = read()
        except Exception:  # noqa: BLE001 - the element may vanish, e.g. a button that closes its window
            value = None
        if accept(value) or time.monotonic() >= deadline:
            return value
        time.sleep(0.02)


def background_activate(control: Any) -> str | None:
    """What a left click would do, through UIA patterns, without mouse or focus.

    Returns a description of the effect, read back from the element when UIA can tell it, or None when the
    element offers no suitable pattern (the caller then needs the real mouse). waitTime=0 everywhere: the
    uiautomation package otherwise sleeps 0.5 s after each call, while the application may hold the foreground.
    """
    control_type = control.ControlTypeName
    if control_type in _SELECT_TYPES and (pattern := _pattern(control, uia.PatternId.SelectionItemPattern)):
        finished = _run_bounded(lambda: pattern.Select(waitTime=0))
        selected = finished and _read_until(lambda: pattern.IsSelected, bool)
        return "sélectionné" if selected else "sélection demandée, non confirmée"
    if pattern := _pattern(control, uia.PatternId.TogglePattern):
        before = pattern.ToggleState
        finished = _run_bounded(lambda: pattern.Toggle(waitTime=0))
        after = _read_until(lambda: pattern.ToggleState, lambda state: state is not None and state != before)
        if finished and after is not None and after != before:
            return _TOGGLE_STATES.get(after, "basculé")
        return "bascule demandée, état inchangé"
    if pattern := _pattern(control, uia.PatternId.InvokePattern):
        if _run_bounded(lambda: pattern.Invoke(waitTime=0)):
            return "activé (UIA ne confirme pas l'effet : vérifier par une capture)"
        return "activation en cours après 2 s (boîte de dialogue probable) : vérifier par une capture"
    if pattern := _pattern(control, uia.PatternId.ExpandCollapsePattern):
        expanded = pattern.ExpandCollapseState == 1
        _run_bounded(lambda: pattern.Collapse(waitTime=0) if expanded else pattern.Expand(waitTime=0))
        wanted = 0 if expanded else 1
        if _read_until(lambda: pattern.ExpandCollapseState, lambda state: state == wanted) == wanted:
            return "replié" if expanded else "déplié"
        return "repli demandé, état inchangé" if expanded else "dépliage demandé, état inchangé"
    return None


_SCROLL_AMOUNT = {"up": (2, 1), "down": (2, 4), "left": (1, 2), "right": (4, 2)}  # (horizontal, vertical) ScrollAmount


def _percent(value: Any) -> float | None:
    """A scroll position UIA can vouch for: Chromium reports values such as 277 % for reversed chat lists."""
    return value if isinstance(value, (int, float)) and 0 <= value <= 100 else None


def background_scroll(control: Any, direction: str, amount: int) -> str | None:
    """Scrolls the nearest scrollable container of the element through UIA, one small step (a line) per notch.

    Returns the position read back afterwards, or None if no container around the element scrolls that way. One
    step per notch rather than the wheel's three: each step lets the application hold the foreground longer.
    """
    if direction not in _SCROLL_AMOUNT:
        raise ComputerError(f"Direction inconnue : {direction!r} (up, down, left, right).")
    horizontal_amount, vertical_amount = _SCROLL_AMOUNT[direction]
    sideways = direction in ("left", "right")
    current, depth = control, 0
    while current is not None and depth < 15:
        pattern = _pattern(current, uia.PatternId.ScrollPattern)
        if pattern is not None and (pattern.HorizontallyScrollable if sideways else pattern.VerticallyScrollable):
            break
        current, depth = current.GetParentControl(), depth + 1
    else:
        return None

    def position() -> float:
        return pattern.HorizontalScrollPercent if sideways else pattern.VerticalScrollPercent

    def scroll() -> None:
        for _ in range(amount):
            pattern.Scroll(horizontal_amount, vertical_amount, waitTime=0)

    before = position()
    finished = _run_bounded(scroll)
    after = _read_until(position, lambda value: value is not None and value != before)
    late = "" if finished else ", défilement encore en cours après 2 s"
    if _percent(after) is None:
        return f"position illisible{late} : vérifier par une capture"
    if _percent(before) is None:
        return f"position {after:.0f} %{late}"
    if after == before:
        return f"position {after:.0f} % : rien n'a bougé, déjà au bout ?"
    return f"position {before:.0f} % → {after:.0f} %{late}"


def _field_value(control: Any, value: str | None) -> str:
    """RichEdit adds one synthetic final CR; every preceding line break belongs to the user's text."""
    text = value or ""
    try:
        rich_edit = "richedit" in control.ClassName.lower()
    except Exception:  # noqa: BLE001 - unknown providers keep their value intact
        rich_edit = False
    return text.removesuffix("\r") if rich_edit else text


def set_value(control: Any, text: str, append: bool = False) -> bool:
    """Writes the field through UIA, without keyboard or focus, when it supports it and the text has no Enter/Tab.

    Returns True only when reading the value back confirms it (some providers apply it late or not at all).
    """
    if any(char in text for char in "\r\n\t"):
        return False
    try:
        pattern = control.GetPattern(uia.PatternId.ValuePattern)
        if pattern is None or pattern.IsReadOnly:
            return False
        wanted = _field_value(control, pattern.Value) + text if append else text
        pattern.SetValue(wanted, waitTime=0)
        return _read_until(lambda: _field_value(control, pattern.Value), lambda value: value == wanted, 0.5) == wanted
    except Exception:  # noqa: BLE001
        return False


def focus_element(control: Any, wait_s: float = 0.5) -> bool:
    """Gives keyboard focus to the element and confirms it (Chromium focuses asynchronously)."""
    if not control.SetFocus():  # uiautomation returns False on COM errors: stale, disabled or not focusable
        return False
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        try:
            focused = uia.GetFocusedControl()
            while focused is not None:  # Focus may land on a child, e.g. the edit inside a combo box.
                if uia.ControlsAreSame(focused, control):
                    return True
                focused = focused.GetParentControl()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.05)
    return False


# -----------------------------------------------------------------------------
# Focus and input safety
# -----------------------------------------------------------------------------
def _mouse_input(flags: int, data: int = 0) -> INPUT:
    item = INPUT(type=INPUT_MOUSE)
    item.u.mi.dwFlags = flags
    item.u.mi.mouseData = data & 0xFFFFFFFF
    return item


def _key_input(vk: int, up: bool) -> INPUT:
    item = INPUT(type=INPUT_KEYBOARD)
    item.u.ki.wVk = vk
    item.u.ki.wScan = MapVirtualKeyW(vk, 0) & 0xFF
    item.u.ki.dwFlags = (KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED_VKS else 0) | (KEYEVENTF_KEYUP if up else 0)
    return item


def _unicode_input(code_unit: int, up: bool) -> INPUT:
    item = INPUT(type=INPUT_KEYBOARD)
    item.u.ki.wScan = code_unit
    item.u.ki.dwFlags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return item


def _send(*inputs: INPUT) -> None:
    with input_lock():
        array = (INPUT * len(inputs))(*inputs)
        if SendInput(len(inputs), array, ctypes.sizeof(INPUT)) != len(inputs):
            raise ComputerError(
                f"Windows a refusé l'entrée simulée (erreur {ctypes.get_last_error()}) : session verrouillée, "
                "invite UAC ou bureau sécurisé."
            )


def _try_foreground(hwnd: int, with_alt: bool) -> None:
    with input_lock(timeout_ms=1000):
        current = foreground()
        own_thread = GetCurrentThreadId()
        other_thread = GetWindowThreadProcessId(current, None) if current else 0
        attached = bool(other_thread and other_thread != own_thread and AttachThreadInput(own_thread, other_thread, True))
        try:
            if with_alt:  # A held Alt key lifts the foreground lock for the next SetForegroundWindow.
                _send(_key_input(VK_MENU, up=False))
            BringWindowToTop(hwnd)
            SetForegroundWindow(hwnd)
            if with_alt:
                _send(_key_input(VK_MENU, up=True))
        finally:
            if attached:
                AttachThreadInput(own_thread, other_thread, False)


def give_foreground(hwnd: int) -> threading.Thread | None:
    """Starts handing the foreground back to the user's window on its own thread; no key is simulated.

    BringWindowToTop, the call that gets past the foreground lock here, waits for the thread of the window losing
    activation (measured: 7–25 ms while the target finishes a UIA call): a busy or hung application must not block
    the caller.
    """
    if not hwnd or not IsWindow(hwnd) or IsIconic(hwnd):
        return None
    worker = threading.Thread(target=_try_foreground, args=(hwnd, False), daemon=True)
    worker.start()
    return worker


def restore_foreground(hwnd: int, wait_s: float = 0.5) -> bool:
    """Gives the foreground back to the user's window after an application took it by itself."""
    if give_foreground(hwnd) is None:
        return False
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if foreground() == hwnd:
            return True
        time.sleep(0.01)
    return foreground() == hwnd


def user_input_tick() -> int:
    """GetTickCount time of the user's last keyboard or mouse input in this session."""
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO))
    return info.dwTime if GetLastInputInfo(ctypes.byref(info)) else 0


def windows_above(hwnd: int, limit: int = 4000) -> list[int]:
    """Top-level windows above hwnd in the Z-order, nearest first."""
    above: list[int] = []
    current = _handle(GetWindow(hwnd, GW_HWNDPREV))
    while current and len(above) < limit:
        above.append(current)
        current = _handle(GetWindow(current, GW_HWNDPREV))
    return above


def z_anchor(hwnd: int) -> int:
    """Nearest shown, non-topmost window of another process above hwnd: hwnd belongs right under it (0: none)."""
    pid = window_pid(hwnd)
    for other in windows_above(hwnd):
        if (
            IsWindowVisible(other)
            and not is_cloaked(other)
            and not GetWindowLongPtrW(other, GWL_EXSTYLE) & WS_EX_TOPMOST
            and window_pid(other) != pid
        ):
            return other
    return 0


def restore_z_order(hwnd: int, anchor: int) -> bool | None:
    """Puts hwnd back right under anchor without activating anything; None when it never left its place."""
    if not anchor or not IsWindow(anchor) or not IsWindow(hwnd) or anchor in windows_above(hwnd):
        return None
    # Asynchronous: a busy target thread must not block the server.
    SetWindowPos(hwnd, anchor, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        if anchor in windows_above(hwnd):
            return True
        time.sleep(0.02)
    return anchor in windows_above(hwnd)


class ForegroundGuard:
    """Wraps a background action: the user's window keeps the foreground and the target keeps its Z-order place.

    Applications activate themselves while UI Automation acts on them: the provider activates the window before
    clicking a Win32 control (BM_CLICK fails in an inactive dialog), WinForms focuses the control. That activation
    is part of the action: handing the foreground back before the UIA call returns lost one toggle in six on
    Character Map. So the foreground goes back the moment the call returns (10–50 ms away in all, instead of
    0.6 s), and a foreground-change hook hands it back within milliseconds whenever the application takes it again
    during a short quiet period. Then the target goes back right under the window that covered it. A switch to
    another application after the user's own input is the user's doing: it is never fought.
    """

    QUIET_S = 0.15  # Watch at least this long after the action: some apps activate a moment after the call returns.
    SETTLE_S = 0.3  # ...and this long after the foreground was last seen away from the user's window.
    MAX_WATCH_S = 2.0
    MAX_RESTORES = 8
    RETRY_S = 0.02

    def __init__(self, target: int) -> None:
        self.target = target
        self.target_pid = window_pid(target)
        self.front = foreground()
        self.anchor = z_anchor(target)
        self.active = bool(self.front) and self.front != target
        self.timeline: list[tuple[int, int, str]] = []  # (ms since start, foreground hwnd, what happened)
        self.taken = 0  # Times the foreground left the user's window.
        self.longest_ms = 0.0  # Longest of those absences.
        self.yielded = False
        self.failed = False
        self.z_restored: bool | None = None
        self._restores = 0
        self._start = 0.0
        self._input_tick = 0
        self._lost_at: float | None = None
        self._last_away = 0.0
        self._last_try = 0.0
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._action_done = threading.Event()
        self._watcher_thread_id = 0
        self._hook_proc = WINEVENTPROC(self._on_event)  # Kept referenced for the hook's lifetime.

    def __enter__(self) -> Self:
        self._start = time.perf_counter()
        if self.active:
            self._input_tick = user_input_tick()
            self._thread = threading.Thread(target=self._watch, daemon=True)
            self._thread.start()
            self._ready.wait(0.5)
        return self

    def __exit__(self, *_exc: object) -> None:
        self._action_done.set()
        if self._thread is not None:
            PostThreadMessageW(self._watcher_thread_id, WM_NULL, 0, 0)  # Wake the watcher now, not at its next poll.
            end = time.perf_counter()
            while True:
                now = time.perf_counter()
                quiet = now - end >= self.QUIET_S and now - self._last_away >= self.SETTLE_S
                if quiet or now - end >= self.MAX_WATCH_S:
                    break
                time.sleep(0.01)
            self._stop.set()
            self._thread.join(1.0)
            current = foreground()
            if current != self.front and not self.yielded and current and self._caused_by_action(current):
                self.failed = not restore_foreground(self.front)
            if self._lost_at is not None and not self.failed:
                self.longest_ms = max(self.longest_ms, (time.perf_counter() - self._lost_at) * 1000)
        current = foreground()
        if not current or window_pid(current) != self.target_pid:  # Never push the active window down.
            self.z_restored = restore_z_order(self.target, self.anchor)

    def _ms(self) -> int:
        return round((time.perf_counter() - self._start) * 1000)

    def _on_event(self, _hook: Any, _event: int, hwnd: Any, *_rest: Any) -> None:
        self.timeline.append((self._ms(), _handle(hwnd), "événement"))

    def _caused_by_action(self, hwnd: int) -> bool:
        """The target's own process, or any window activated without the user touching mouse or keyboard."""
        return window_pid(hwnd) == self.target_pid or user_input_tick() == self._input_tick

    def _watch(self) -> None:
        hook = SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, self._hook_proc, 0, 0, WINEVENT_OUTOFCONTEXT
        )
        self._watcher_thread_id = GetCurrentThreadId()
        self._ready.set()
        message = wintypes.MSG()
        try:
            while not self._stop.is_set():
                # Woken at once by the hook's event; the timeout also makes it a 5 ms poll if the hook is missing.
                MsgWaitForMultipleObjects(0, None, False, 5, QS_ALLINPUT)
                while PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
                    TranslateMessage(ctypes.byref(message))
                    DispatchMessageW(ctypes.byref(message))
                try:
                    self._check()
                except Exception as error:  # noqa: BLE001 - windows vanish; the guard must keep running
                    self.timeline.append((self._ms(), 0, f"erreur {error}"))
        finally:
            if hook:
                UnhookWinEvent(hook)

    def _check(self) -> None:
        current, now = foreground(), time.perf_counter()
        if current == self.front:
            if self._lost_at is not None:
                self.longest_ms = max(self.longest_ms, (now - self._lost_at) * 1000)
                self._lost_at = None
                self.timeline.append((self._ms(), current, "rendu"))
            return
        self._last_away = now
        if self._lost_at is None:
            self._lost_at = now
            self.taken += 1
            self.timeline.append((self._ms(), current, "pris"))
        if not current or self.yielded:  # 0: an activation is in progress.
            return
        if not self._caused_by_action(current):
            self.yielded = True
            self.timeline.append((self._ms(), current, "laissé à l'utilisateur"))
            return
        if not self._action_done.is_set():  # The activation belongs to the UIA call: let it finish.
            return
        in_flight = self._worker is not None and self._worker.is_alive()
        if not in_flight and self._restores < self.MAX_RESTORES and now - self._last_try >= self.RETRY_S:
            self._last_try = now
            self._restores += 1
            self._worker = give_foreground(self.front)

    def summary(self) -> str:
        parts = []
        if self.failed:
            parts.append(f"l'application a pris le premier plan et Windows a refusé de le rendre à {describe(self.front)}")
        elif self.taken and not self.yielded:
            parts.append(f"l'application a pris le premier plan : rendu en {self.longest_ms:.0f} ms")
        if self.yielded:
            parts.append("une autre fenêtre est passée au premier plan pendant l'action, sans doute Julien : laissée devant")
        if self.z_restored is True:
            parts.append("fenêtre remise à sa place dans l'empilement")
        elif self.z_restored is False:
            parts.append("la fenêtre n'a pas pu être remise à sa place dans l'empilement")
        return " ; ".join(parts)


def bring_to_front(hwnd: int) -> bool:
    if IsIconic(hwnd):
        ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.2)
    for with_alt in (False, True):
        if foreground() == hwnd:
            return True
        _try_foreground(hwnd, with_alt)
        deadline = time.monotonic() + 0.6
        while time.monotonic() < deadline:
            if foreground() == hwnd:
                return True
            time.sleep(0.03)
    return foreground() == hwnd


def ensure_input_target(hwnd: int) -> None:
    """Puts the target in front and refuses to send anything if another application would receive it."""
    if hwnd == SCREEN:
        return
    pid = window_pid(hwnd)
    if process_elevated(pid) and not SELF_ELEVATED:
        raise ComputerError(
            f"{describe(hwnd)} tourne en administrateur : Windows (UIPI) bloque les entrées d'un processus "
            "non élevé. Rien n'a été envoyé."
        )
    bring_to_front(hwnd)
    active = foreground()
    if not active or window_pid(active) != pid:
        raise ComputerError(
            f"Impossible de mettre {describe(hwnd)} au premier plan (actuellement : "
            f"{describe(active) if active else 'aucune'}). Rien n'a été envoyé."
        )


def ensure_point(hwnd: int, x: int, y: int) -> None:
    if hwnd == SCREEN:
        return
    hit = root_window_at(x, y)
    if not hit or window_pid(hit) != window_pid(hwnd):
        raise ComputerError(
            f"Ce point est recouvert par {describe(hit) if hit else 'aucune fenêtre'}, pas par {describe(hwnd)}. "
            "Rien n'a été cliqué."
        )


@contextlib.contextmanager
def input_target(hwnd: int, *points: tuple[int, int], activate: bool = True, action: str = "L'entrée physique"):
    """One physical input transaction: the input lock is held from the foreground check to the last input.

    Checked before taking the lock, the target could lose the foreground while another agent held it (up to 5 s)
    and the input would land in whatever window that agent left in front. activate=False never takes the
    foreground: the target must already have it. Mutexes are re-entrant per thread, so the input primitives called
    inside take the lock again without waiting.
    """
    with input_lock():
        if activate:
            ensure_input_target(hwnd)
        elif hwnd != SCREEN and foreground() != hwnd:
            raise ComputerError(
                f"{action} requiert la mise au premier plan de {describe(hwnd)}. "
                "Pour ne pas interrompre le travail de Julien, passez foreground=True. Rien n'a été envoyé."
            )
        for point in points:
            ensure_point(hwnd, *point)
        yield


# -----------------------------------------------------------------------------
# Mouse
# -----------------------------------------------------------------------------
def move_cursor(x: int, y: int) -> None:
    SetCursorPos(x, y)
    _send(_mouse_input(MOUSEEVENTF_MOVE))  # A real move event, so hover handlers fire.
    time.sleep(0.03)


def click_at(x: int, y: int, button: str = "left", count: int = 1) -> None:
    if button not in _BUTTONS:
        raise ComputerError(f"Bouton inconnu : {button!r} (left, right, middle).")
    if not 1 <= count <= 3:
        raise ComputerError("click_count doit valoir 1, 2 ou 3.")
    down, up = _BUTTONS[button]
    with input_lock():
        move_cursor(x, y)
        for _ in range(count):
            _send(_mouse_input(down))
            time.sleep(0.02)
            _send(_mouse_input(up))
            time.sleep(0.04)


def scroll_at(x: int, y: int, direction: str, amount: int) -> None:
    flags, sign = {
        "up": (MOUSEEVENTF_WHEEL, 1),
        "down": (MOUSEEVENTF_WHEEL, -1),
        "right": (MOUSEEVENTF_HWHEEL, 1),
        "left": (MOUSEEVENTF_HWHEEL, -1),
    }.get(direction, (None, 0))
    if flags is None:
        raise ComputerError(f"Direction inconnue : {direction!r} (up, down, left, right).")
    with input_lock():
        move_cursor(x, y)
        for _ in range(max(1, min(amount, 50))):
            _send(_mouse_input(flags, sign * WHEEL_DELTA))
            time.sleep(0.02)


def drag(
    start: tuple[int, int] | int,
    end: tuple[int, int] | int | None = None,
    steps: int = 20,
    to_x: int | None = None,
    to_y: int | None = None,
    hwnd: int | None = None,
    delay_ms: int = 15,
    foreground: bool = False,
    **kwargs: Any,
) -> Any:
    """Performs a smooth mouse drag between two coordinates.

    Supports both Claude tuple signature (start=(x1, y1), end=(x2, y2), steps=20)
    and Antigravity signature (from_x, from_y, to_x, to_y, hwnd=..., steps=20).
    """
    ensure_default_desktop()
    steps = max(1, int(steps))
    if hwnd and not IsWindow(hwnd):
        raise ComputerError("Fenêtre cible introuvable pour le glisser-déposer.")

    if isinstance(start, (tuple, list)) and isinstance(end, (tuple, list)):
        # Screen coordinates. Without hwnd the caller owns the target check (the adapters hold input_target).
        s_from, s_to = (int(start[0]), int(start[1])), (int(end[0]), int(end[1]))
        with input_target(hwnd or SCREEN, s_from, s_to, activate=foreground, action="Le glisser-déposer à la souris"):
            _drag_path(s_from, s_to, steps, delay_ms)
        return None

    from_x = int(start)
    from_y = int(end if end is not None else 0)
    target_to_x = int(to_x if to_x is not None else from_x)
    target_to_y = int(to_y if to_y is not None else from_y)
    target_hwnd = hwnd or _handle(GetForegroundWindow())
    if not target_hwnd or not IsWindow(target_hwnd):
        raise ComputerError("Fenêtre cible introuvable pour le glisser-déposer.")

    with input_target(target_hwnd, activate=foreground, action="Le glisser-déposer à la souris"):
        # Measured once the target is in front: activation may restore or move it.
        s_from = _window_point(target_hwnd, from_x, from_y)
        s_to = _window_point(target_hwnd, target_to_x, target_to_y)
        ensure_point(target_hwnd, *s_from)
        ensure_point(target_hwnd, *s_to)
        _drag_path(s_from, s_to, steps, delay_ms)
    return {"success": True, "from": (from_x, from_y), "to": (target_to_x, target_to_y), "steps": steps}


def _drag_path(start: tuple[int, int], end: tuple[int, int], steps: int, delay_ms: int) -> None:
    """Left button down at start, a real move event at every step, and the button always released."""
    down, up = _BUTTONS["left"]
    with input_lock():
        move_cursor(*start)
        _send(_mouse_input(down))
        time.sleep(0.08)
        try:
            for step in range(1, steps + 1):
                SetCursorPos(
                    round(start[0] + (end[0] - start[0]) * step / steps),
                    round(start[1] + (end[1] - start[1]) * step / steps),
                )
                _send(_mouse_input(MOUSEEVENTF_MOVE))
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000)
            time.sleep(0.05)
        finally:
            _send(_mouse_input(up))


# -----------------------------------------------------------------------------
# Keyboard
# -----------------------------------------------------------------------------
def _key_vks(name: str, bare: bool = False) -> list[int]:
    """Virtual keys for one key name, including the modifiers the current layout needs for the character.

    Inside a combination, letters and digits are physical keys (Ctrl+1 means the key labelled 1). Alone, a
    character is typed as itself: a bare '2' on AZERTY needs Shift, a bare 'A' needs Shift too.
    """
    lowered = name.lower()
    if lowered in ("plus", "minus"):
        name, lowered = ("+", "+") if lowered == "plus" else ("-", "-")
    if lowered in _KEY_NAMES:
        return [_KEY_NAMES[lowered]]
    if len(name) != 1:
        raise ComputerError(f"Touche inconnue : {name!r}.")
    if name.isascii() and name.isalnum() and not bare:
        return [ord(name.upper())]
    scan = VkKeyScanW(name)
    if scan == -1:
        raise ComputerError(
            f"La touche {name!r} n'existe pas sur la disposition clavier actuelle : utilisez computer_type_text."
        )
    shift_state, vk = (scan >> 8) & 0xFF, scan & 0xFF
    modifiers = [vk_ for bit, vk_ in ((1, VK_SHIFT), (2, VK_CONTROL), (4, VK_MENU)) if shift_state & bit]
    return [*modifiers, vk]


def parse_combo(combo: str) -> list[int]:
    """'ctrl+shift+p' → virtual keys in press order; a trailing '++' means the plus key."""
    combo = combo.strip()
    if not combo:
        raise ComputerError("Combinaison de touches vide.")
    names = combo[:-2].split("+") + ["+"] if combo.endswith("++") else combo.split("+")
    vks: list[int] = []
    for name in names:
        if not name:
            raise ComputerError(f"Combinaison mal formée : {combo!r}.")
        for vk in _key_vks(name, bare=len(names) == 1):
            if vk not in vks:
                vks.append(vk)
    return vks


def press_combo(combo: str) -> None:
    vks = parse_combo(combo)
    try:
        _send(*(_key_input(vk, up=False) for vk in vks))
        time.sleep(0.03)
    finally:  # Never leave a modifier logically held down.
        _send(*(_key_input(vk, up=True) for vk in reversed(vks)))
    time.sleep(0.02)


def utf16_units(char: str) -> list[int]:
    encoded = char.encode("utf-16-le")
    return [int.from_bytes(encoded[i : i + 2], "little") for i in range(0, len(encoded), 2)]


def type_unicode(text: str) -> None:
    """Layout-independent typing; newlines and tabs become real Enter and Tab presses."""
    for char in text.replace("\r\n", "\n").replace("\r", "\n"):
        if char == "\n":
            press_combo("enter")
        elif char == "\t":
            press_combo("tab")
        else:
            units = utf16_units(char)
            _send(*(item for unit in units for item in (_unicode_input(unit, False), _unicode_input(unit, True))))
            time.sleep(0.004)


# -----------------------------------------------------------------------------
# Unified Antigravity & High-Level UIA Engine Primitives
# -----------------------------------------------------------------------------
_element_cache: dict[int, Any] = {}
_cached_window_hwnd: int = 0
_cache_generation: float = 0.0


def get_window_rect(hwnd: int) -> dict[str, int]:
    """Retrieves visible bounding rectangle of a window."""
    left, top, right, bottom = frame_bounds(hwnd)
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def focus_window(
    hwnd: int | None = None,
    title: str | None = None,
    process_name_filter: str | None = None,
) -> dict[str, Any]:
    """Brings the target application window to the foreground and restores if minimized."""
    ensure_default_desktop()
    target_hwnd = hwnd
    if not target_hwnd:
        target_hwnd = find_window(title=title, process=process_name_filter)
    if not target_hwnd or not IsWindow(target_hwnd):
        raise ComputerError("Fenêtre introuvable avec les critères spécifiés.")
    success = bring_to_front(target_hwnd)
    pid = window_pid(target_hwnd)
    return {
        "hwnd": target_hwnd,
        "title": window_title(target_hwnd),
        "process_name": process_name(pid) if pid else "",
        "success": success,
    }


def is_point_occluded(x: int, y: int, target_hwnd: int) -> bool:
    """Checks whether the screen coordinate (x, y) is covered by another top-level window."""
    if not target_hwnd:
        return False
    pt = POINT(x, y)
    hit = _handle(WindowFromPoint(pt))
    if not hit:
        return False
    hit_root = _handle(GetAncestor(hit, GA_ROOT))
    target_root = _handle(GetAncestor(target_hwnd, GA_ROOT))
    return hit != target_hwnd and hit_root != target_root and hit_root != target_hwnd


def capture_window_background_gdi(hwnd: int) -> Image.Image | None:
    """Captures a window surface directly in memory via PrintWindow without bringing it to front."""
    if not hwnd or not IsWindow(hwnd) or IsIconic(hwnd):
        return None
    rect = RECT()
    GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None

    hdc_screen = GetDC(0)
    hdc_mem = CreateCompatibleDC(hdc_screen)
    hbm = CreateCompatibleBitmap(hdc_screen, w, h)
    prev = SelectObject(hdc_mem, hbm)
    try:
        res = PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
        if not res:
            return None
        buf = ctypes.create_string_buffer(w * h * 4)
        GetBitmapBits(hbm, len(buf), buf)
        img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)

        stat = ImageStat.Stat(img.convert("L"))
        if stat.stddev[0] < 2.0:
            return None
        return img
    except Exception:
        return None
    finally:
        SelectObject(hdc_mem, prev)
        DeleteObject(hbm)
        DeleteDC(hdc_mem)
        ReleaseDC(0, hdc_screen)


def capture_window_image(
    hwnd: int | None = None,
    full_screen: bool = False,
    max_dimension: int = 1568,
    quality: int = 80,
    return_meta: bool = False,
    elements_to_annotate: list[dict[str, Any]] | None = None,
) -> tuple[bytes, dict[str, Any]] | bytes:
    """Captures a window or full screen with adaptive WebP compression guaranteed < 200 KB."""
    ensure_default_desktop()
    fg_hwnd = foreground()
    target_hwnd = hwnd or (0 if full_screen else fg_hwnd)
    capture_mode = "offscreen_gdi"
    img: Image.Image | None = None
    region: dict[str, Any] = {}

    if not full_screen and target_hwnd and target_hwnd != fg_hwnd:
        img = capture_window_background_gdi(target_hwnd)
        if img is not None:
            region = get_window_rect(target_hwnd)
        else:
            capture_mode = "screen_fallback"

    if img is None:
        capture_mode = "screen_fallback"
        with mss.MSS() as sct:
            if full_screen or not target_hwnd:
                mon = sct.monitors[0]
                region = {"left": mon["left"], "top": mon["top"], "width": mon["width"], "height": mon["height"]}
            else:
                rect = get_window_rect(target_hwnd)
                if rect["width"] <= 0 or rect["height"] <= 0:
                    raise ComputerError("Dimensions de fenêtre invalides pour la capture.")
                region = rect
            shot = sct.grab(region)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    if elements_to_annotate:
        try:
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

    # Anti-Crash 400 enforcement: guarantee WebP < 200 KB (target <= 195 KB)
    current_q = quality
    current_img = img
    max_allowed = 195 * 1024

    buf = io.BytesIO()
    current_img.save(buf, format="WEBP", quality=current_q, method=4)
    data = buf.getvalue()

    while len(data) > max_allowed and current_q > 20:
        current_q -= 15
        buf = io.BytesIO()
        current_img.save(buf, format="WEBP", quality=current_q, method=4)
        data = buf.getvalue()

    while len(data) > max_allowed and current_img.width > 320:
        new_w = int(current_img.width * 0.8)
        new_h = int(current_img.height * 0.8)
        current_img = current_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        current_img.save(buf, format="WEBP", quality=max(current_q, 30), method=4)
        data = buf.getvalue()

    if return_meta:
        meta = {
            "original_bounds": region,
            "original_size": (region.get("width", 0), region.get("height", 0)),
            "captured_size": current_img.size,
            "width": current_img.width,
            "height": current_img.height,
            "scale_factor": round(current_img.size[0] / max(1, region.get("width", 1)), 4),
            "capture_mode": capture_mode,
            "size_bytes": len(data),
        }
        return data, meta

    return data


def cleanup_screenshot_cache(max_files: int = 50, max_age_hours: float = 24.0) -> int:
    """Removes old cached screenshots from ~/.nexusagy/screenshots."""
    cache_dir = Path.home() / ".nexusagy" / "screenshots"
    if not cache_dir.exists():
        return 0
    now = time.time()
    max_age_sec = max_age_hours * 3600.0
    files = list(cache_dir.glob("*.webp")) + list(cache_dir.glob("*.png"))
    removed = 0
    for f in files:
        try:
            if now - f.stat().st_mtime > max_age_sec:
                f.unlink(missing_ok=True)
                removed += 1
        except Exception:
            pass
    remaining = [f for f in files if f.exists()]
    if len(remaining) > max_files:
        remaining.sort(key=lambda p: p.stat().st_mtime)
        for f in remaining[:-max_files]:
            try:
                f.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass
    return removed


def get_window_state(
    hwnd: int | None = None,
    max_elements: int = 50,
    capture_screenshot: bool = False,
    output_path: str | None = None,
    max_depth: int = 30,
    time_budget: float = 1.618,
    include_data_url: bool = False,
    annotate_screenshot: bool = False,
) -> dict[str, Any]:
    """Extracts compact UI Automation interactive elements and optional WebP screenshot with Gemini box_2d."""
    global _element_cache, _cached_window_hwnd, _cache_generation
    ensure_default_desktop()
    target_hwnd = hwnd or foreground()
    if not target_hwnd or not IsWindow(target_hwnd):
        raise ComputerError("Aucune fenêtre active détectée.")

    win_rect = get_window_rect(target_hwnd)
    w_width = max(1, win_rect["width"])
    w_height = max(1, win_rect["height"])
    title = window_title(target_hwnd)
    pid = window_pid(target_hwnd)
    pname = process_name(pid)

    elements: list[dict[str, Any]] = []
    _element_cache.clear()
    _cached_window_hwnd = target_hwnd
    _cache_generation = time.time()

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

                        if (
                            c_rect.right <= win_rect["left"]
                            or c_rect.bottom <= win_rect["top"]
                            or c_rect.left >= win_rect["right"]
                            or c_rect.top >= win_rect["bottom"]
                        ):
                            continue

                        ctype = child.ControlTypeName
                        if ctype in _INTERACTIVE_TYPES and cw > 0 and ch > 0:
                            idx = len(elements) + 1
                            _element_cache[idx] = child

                            rel_l = c_rect.left - win_rect["left"]
                            rel_t = c_rect.top - win_rect["top"]
                            rel_r = c_rect.right - win_rect["left"]
                            rel_b = c_rect.bottom - win_rect["top"]
                            rel_cx = rel_l + cw // 2
                            rel_cy = rel_t + ch // 2

                            val_str = ""
                            try:
                                val_pat = child.GetValuePattern()
                                if val_pat:
                                    val_str = val_pat.Value or ""
                            except Exception:
                                pass

                            elements.append(
                                {
                                    "index": idx,
                                    "type": ctype.replace("Control", ""),
                                    "name": (child.Name or "")[:60],
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
        "process_name": pname,
        "bounds": win_rect,
        "element_count": len(elements),
        "elements": elements,
    }

    if capture_screenshot or output_path:
        annotate_list = elements if annotate_screenshot else None
        webp_bytes, meta = capture_window_image(
            target_hwnd, return_meta=True, elements_to_annotate=annotate_list
        )
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
            import base64

            result["screenshot_data_url"] = f"data:image/webp;base64,{base64.b64encode(webp_bytes).decode('ascii')}"

    return result


def _legacy_target(hwnd: int | None) -> int:
    """Target of a window-relative action: hwnd, or the foreground window; 0 means screen coordinates."""
    ensure_default_desktop()
    target = hwnd or _handle(GetForegroundWindow())
    if target and not IsWindow(target):
        raise ComputerError(f"Fenêtre cible introuvable (hwnd={target}).")
    return target


def _cached_element(hwnd: int, index: int) -> Any:
    """Element [index] of the last listing made for hwnd: a listing of any other window is never used."""
    if hwnd and SESSION.elements_hwnd == hwnd and index in SESSION.elements:
        return SESSION.elements[index]
    if hwnd and _cached_window_hwnd == hwnd and index in _element_cache:
        return _element_cache[index]
    raise ComputerError(
        f"Élément [{index}] introuvable ou obsolète (STALE_ELEMENT) pour la fenêtre ciblée (hwnd={hwnd}) : "
        "relancez computer_get_window_state."
    )


def _window_point(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Screen point of (x, y) relative to the window's visible frame; (x, y) is already on the screen for SCREEN."""
    if hwnd == SCREEN:
        return x, y
    rect = get_window_rect(hwnd)
    return rect["left"] + x, rect["top"] + y


def _control_center(control: Any) -> tuple[int, int]:
    try:
        rect = control.BoundingRectangle
        return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
    except Exception as error:
        raise ComputerError(f"Impossible d'obtenir les coordonnées de l'élément : {error}") from error


def click(
    hwnd: int | None = None,
    element_index: int | None = None,
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    click_count: int = 1,
    foreground: bool = False,
) -> dict[str, Any]:
    """Clicks on an element [#N] (in background via UI Automation) or at (x, y) coordinates."""
    target_hwnd = _legacy_target(hwnd)
    ctrl = None
    if element_index is not None:
        ctrl = _cached_element(target_hwnd, element_index)
        if button == "left" and click_count == 1:
            effect = background_activate(ctrl)
            if effect:
                return {"success": True, "method": "uia_pattern", "effect": effect, "element_index": element_index}
    elif x is None or y is None:
        raise ComputerError("Spécifiez soit element_index soit (x, y).")

    with input_target(target_hwnd, activate=foreground, action="Le clic physique à la souris"):
        # Measured once the target is in front: activation may restore or move it.
        click_x, click_y = _control_center(ctrl) if ctrl is not None else _window_point(target_hwnd, x, y)
        ensure_point(target_hwnd, click_x, click_y)
        click_at(click_x, click_y, button=button, count=click_count)
    return {
        "success": True,
        "method": "physical_click",
        "x": click_x,
        "y": click_y,
        "button": button,
        "count": click_count,
    }


def mouse_move(
    x: int,
    y: int,
    hwnd: int | None = None,
    smooth: bool = True,
    steps: int = 10,
    duration_ms: int = 200,
    foreground: bool = False,
) -> dict[str, Any]:
    """Moves physical cursor to window coordinates (x, y). Requires foreground=True."""
    target_hwnd = _legacy_target(hwnd)
    with input_target(target_hwnd, activate=foreground, action="Le déplacement de la souris"):
        target_x, target_y = _window_point(target_hwnd, x, y)
        ensure_point(target_hwnd, target_x, target_y)
        if smooth and steps > 1:
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            start_x, start_y = pt.x, pt.y
            step_delay = (duration_ms / 1000.0) / steps
            for i in range(1, steps + 1):
                cur_x = int(start_x + (target_x - start_x) * (i / steps))
                cur_y = int(start_y + (target_y - start_y) * (i / steps))
                user32.SetCursorPos(cur_x, cur_y)
                if step_delay > 0:
                    time.sleep(step_delay)
        else:
            user32.SetCursorPos(target_x, target_y)

    return {"success": True, "x": target_x, "y": target_y, "smooth": smooth, "steps": steps}


def type_text(
    text: str,
    hwnd: int | None = None,
    element_index: int | None = None,
    clear_first: bool = False,
    foreground: bool = False,
) -> dict[str, Any]:
    """Types text into an element [#N] in background via ValuePattern without stealing focus."""
    target_hwnd = _legacy_target(hwnd)
    ctrl = None
    if element_index is not None:
        ctrl = _cached_element(target_hwnd, element_index)
        if set_value(ctrl, text, append=not clear_first):
            return {
                "success": True,
                "method": "uia_value_pattern",
                "element_index": element_index,
                "length": len(text),
            }

    with input_target(target_hwnd, activate=foreground, action="La saisie clavier physique"):
        if ctrl is not None and not focus_element(ctrl):
            raise ComputerError(
                f"[{element_index}] n'a pas pu recevoir le focus (disparu, désactivé ou non focusable) : "
                "relancez computer_get_window_state. Rien n'a été tapé."
            )
        if clear_first:
            press_combo("ctrl+a")
            press_combo("backspace")
        type_unicode(text)
    return {"success": True, "method": "physical_keyboard", "length": len(text)}


def press_key(keys: str, hwnd: int | None = None, foreground: bool = False) -> dict[str, Any]:
    """Presses key combination (e.g. 'ctrl+c', 'alt+f4', 'win+r', 'enter', 'ctrl+,')."""
    combo = "".join(keys.split())
    vks = parse_combo(combo)  # Validate before touching the foreground.
    target_hwnd = _legacy_target(hwnd)
    with input_target(target_hwnd, activate=foreground, action="L'envoi de touches physiques"):
        press_combo(combo)
    return {"success": True, "keys": keys, "vk_codes": vks}


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
    target_hwnd = _legacy_target(hwnd)

    if element_index is not None:
        curr = _cached_element(target_hwnd, element_index)
        scroll_pat = None
        for _ in range(15):
            if not curr:
                break
            try:
                sp = curr.GetScrollPattern()
                if sp and (
                    (delta_y != 0 and getattr(sp, "VerticallyScrollable", False))
                    or (delta_x != 0 and getattr(sp, "HorizontallyScrollable", False))
                ):
                    scroll_pat = sp
                    break
            except Exception:
                pass
            try:
                curr = curr.GetParentControl()
            except Exception:
                break
        if scroll_pat:
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

    with input_target(target_hwnd, activate=foreground, action="Le défilement par molette physique"):
        if x is not None and y is not None:
            scroll_x, scroll_y = _window_point(target_hwnd, x, y)
        elif target_hwnd != SCREEN:  # The window's center, never wherever the cursor happens to be.
            rect = get_window_rect(target_hwnd)
            scroll_x, scroll_y = rect["left"] + rect["width"] // 2, rect["top"] + rect["height"] // 2
        else:
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            scroll_x, scroll_y = pt.x, pt.y
        ensure_point(target_hwnd, scroll_x, scroll_y)
        if delta_y != 0:
            scroll_at(scroll_x, scroll_y, "up" if delta_y > 0 else "down", abs(delta_y))
        if delta_x != 0:
            scroll_at(scroll_x, scroll_y, "right" if delta_x > 0 else "left", abs(delta_x))
    return {"success": True, "delta_y": delta_y, "delta_x": delta_x}
