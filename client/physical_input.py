"""Entrées PHYSIQUES de Julien (clavier, boutons, molette et déplacements de la souris), distinguées des entrées
injectées (SendInput de NexusAGY, SetFocus d'UI Automation, autres agents).

GetLastInputInfo compte toute entrée, injectée comprise : NexusAGY se voyait lui-même « actif ». Raw Input donne le
périphérique d'origine : une entrée injectée n'en a pas (hDevice nul). Une fenêtre de premier niveau jamais affichée
reçoit ces notifications en arrière-plan (RIDEV_INPUTSINK), sur un fil dédié. Aucun crochet : rien ne
s'insère dans la chaîne d'entrée de Julien, aucune latence ajoutée, et le contenu des touches n'est ni lu ni gardé,
seulement l'instant de la dernière entrée physique (inspiré de NexusClaude/nexus-windows physical.py).

Repli si Raw Input est indisponible : GetLastInputInfo, en écartant les fenêtres de temps des injections de NexusAGY
(`injecting()` autour de chaque SendInput). Limite assumée du repli : une frappe de Julien pendant une injection de
NexusAGY (quelques millisecondes) est masquée, et les injections d'UI Automation ne sont pas écartées.

Une seule écoute par processus, même si le module est importé sous deux noms (« physical_input » et
« client.physical_input ») : l'état vit dans un objet partagé par sys.modules.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
import types
from collections import deque
from contextlib import contextmanager
from ctypes import wintypes

WM_INPUT, RID_INPUT, RIDEV_INPUTSINK = 0x00FF, 0x10000003, 0x00000100
RIM_TYPEMOUSE, RIM_TYPEKEYBOARD = 0, 1
HWND_MESSAGE = wintypes.HWND(-3)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
INJECTION_GRACE_MS = 60  # une injection est vue par GetLastInputInfo jusqu'à ce délai après son envoi


class _RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class _RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class _RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("_align", wintypes.USHORT),  # l'union ulButtons qui suit est alignée sur 4 octets
        ("usButtonFlags", wintypes.USHORT),  # (union ulButtons : drapeaux puis données de bouton)
        ("usButtonData", wintypes.USHORT),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", ctypes.c_long),
        ("lLastY", ctypes.c_long),
        ("ulExtraInformation", wintypes.ULONG),
    ]


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.DefWindowProcW.restype = LRESULT
_user32.RegisterClassW.argtypes = (ctypes.POINTER(_WNDCLASSW),)
_user32.RegisterClassW.restype = wintypes.ATOM
_user32.CreateWindowExW.argtypes = (
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
)
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.RegisterRawInputDevices.argtypes = (ctypes.POINTER(_RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT)
_user32.RegisterRawInputDevices.restype = wintypes.BOOL
_user32.GetRawInputData.argtypes = (
    wintypes.HANDLE,
    wintypes.UINT,
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.UINT),
    wintypes.UINT,
)
_user32.GetRawInputData.restype = wintypes.UINT
_user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
_user32.GetMessageW.restype = wintypes.BOOL
_user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
_user32.DispatchMessageW.restype = LRESULT
_user32.GetLastInputInfo.argtypes = (ctypes.POINTER(_LASTINPUTINFO),)
_user32.GetLastInputInfo.restype = wintypes.BOOL
_kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetTickCount.argtypes = ()
_kernel32.GetTickCount.restype = wintypes.DWORD

_HEADER = ctypes.sizeof(_RAWINPUTHEADER)


def _shared_state() -> types.SimpleNamespace:
    """État unique du processus (voir la note du module sur le double import)."""
    key = "_nexusagy_physical_input_state"
    holder = sys.modules.get(key)
    if holder is None:
        holder = types.ModuleType(key)
        holder.state = types.SimpleNamespace(  # pyright: ignore[reportAttributeAccessIssue]
            lock=threading.Lock(),
            started=threading.Event(),
            ready=threading.Event(),
            ok=False,
            last_input=0.0,  # monotonic de la dernière touche / bouton / molette physique (0 : aucune)
            last_move=0.0,  # monotonic du dernier déplacement physique de la souris
            listening_since=0.0,
            baseline_idle_s=0.0,  # inactivité (toutes entrées) au début de l'écoute : borne basse de l'inactivité physique
            counts={"keyboard": 0, "mouse_buttons": 0, "mouse_moves": 0, "injected": 0},
            proc=None,  # WNDPROC gardé vivant
            injections=deque(maxlen=128),  # (tick début, tick fin) des SendInput de NexusAGY
            injection_lock=threading.Lock(),
            last_foreign_tick=None,  # repli : tick de la dernière entrée qui n'est pas une injection de NexusAGY
        )
        sys.modules[key] = holder
    return holder.state


_S = _shared_state()


def _lastinput_tick() -> int | None:
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    return int(info.dwTime)


def _tick() -> int:
    return int(_kernel32.GetTickCount())


def _elapsed_ms(since_tick: int, now_tick: int | None = None) -> int:
    return ((now_tick if now_tick is not None else _tick()) - since_tick) & 0xFFFFFFFF


def lastinput_idle_s() -> float:
    """Inactivité selon GetLastInputInfo, injections comprises (borne basse de l'inactivité physique)."""
    tick = _lastinput_tick()
    return 999.0 if tick is None else _elapsed_ms(tick) / 1000.0


# --- Raw Input -------------------------------------------------------------------------------------------------
def _on_input(lparam: int) -> None:
    buffer = (ctypes.c_ubyte * 64)()
    size = wintypes.UINT(ctypes.sizeof(buffer))
    got = _user32.GetRawInputData(wintypes.HANDLE(lparam), RID_INPUT, buffer, ctypes.byref(size), _HEADER)
    if got == 0xFFFFFFFF or got < _HEADER:
        return
    header = _RAWINPUTHEADER.from_buffer(buffer)
    if not header.hDevice:  # entrée injectée (SendInput, UI Automation, autre programme) : pas un geste de Julien
        _S.counts["injected"] += 1
        return
    now = time.monotonic()
    if header.dwType == RIM_TYPEKEYBOARD:
        _S.last_input = now
        _S.counts["keyboard"] += 1
    elif header.dwType == RIM_TYPEMOUSE and got >= _HEADER + _RAWMOUSE.lLastY.offset + 4:
        mouse = _RAWMOUSE.from_buffer(buffer, _HEADER)
        if mouse.usButtonFlags:
            _S.last_input = now
            _S.counts["mouse_buttons"] += 1
        elif mouse.lLastX or mouse.lLastY:
            _S.last_move = now
            _S.counts["mouse_moves"] += 1


def _proc(hwnd, msg, wparam, lparam):
    if msg == WM_INPUT:
        try:
            _on_input(lparam)
        except Exception:  # noqa: BLE001 - la procédure de fenêtre ne doit jamais lever
            pass
    return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _loop() -> None:
    _S.listening_since = time.monotonic()
    _S.baseline_idle_s = lastinput_idle_s()
    try:
        _S.proc = WNDPROC(_proc)
        hinst = _kernel32.GetModuleHandleW(None)
        wc = _WNDCLASSW(lpfnWndProc=_S.proc, hInstance=hinst, lpszClassName="NexusAGYPhysicalInput")
        _user32.RegisterClassW(ctypes.byref(wc))
        hwnd = _user32.CreateWindowExW(0, wc.lpszClassName, None, 0, 0, 0, 0, 0, None, None, hinst, None)
        devices = (_RAWINPUTDEVICE * 2)(
            _RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd),  # clavier
            _RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, hwnd),  # souris
        )
        _S.ok = bool(hwnd) and bool(_user32.RegisterRawInputDevices(devices, 2, ctypes.sizeof(_RAWINPUTDEVICE)))
    except Exception:  # noqa: BLE001 - indisponible : repli GetLastInputInfo
        _S.ok = False
    finally:
        _S.ready.set()
    if not _S.ok:
        return
    msg = wintypes.MSG()
    while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        _user32.DispatchMessageW(ctypes.byref(msg))


def start(timeout_s: float = 2.0) -> bool:
    """Lance l'écoute (une fois par processus). Vrai si Raw Input est disponible."""
    with _S.lock:
        if not _S.started.is_set():
            _S.started.set()
            threading.Thread(target=_loop, name="nexusagy-physical-input", daemon=True).start()
    _S.ready.wait(timeout_s)
    return _S.ok


def available() -> bool:
    return bool(_S.ok)


def listening_s() -> float:
    return time.monotonic() - _S.listening_since if _S.ok else 0.0


def _raw_last(include_moves: bool) -> float:
    return max(_S.last_input, _S.last_move) if include_moves else _S.last_input


def raw_idle_s(include_moves: bool = True) -> float:
    """Inactivité PHYSIQUE (borne basse sûre) : depuis la dernière entrée physique vue ; si aucune depuis le début de
    l'écoute, durée d'écoute + inactivité GetLastInputInfo mesurée au début (qui compte aussi les injections, donc
    jamais plus longue que l'inactivité physique réelle)."""
    last = _raw_last(include_moves)
    if last:
        return time.monotonic() - last
    return listening_s() + _S.baseline_idle_s


# --- Repli : GetLastInputInfo sans les injections de NexusAGY --------------------------------------------------
@contextmanager
def injecting():
    """Encadre un envoi SendInput de NexusAGY : son instant est écarté du repli GetLastInputInfo."""
    begin = _tick()
    try:
        yield
    finally:
        with _S.injection_lock:
            _S.injections.append((begin, _tick() + INJECTION_GRACE_MS))


def _is_own_injection(tick: int) -> bool:
    with _S.injection_lock:
        windows = list(_S.injections)
    return any(_elapsed_ms(begin, tick) <= _elapsed_ms(begin, end) for begin, end in windows)


def _refresh_foreign_tick() -> int | None:
    tick = _lastinput_tick()
    if tick is None:
        return _S.last_foreign_tick
    if _S.last_foreign_tick is None or not _is_own_injection(tick):
        _S.last_foreign_tick = tick
    return _S.last_foreign_tick


def fallback_idle_s() -> float:
    tick = _refresh_foreign_tick()
    return 999.0 if tick is None else _elapsed_ms(tick) / 1000.0


# --- API commune -----------------------------------------------------------------------------------------------
def user_idle_s() -> float:
    """Secondes depuis le dernier geste physique de Julien (Raw Input), sinon repli GetLastInputInfo sans les
    injections de NexusAGY."""
    if available():
        return raw_idle_s()
    return fallback_idle_s()


def mark() -> tuple[float, int]:
    """Repère de début d'une action physique, pour user_touched_since."""
    _refresh_foreign_tick()
    return (time.monotonic(), _tick())


def user_touched_since(token: tuple[float, int], include_moves: bool = True) -> bool:
    """Julien a-t-il touché clavier ou souris (physiquement) depuis le repère `token` ?"""
    moment, tick = token
    if available() and _raw_last(include_moves) > moment:
        return True
    if tick > 0:
        foreign = _refresh_foreign_tick()
        if foreign is not None and 0 < _elapsed_ms(tick, foreign) < 0x7FFFFFFF:
            return True
    return False


def method() -> str:
    return "raw_input" if available() else "getlastinputinfo_sans_injections"


def summary() -> dict:
    """Diagnostic : nombres d'événements vus depuis le démarrage, jamais leur contenu."""
    idle = user_idle_s()
    return {
        "method": method(),
        "idle_s": round(idle, 1),
        "listening_s": round(listening_s(), 1),
        "counts": dict(_S.counts),
    }
