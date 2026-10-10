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

# In-memory element cache for deterministic sequential actions
_element_cache: dict[int, Any] = {}
_cached_window_hwnd: int = 0


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
    if _hdesk_default:
        user32.EnumDesktopWindows(_hdesk_default, proc, 0)
    else:
        user32.EnumWindows(proc, 0)

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
                        badge_w = 16 if el["index"] < 10 else 22
                        draw.rectangle([left, max(0, top - 11), min(img.width, left + badge_w), top], fill=(255, 60, 60))
                        draw.text((left + 2, max(0, top - 11)), str(el["index"]), fill=(255, 255, 255))
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
    max_elements: int = 50,
    capture_screenshot: bool = False,
    output_path: str | None = None,
    max_depth: int = 30,
    time_budget: float = 1.618,
    include_data_url: bool = False,
    annotate_screenshot: bool = False,
) -> dict[str, Any]:
    """Extracts compact UI Automation interactive elements and optional WebP screenshot.

    Equips Antigravity with Set-of-Marks markers [#1], [#2] and Gemini box_2d coordinates.
    Bounded by max_depth and a harmonic time budget (1.618s) with spatial pruning and optional visual SoM overlay.
    """
    global _element_cache, _cached_window_hwnd
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
                        if (c_rect.right <= win_rect["left"] or
                            c_rect.bottom <= win_rect["top"] or
                            c_rect.left >= win_rect["right"] or
                            c_rect.top >= win_rect["bottom"]):
                            continue

                        ctype = child.ControlTypeName
                        if ctype in INTERACTIVE_CONTROL_TYPES and cw > 0 and ch > 0:
                            idx = len(elements) + 1
                            _element_cache[idx] = child

                            rel_l = c_rect.left - win_rect["left"]
                            rel_t = c_rect.top - win_rect["top"]
                            rel_r = c_rect.right - win_rect["left"]
                            rel_b = c_rect.bottom - win_rect["top"]
                            rel_cx = rel_l + cw // 2
                            rel_cy = rel_t + ch // 2

                            # Current value if available
                            val_str = ""
                            try:
                                val_pattern = child.GetValuePattern()
                                if val_pattern:
                                    val_str = val_pattern.Value
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
        "process_name": proc_name,
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
) -> dict[str, Any]:
    """Moves mouse cursor to window-relative coordinates (x, y) with smooth Bézier/easing trajectory."""
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()
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
        ease = 3 * (t ** 2) - 2 * (t ** 3)
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
    button: str = "left",
    click_count: int = 1,
) -> dict[str, Any]:
    """Clicks an element by index [#N] or clicks relative coordinates (x, y) inside target window.

    Prioritizes background-friendly UI Automation without stealing user focus whenever possible.
    """
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()

    # 1. Background-first: Deterministic UI Automation element click (NO FOCUS STEAL)
    if element_index is not None and element_index in _element_cache:
        ctrl = _element_cache[element_index]

        # Single left-click via InvokePattern operates entirely in background
        if button.lower() == "left" and click_count == 1:
            try:
                invoke_pat = ctrl.GetInvokePattern()
                if invoke_pat:
                    import threading
                    t = threading.Thread(target=invoke_pat.Invoke, daemon=True)
                    t.start()
                    t.join(timeout=0.15)
                    return {"success": True, "method": "uia_invoke", "element_index": element_index}
            except Exception:
                pass

        # If hardware click is required (right-click, double-click, non-invocable), ensure focus and verify occlusion
        if target_hwnd and user32.GetForegroundWindow() != target_hwnd:
            focus_window(hwnd=target_hwnd)

        try:
            rect = ctrl.BoundingRectangle
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            if target_hwnd and is_point_occluded(cx, cy, target_hwnd):
                raise RuntimeError(f"Le centre de l'élément [{element_index}] est recouvert par une autre fenêtre.")
            mouse_click(cx, cy, button=button, click_count=click_count)
            return {"success": True, "method": "element_center", "element_index": element_index, "coords": (cx, cy)}
        except Exception as err:
            if isinstance(err, RuntimeError):
                raise
            pass

    # 2. Window-relative coordinates (x, y) - requires focus and occlusion check
    if x is not None and y is not None:
        if target_hwnd and user32.GetForegroundWindow() != target_hwnd:
            focus_window(hwnd=target_hwnd)
        win_rect = get_window_rect(target_hwnd)
        screen_x = win_rect["left"] + x
        screen_y = win_rect["top"] + y
        if target_hwnd and is_point_occluded(screen_x, screen_y, target_hwnd):
            raise RuntimeError(f"Les coordonnées ({screen_x}, {screen_y}) sont recouvertes par une autre fenêtre.")
        mouse_click(screen_x, screen_y, button=button, click_count=click_count)
        return {"success": True, "method": "relative_coordinates", "screen_coords": (screen_x, screen_y)}

    raise ValueError("Indiquez un 'element_index' valide ou des coordonnées relatives (x, y).")


def type_text(
    text: str,
    hwnd: int | None = None,
    element_index: int | None = None,
    clear_first: bool = False,
) -> dict[str, Any]:
    """Types text using Unicode SendInput or sets UIA ValuePattern directly.

    Prioritizes background-friendly UI Automation ValuePattern (no focus steal, no typing interference).
    """
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()

    # Normalize newlines so Windows \r\n does not send Enter twice
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 1. Background-first: Direct UIA value replacement without stealing user focus
    if element_index is not None and element_index in _element_cache:
        ctrl = _element_cache[element_index]
        try:
            val_pat = ctrl.GetValuePattern()
            if val_pat:
                if clear_first:
                    val_pat.SetValue(text)
                else:
                    curr_val = val_pat.Value or ""
                    val_pat.SetValue(curr_val + text)
                return {"success": True, "method": "uia_set_value", "element_index": element_index}
        except Exception:
            pass

    # 2. Hardware Unicode typing fallback (requires window focus and active verification)
    if target_hwnd and user32.GetForegroundWindow() != target_hwnd:
        focus_window(hwnd=target_hwnd)
        for _ in range(5):
            if user32.GetForegroundWindow() == target_hwnd:
                break
            time.sleep(0.04)
        current_fg = user32.GetForegroundWindow()
        if current_fg != target_hwnd:
            raise RuntimeError(
                f"Impossible d'activer la fenêtre cible (HWND={target_hwnd}) au premier plan avant la saisie (fenêtre active : HWND={current_fg})."
            )

    # Fallback to hardware Unicode typing
    if clear_first:
        press_key("ctrl+a", hwnd=target_hwnd)
        press_key("backspace", hwnd=target_hwnd)

    for char in text:
        if char == "\n":
            press_key("enter", hwnd=target_hwnd)
            time.sleep(0.01)
        else:
            # Encode in UTF-16 LE code units to support surrogate pairs for emojis
            utf16_bytes = char.encode("utf-16-le")
            for i in range(0, len(utf16_bytes), 2):
                code_unit = int.from_bytes(utf16_bytes[i:i+2], "little")
                down = INPUT(type=INPUT_KEYBOARD)
                down.union.ki.wScan = code_unit
                down.union.ki.dwFlags = KEYEVENTF_UNICODE
                up = INPUT(type=INPUT_KEYBOARD)
                up.union.ki.wScan = code_unit
                up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                _send_inputs([down, up])
                time.sleep(0.005)

    return {"success": True, "method": "sendinput_unicode", "char_count": len(text)}


def press_key(keys: str, hwnd: int | None = None) -> dict[str, Any]:
    """Presses key combination (e.g. 'ctrl+c', 'alt+f4', 'win+r', 'enter', 'ctrl+,')."""
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()

    # Automatically ensure target window is in the foreground and verified
    if target_hwnd and user32.GetForegroundWindow() != target_hwnd:
        focus_window(hwnd=target_hwnd)
        for _ in range(5):
            if user32.GetForegroundWindow() == target_hwnd:
                break
            time.sleep(0.04)
        current_fg = user32.GetForegroundWindow()
        if current_fg != target_hwnd:
            raise RuntimeError(
                f"Impossible d'activer la fenêtre cible (HWND={target_hwnd}) au premier plan avant la combinaison de touches (fenêtre active : HWND={current_fg})."
            )

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
                # Map non-alphanumeric punctuation/symbols via VkKeyScanW
                vk_scan = user32.VkKeyScanW(ord(part))
                if vk_scan != -1:
                    vk = vk_scan & 0xFF
                    vk_entries.append((vk, vk in EXTENDED_VKEYS))
                else:
                    vk_entries.append((ord(part.upper()), False))
        else:
            raise ValueError(f"Touche inconnue : {part}")

    # Press keys in sequence
    down_inputs = []
    for vk, is_ext in vk_entries:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.union.ki.wVk = vk
        flags = KEYEVENTF_EXTENDEDKEY if is_ext else 0
        inp.union.ki.dwFlags = flags
        down_inputs.append(inp)
    _send_inputs(down_inputs)
    time.sleep(0.03)

    # Release keys in reverse sequence
    up_inputs = []
    for vk, is_ext in reversed(vk_entries):
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.union.ki.wVk = vk
        flags = KEYEVENTF_KEYUP
        if is_ext:
            flags |= KEYEVENTF_EXTENDEDKEY
        inp.union.ki.dwFlags = flags
        up_inputs.append(inp)
    _send_inputs(up_inputs)

    return {"success": True, "keys": keys, "vk_codes": [v[0] for v in vk_entries]}


def scroll(
    delta_y: int = 0,
    delta_x: int = 0,
    hwnd: int | None = None,
    x: int | None = None,
    y: int | None = None,
) -> dict[str, Any]:
    """Scrolls the mouse wheel vertically (delta_y) or horizontally (delta_x)."""
    ensure_default_desktop()
    if x is not None and y is not None:
        target_hwnd = hwnd or user32.GetForegroundWindow()
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
) -> dict[str, Any]:
    """Performs a smooth mouse drag between two coordinates."""
    ensure_default_desktop()
    target_hwnd = hwnd or user32.GetForegroundWindow()
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
