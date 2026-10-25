#!/usr/bin/env python3
"""
NexusWindows pour Antigravity, moteur : le bureau Windows de Julien piloté en arrière-plan (UI Automation, messages Win32),
vraie souris/clavier en repli seulement.

Garde-fous DANS le code (revue de Claude du 17/10/2026, pensés pour un modèle rapide et crédule) : fenêtre toujours
nommée (jamais celle de devant par défaut), libellé ambigu refusé avec les candidats, premier plan relu juste avant
chaque entrée physique, `confirm=true` exigé seulement pour ce qui part chez un tiers, coûte de l'argent ou ne se
rattrape pas (payer, envoyer, publier, supprimer définitivement, désinstaller, formater, réinitialiser, résilier…), que
le geste soit un clic, une touche ou un submit (2.8.0), effet « relu » seulement sur une preuve exacte.
Autonomie (2.7.0) : banques, champs mot de passe, Chrome/Edge et tout chemin ouvrable sont permis ; gestionnaires de
mots de passe jamais lus ni pilotés (accord « garde-fous » du 18/10, 2.8.0).
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import io
import math
import os
import re
import sys
import threading
import time
import unicodedata
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import Any, Literal, overload

# Politique commune des garde-fous de bureau (Claude et Antigravity) : NexusWindows/commun/garde-fous.json, lue par
# commun/garde_fous.py. Accord « garde-fous » du 18/10/2026 (journal de la trinité). Illisible : le module ne se
# charge pas (échec fermé : aucun outil de bureau sans politique).
SHARED_DIR = Path(__file__).resolve().parent.parent.parent / "commun"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))
import garde_fous  # noqa: E402

sys.dont_write_bytecode = True


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi
gdi32 = ctypes.windll.gdi32

try:
    from . import (
        agent_guard,
        cdp_wheel,
        computer_logger,
        emergency_stop,
        physical_input,
        uia_scroll,
        win32_controls,
    )
except ImportError:
    import agent_guard
    import cdp_wheel
    import computer_logger
    import emergency_stop
    import physical_input
    import uia_scroll
    import win32_controls

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
user32.EnumClipboardFormats.argtypes = [UINT]
user32.EnumClipboardFormats.restype = UINT
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = UINT
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
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t

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
INVOKE_TIMEOUT_S = 1.0  # au-delà, Invoke est tenu pour envoyé mais bloqué (fenêtre modale) : jamais de second clic

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

try:
    try:
        from . import uia_fast  # noqa: E402
    except ImportError:
        import uia_fast  # noqa: E402
except Exception:  # noqa: BLE001 - comtypes/UIAutomationCore indisponible : lecture pas à pas (signalée)
    uia_fast = None

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

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


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
user32.GetLastInputInfo.restype = BOOL
kernel32.GetTickCount.argtypes = []
kernel32.GetTickCount.restype = wintypes.DWORD


def get_idle_duration_s() -> float:
    """Secondes depuis le dernier geste PHYSIQUE de Julien (clavier, souris).

    Raw Input (fil dédié, entrées injectées écartées : SendInput de NexusAGY, SetFocus d'UI Automation) ; repli sur
    GetLastInputInfo sans les fenêtres de temps des injections de NexusAGY si Raw Input est indisponible."""
    try:
        physical_input.start(timeout_s=1.0)
        return float(physical_input.user_idle_s())
    except Exception:  # noqa: BLE001
        return 999.0


def wait_for_user_idle(threshold_s: float = 1.5, max_wait_s: float = 5.0) -> bool:
    """Waits for user physical input pause before stealing focus or moving cursor.

    Guarantees agents do not hijack keystrokes while Julien is typing.
    Returns True if user became idle, False if timed out after max_wait_s.
    """
    t0 = time.monotonic()
    while (time.monotonic() - t0) < max_wait_s:
        if get_idle_duration_s() >= threshold_s:
            return True
        time.sleep(0.05)
    return False


class UserInterruptError(RuntimeError):
    """Julien a repris son clavier ou sa souris pendant une action physique de NexusAGY : arrêt, main rendue."""


_guard_tokens = threading.local()


def _active_token() -> tuple[float, int] | None:
    stack = getattr(_guard_tokens, "stack", None)
    return stack[-1] if stack else None


def _checkpoint() -> None:
    """Point de contrôle d'une action physique : arrêt d'urgence, puis reprise en main par Julien (Raw Input)."""
    emergency_stop.check()
    token = _active_token()
    if token is not None and physical_input.user_touched_since(token):
        raise UserInterruptError(
            "Julien a repris le clavier ou la souris pendant l'action : arrêt au point de contrôle, premier plan "
            "rendu. Ne pas relancer tant qu'il travaille."
        )


# -----------------------------------------------------------------------------
# Politique physique : arrière-plan d'abord, vraie souris/clavier en REPLI seulement
# -----------------------------------------------------------------------------
class NeedsForegroundError(RuntimeError):
    """Aucune technique d'arrière-plan ne s'applique et la vraie souris/le vrai clavier ne sont pas autorisés
    (foreground=False) : rien n'a été envoyé. `what` : l'action et la raison, en clair et court."""

    def __init__(self, message: str, what: str = "") -> None:
        super().__init__(message)
        self.what = what or message


_policy_local = threading.local()


class _PhysicalPolicy:
    """Politique d'un lot act : `allow` = vraie souris/clavier permis en repli (foreground=True). La garde du
    lot (jeton commun tenu sans trou, fenêtre devant, premier plan rendu à la fin) n'est prise qu'au PREMIER geste
    physique réellement nécessaire : un lot que l'arrière-plan suffit à faire ne touche jamais au premier plan."""

    def __init__(self, allow: bool, target_hwnd: int = 0, lot: bool = False, accord: str = "") -> None:
        self.allow = allow
        self.target_hwnd = target_hwnd
        self.lot_wanted = lot
        self.lot_guard: Any = None
        self.physical_steps = 0
        self.accord = accord
        self.approved: set[str] = set()


def _current_policy() -> _PhysicalPolicy | None:
    return getattr(_policy_local, "current", None)


def _physical_allowed(foreground: bool) -> bool:
    policy = _current_policy()
    return policy.allow if policy is not None else bool(foreground)


class _no_physical:
    """Bloc où aucun geste physique n'est permis (traduction d'un raccourci en saisie d'arrière-plan)."""

    def __enter__(self) -> None:
        self._previous = _current_policy()
        _policy_local.current = _PhysicalPolicy(False)

    def __exit__(self, *exc: Any) -> None:
        _policy_local.current = self._previous


def _is_foreground(hwnd: int) -> bool:
    return bool(hwnd) and user32.GetForegroundWindow() == hwnd


class ForegroundLostError(RuntimeError):
    """La fenêtre visée n'est pas (ou plus) au premier plan juste avant une entrée physique : rien (de plus) n'est
    envoyé. Cas réel visé : SetForegroundWindow refusé par Windows, puis frappe + Entrée dans la messagerie de Julien."""


FRONT_WAIT_S = 0.5  # attente de la mise au premier plan demandée, relue avant le premier geste
_front_local = threading.local()


def _physical_target() -> int:
    """Fenêtre visée par la garde physique en cours (FocusGuard) sur ce fil, 0 sans garde."""
    stack = getattr(_front_local, "stack", None)
    return stack[-1] if stack else 0


def _target_in_front(target: int) -> bool:
    """Vrai si la fenêtre de premier plan est la cible ou la fenêtre racine de la cible."""
    if not target:
        return False
    front = int(user32.GetForegroundWindow() or 0)
    return bool(front) and (front == target or front == win32_controls.root_of(target))


def _require_front(what: str = "entrée physique") -> None:
    """Relu juste avant chaque SendInput et chaque déplacement du curseur : sans fenêtre visée, ou cible plus au
    premier plan → refus, rien n'est envoyé (jamais une frappe dans la fenêtre de Julien)."""
    target = _physical_target()
    if not target:
        raise ForegroundLostError(f"{what} sans fenêtre visée : refusée, rien n'a été envoyé.")
    if not _target_in_front(target):
        front = int(user32.GetForegroundWindow() or 0)
        raise ForegroundLostError(
            f"{what} : la fenêtre visée ({target}) n'est pas au premier plan (fenêtre {front} devant : Windows a refusé "
            "la mise au premier plan, ou une autre fenêtre est passée devant) ; arrêt, rien n'a été envoyé ailleurs."
        )


def _wait_front(target: int, timeout: float = FRONT_WAIT_S) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if _target_in_front(target):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)


def _physical_gate(target_hwnd: int, foreground: bool, what: str) -> None:
    """Point de passage obligé de tout geste physique : refus explicite (rien n'est envoyé) sans foreground=True ;
    sinon, dans un lot, prise unique de la garde du lot."""
    if not _physical_allowed(foreground):
        fam = win32_controls.family(target_hwnd) if target_hwnd and user32.IsWindow(target_hwnd) else "Inconnue"
        raise NeedsForegroundError(
            f"{what} : aucune technique d'arrière-plan ne s'applique ici ({fam}) ; rien n'a été envoyé. Viser "
            "l'élément par son libellé (target), ou foreground=True pour la vraie souris/le vrai clavier en repli.",
            what=f"{what} — impossible en arrière-plan ({fam}), rien n'a été envoyé",
        )
    policy = _current_policy()
    if policy is None:
        return
    policy.physical_steps += 1
    if policy.lot_wanted and policy.lot_guard is None and policy.target_hwnd:
        guard = FocusGuard(policy.target_hwnd, restore=True, purpose="lot au premier plan (act)")
        guard.__enter__()
        policy.lot_guard = guard


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

# Surfaces Windows qu'aucune application de la session ne peut piloter : bureau sécurisé (Winlogon) ou intégrité
# Système, où Windows bloque toute entrée simulée (UIPI) et toute lecture UIA. Refus clair et immédiat plutôt qu'un
# faux essai. Le reste (invite d'identifiants, Sécurité Windows, banques, mots de passe) est pilotable.
GARDE_FOUS_AGENT = "antigravity"  # catégories de blocage dur appliquées (garde-fous.json, « agents »)
PROTECTED_WINDOW_CLASSES: set[str] = garde_fous.hard_block_classes(GARDE_FOUS_AGENT)
PROTECTED_PROCESS_NAMES = garde_fous.hard_block_processes(GARDE_FOUS_AGENT)  # bureau sécurisé (UAC, verrouillage…)

# Gestionnaires de mots de passe : ni regard, ni capture, ni lecture UI Automation, ni action (accord Claude–Antigravity
# « garde-fous » du 18/10, journal de la trinité) : leur contenu n'arrive jamais au modèle. Préfixe du processus.
PASSWORD_MANAGER_PREFIXES = garde_fous.password_manager_prefixes()
PASSWORD_MANAGER_REASON = "gestionnaire de mots de passe ({proc}) : ni lu, ni capturé, ni piloté (blocage dur)"


class ProtectedWindowError(PermissionError):
    """Fenêtre jamais lue ni pilotée (gestionnaire de mots de passe, surface Windows protégée) : rien n'a été fait."""


def is_password_manager_process(proc: Any) -> bool:
    return str(proc or "").strip().lower().startswith(PASSWORD_MANAGER_PREFIXES)


BROWSER_PROCESSES = {"chrome.exe", "msedge.exe"}
BROWSER_NOTE = "Pour le web, nexus-browser est plus fiable."


def _plain(text: Any) -> str:
    """Texte comparable : sans accents ni casse, apostrophes et ponctuation ramenées à des espaces."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    bare = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", bare).split())


def browser_note(proc: Any) -> str:
    """Note courte pour une fenêtre Chrome/Edge : pilotable par le bureau, mais le pont NexusBrowser est plus fiable."""
    return BROWSER_NOTE if str(proc or "").lower() in BROWSER_PROCESSES else ""


def window_browser_note(hwnd: int) -> str:
    """BROWSER_NOTE si la fenêtre est celle de Chrome ou d'Edge, « » sinon (jamais d'erreur)."""
    try:
        if not hwnd or not user32.IsWindow(hwnd):
            return ""
        return browser_note(get_process_image_path(app_pid(hwnd))[1])
    except Exception:  # noqa: BLE001 - une note ne fait jamais échouer une action
        return ""


def is_protected_system_window(hwnd: int) -> tuple[bool, str]:
    """Fenêtre où toute action est refusée : surface Windows impossible à piloter (session, verrouillage, UAC) ou
    gestionnaire de mots de passe (jamais lu ni piloté)."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False, ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    cls_name = buf.value
    if cls_name in PROTECTED_WINDOW_CLASSES:
        return True, f"Fenêtre système protégée (classe: {cls_name})"

    pid = wintypes.DWORD(app_pid(hwnd))
    _, proc = get_process_image_path(pid.value)
    if proc.lower() in PROTECTED_PROCESS_NAMES:
        return True, f"surface Windows impossible à piloter ({proc} : bureau sécurisé ou intégrité Système)"
    if is_password_manager_process(proc):
        return True, PASSWORD_MANAGER_REASON.format(proc=proc)
    return False, ""


def ensure_readable(hwnd: int) -> None:
    """Refuse toute LECTURE (regard, arbre UIA, capture) d'une fenêtre protégée : ProtectedWindowError."""
    protected, reason = is_protected_system_window(hwnd)
    if protected:
        raise ProtectedWindowError(f"Lecture refusée : {reason}. Rien n'a été lu.")


def ensure_screen_readable() -> None:
    """Capture de tout l'écran refusée tant qu'un gestionnaire de mots de passe y est affiché."""
    for w in list_windows(visible_only=True):
        if is_password_manager_process(w.get("process_name")) and not user32.IsIconic(int(w["hwnd"])):
            raise ProtectedWindowError(
                f"Capture de l'écran refusée : {PASSWORD_MANAGER_REASON.format(proc=w.get('process_name'))} est "
                "affiché. Capturer une fenêtre nommée, ou attendre qu'il soit réduit."
            )


# -----------------------------------------------------------------------------
# Confirmation : ce qui part chez un tiers, coûte de l'argent ou ne se rattrape pas
# -----------------------------------------------------------------------------
# UNE liste commune (NexusWindows/commun/garde-fous.json, « confirmation »), facile à vider : payer, acheter, commander, virer de l'argent, envoyer un message, publier, supprimer
# définitivement ; depuis 2.8.0 aussi désinstaller, formater, réinitialiser, résilier, supprimer un compte, effacer les
# données. Tout le reste (supprimer simple, valider, confirmer, s'abonner, accepter…) passe sans confirm, sauf
# valider/confirmer dans une fenêtre qui parle de paiement ou de virement, et démarrer/OK dans celle d'un formatage
# (CONTEXT_CONFIRM). Verbes d'action seulement : « Boîte d'envoi », « Éléments envoyés », « Transferts » ne comptent pas.
# Réglage : NEXUS_AGY_CONFIRM=off (variable d'environnement du serveur MCP) désactive toute confirmation.
CONFIRM_PATTERNS: tuple[str, ...] = garde_fous.confirm_patterns()
# Verbe générique à confirmer seulement quand le TITRE de la fenêtre parle d'argent ou de formatage : (contexte,
# verbes, quoi). Titre seul (revue d'Antigravity) : un « Moyens de paiement acceptés » en bas de page, un IBAN cité
# dans un mail ou l'onglet « Virements » d'une banque ne bloquent pas tous les « OK » ; et aucune lecture d'arbre.
CONTEXT_CONFIRM: tuple[tuple[str, str, str], ...] = garde_fous.confirm_contexts()
CONFIRM_ENV = "NEXUS_AGY_CONFIRM"
CONFIRM_OFF_VALUES = {"off", "0", "false", "non", "no"}
# Éléments qui ne déclenchent rien par eux-mêmes : dossier, élément de liste ou d'arbre, onglet, en-tête, champ, case.
# Leur libellé (« Éléments envoyés ») n'exige jamais confirm. Les éléments d'ACTION (Button, SplitButton, MenuItem,
# Hyperlink) et ceux au rôle inconnu ou générique (Custom, Text, Image…) restent soumis à la règle.
NON_ACTION_ROLES = garde_fous.non_action_roles()


class ConfirmationRequiredError(PermissionError):
    """Action qui part chez un tiers ou coûte de l'argent, demandée sans confirm=true : rien n'a été fait."""


def confirmation_enabled() -> bool:
    """Confirmation active (défaut), sauf NEXUS_AGY_CONFIRM=off (lu à chaque appel)."""
    return os.environ.get(CONFIRM_ENV, "").strip().casefold() not in CONFIRM_OFF_VALUES


def irreversible_word(label: Any) -> str:
    """Mot d'action à confirmer (CONFIRM_PATTERNS) trouvé dans le libellé, accents, casse et apostrophes ignorés ;
    « » sinon (liste vide : jamais)."""
    if not CONFIRM_PATTERNS:
        return ""
    found = re.search(r"\b(" + "|".join(CONFIRM_PATTERNS) + r")\b", _plain(label))
    return found.group(0) if found else ""


_ACCORDS: garde_fous.Accords | None = None
_ACCORDS_LOCK = threading.Lock()


def get_accords() -> garde_fous.Accords:
    """Registre unique des accords liés à l'action exacte et des textes lus (provenance)."""
    global _ACCORDS
    with _ACCORDS_LOCK:
        if _ACCORDS is None:
            _ACCORDS = garde_fous.Accords()
        return _ACCORDS


def outward_word(label: Any, hwnd: int = 0) -> str:
    """Mot sortant pour ce libellé (envoyer, appeler, payer, publier, transférer...) : exige confirm=true ET accord.
    « » sinon (geste libre, ou destruction locale : confirm=true seul)."""
    if not CONFIRM_PATTERNS:
        return ""
    word = garde_fous.irreversible_word(label, garde_fous.outward_patterns())
    if word or not hwnd:
        return word
    plain = _plain(label)
    title = _window_title_plain(hwnd)
    for context, verbs, what in CONTEXT_CONFIRM:
        if "paiement" not in what:
            continue
        found = re.search(r"\b(" + verbs + r")\b", plain)
        if found and re.search(r"\b(" + context + r")\b", title):
            return f"{found.group(0)} (fenêtre de {what})"
    return ""


def _window_title_plain(hwnd: int) -> str:
    """Titre de la fenêtre, en texte comparable (« » si elle a disparu)."""
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return _plain(buf.value)


def _window_title_raw(hwnd: int) -> str:
    """Titre brut de la fenêtre, sans normalisation (« » si elle a disparu)."""
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value.strip()


def _window_process_name(hwnd: int) -> str:
    """Nom du processus exécutable de la fenêtre."""
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return get_process_image_path(pid.value)[1]
    except Exception:
        return ""


def field_contents(target_hwnd: int) -> list[str]:
    """« nom: valeur » des champs éditables de la fenêtre (Edit, Document), triés.
    Le contenu que l'accord lie (destinataire, objet, corps). Jamais un mot de passe."""
    if not target_hwnd or not user32.IsWindow(target_hwnd):
        return []
    fields: list[str] = []
    if uia_fast is not None:
        try:
            tree = _window_tree(target_hwnd, max_nodes=MAX_UIA_NODES, time_budget=1.5)
            for node in tree.nodes:
                if node.control_type not in ("Edit", "Document"):
                    continue
                if node.props.get("password") or is_password_field(
                    {
                        "name": node.name,
                        "props": node.props,
                        "hwnd": node.props.get("hwnd"),
                        "type": node.control_type,
                    }
                ):
                    continue
                val = node.props.get("value")
                if not str(val or "").strip() and node.props.get("hwnd"):
                    own_h = int(node.props.get("hwnd") or 0)
                    if own_h and user32.IsWindow(own_h):
                        val = win32_controls.get_text(own_h)
                val_str = " ".join(str(val or "").split())
                if val_str:
                    name_str = node.name or str(node.props.get("automation_id") or "").strip() or "champ"
                    fields.append(f"{name_str}: {val_str}")
        except Exception:
            pass
    if not fields and win32_controls.family(target_hwnd) in win32_controls.NATIVE_FAMILIES:
        for child in win32_controls.child_windows(target_hwnd):
            if win32_controls.is_class(child, win32_controls.EDIT_CLASSES) and not win32_controls.is_password_edit(
                child
            ):
                text = (win32_controls.get_text(child) or "").strip()
                if text:
                    entry = f"champ: {text}"
                    if entry not in fields:
                        fields.append(entry)
    return sorted(fields)


def confirm_word(label: Any, hwnd: int = 0) -> str:
    """Mot à confirmer pour ce libellé : CONFIRM_PATTERNS, ou verbe générique (valider, OK…) dans une fenêtre qui
    parle de paiement ou de formatage d'après son titre (CONTEXT_CONFIRM) ; « » sinon."""
    word = irreversible_word(label)
    if word or not hwnd or not CONFIRM_PATTERNS:
        return word
    plain = _plain(label)
    for context, verbs, what in CONTEXT_CONFIRM:
        found = re.search(r"\b(" + verbs + r")\b", plain)
        if found and re.search(r"\b(" + context + r")\b", _window_title_plain(hwnd)):
            return f"{found.group(0)} (fenêtre de {what})"
    return ""


def require_confirmation(
    label: Any,
    confirm: bool,
    what: str = "action",
    role: str = "",
    hwnd: int = 0,
    accord: str = "",
    approved: set[str] | None = None,
) -> None:
    """Refuse une action critique :
    - Geste SORTANT (payer, envoyer, publier, transférer...) : exige confirm=true ET accord=<jeton>
      lié à l'action exacte (outil, geste, cible, contenu des champs éditables, contexte).
    - Destruction locale (supprimer définitivement, désinstaller, formater, réinitialiser...) :
      confirm=true seul suffit.
    NEXUS_AGY_CONFIRM=off désactive toute confirmation."""
    if str(role or "") in NON_ACTION_ROLES or not confirmation_enabled():
        return
    outward = outward_word(label, hwnd)
    if outward:
        content_lines = field_contents(hwnd)
        title = _window_title_raw(hwnd) or _window_title_plain(hwnd)
        proc = _window_process_name(hwnd)
        context_str = f"{proc} — {title}" if proc and title else (proc or title)
        act_desc = garde_fous.action(
            "windows",
            what,
            str(label).strip(),
            content="\n".join(content_lines),
            context=context_str,
        )
        fp = garde_fous.fingerprint(act_desc)
        if approved is not None and fp in approved:
            return
        acc = get_accords()
        answer = acc.check(act_desc, confirm, accord)
        if not answer:
            if approved is not None:
                approved.add(fp)
            return
        raise ConfirmationRequiredError(
            f"{what} sur « {str(label).strip()[:60]} » : action sortante (« {outward} »).\n"
            f"Julien doit valider cette action exacte :\n{answer}"
        )
    if not confirm:
        word = confirm_word(label, hwnd)
        if word:
            raise ConfirmationRequiredError(
                f"{what} sur « {str(label).strip()[:60]} » : irréversible ou chez un tiers (« {word} »), rien "
                "n'a été fait. Julien l'a demandé explicitement : renvoyer cette étape avec confirm=true ; sinon (ton "
                "initiative), lui demander d'abord son oui."
            )


# Touches qui déclenchent une action : la confirmation porte sur CE QU'ELLES DÉCLENCHERAIENT, sinon Entrée
# contournerait le refus du clic sur « Envoyer ». Entrée : bouton au focus, bouton par défaut de la fenêtre, bouton
# d'action voisin du champ (envoi d'une messagerie, formulaire web). Ctrl+Entrée (raccourci d'envoi d'Outlook, Teams…) :
# tout bouton d'action de la fenêtre. Espace : bouton au focus. Alt+lettre : bouton ou menu de ce raccourci clavier
# (« &Envoyer » → Alt+E). Maj+Entrée (saut de ligne d'une messagerie) et Alt+Entrée ne déclenchent rien.
MODIFIER_NAMES = {"ctrl", "control", "alt", "shift", "win", "windows", "cmd"}
SUBMIT_KEYS = {"enter", "return"}
TRIGGER_ROLES = garde_fous.trigger_roles()
NEIGHBOR_LEVELS = 3  # ancêtres du champ remontés pour trouver son bouton d'envoi (composeur, formulaire)
NEIGHBOR_ROLES = ("Button", "SplitButton")  # ce qu'Entrée déclenche depuis un champ : un bouton, pas un lien
COMMAND_WORDS = 5  # libellé d'un bouton d'envoi : une commande courte (« Envoyer », « Publier le post »)
STATE_SYSTEM_DEFAULT = 0x100
UIA_LEGACY_STATE = 30096  # UIA_LegacyIAccessibleStatePropertyId
MAX_DEFAULT_PROBES = 60


def _key_kind(keys: str) -> str:
    """Ce qu'une combinaison peut déclencher : « submit » (Entrée), « send » (Ctrl+Entrée), « press » (Espace),
    « alt+x » (raccourci d'un bouton ou d'un menu), « » sinon."""
    parts = [p for p in (k.strip().lower() for k in str(keys or "").split("+")) if p]
    mods = {"ctrl" if p == "control" else p for p in parts if p in MODIFIER_NAMES}
    main = [p for p in parts if p not in MODIFIER_NAMES]
    if len(main) != 1:
        return ""
    key = main[0]
    if key in SUBMIT_KEYS and not mods & {"shift", "alt", "win", "windows"}:
        return "send" if "ctrl" in mods else "submit"
    if key in ("space", "spacebar") and not mods:
        return "press"
    if mods == {"alt"} and len(key) == 1 and key.isalnum():
        return f"alt+{key}"
    return ""


def _field_node(nodes: list[Any], info: dict[str, Any]) -> int:
    """Rang du champ dans l'arbre lu : même identifiant d'exécution, sinon même fenêtre native ; -1 sinon."""
    props = info.get("props") or {}
    rid = props.get("runtime_id")
    own = int(info.get("hwnd") or 0)
    for i, node in enumerate(nodes):
        if (rid and node.props.get("runtime_id") == rid) or (own and int(node.props.get("hwnd") or 0) == own):
            return i
    return -1


def _live_trigger(node: Any) -> bool:
    return node.control_type in TRIGGER_ROLES and node.props.get("enabled") is not False


def command_label(label: Any) -> bool:
    """Libellé d'une commande, pas d'une question ni d'une phrase : un bouton d'aide voisin (« Pourquoi ne puis-je pas
    envoyer cet élément ? », relevé par NexusWindows pour Claude le 25/10 sur le Chrome Web Store) n'est pas ce
    qu'Entrée déclenche dans un champ."""
    text = " ".join(str(label or "").split())
    return bool(text) and "?" not in text and len(text.split()) <= COMMAND_WORDS


def _neighbors(nodes: list[Any], index: int) -> list[Any]:
    """Éléments d'action du groupe du champ : sous-arbre de son ancêtre au plus NEIGHBOR_LEVELS au-dessus, jamais la
    racine (toute la fenêtre)."""
    ancestor = index
    for _ in range(NEIGHBOR_LEVELS):
        if ancestor < 0 or nodes[ancestor].parent < 1:
            break
        ancestor = nodes[ancestor].parent
    if ancestor < 0 or ancestor == index:
        return []
    inside, out = {ancestor}, []
    for i in range(ancestor + 1, len(nodes)):  # ordre du document : descendants contigus
        if nodes[i].parent not in inside:
            break
        inside.add(i)
        if _live_trigger(nodes[i]) and nodes[i].control_type in NEIGHBOR_ROLES and command_label(nodes[i].name):
            out.append(nodes[i])
    return out


def _key_triggers(target_hwnd: int, field: Any, kind: str) -> list[tuple[str, str]]:
    """(libellé, d'où) de ce que la touche (`kind` de _key_kind) déclencherait dans la fenêtre. Lecture seule."""
    out: list[tuple[str, str]] = []
    if field is None:
        designated = _designated_field(target_hwnd)
        if designated is not None:
            field = (designated["ctrl"], designated["info"])
    info = field[1] if field is not None else {}
    activates = kind in ("submit", "send", "press")
    if activates and info and str(info.get("type") or "") not in NON_ACTION_ROLES:
        out.append((str(info.get("name") or ""), "élément visé"))
    native = win32_controls.family(target_hwnd) in win32_controls.NATIVE_FAMILIES
    if native and activates:
        focus = win32_controls.focused_push_button(target_hwnd)
        if focus:
            out.append((win32_controls.get_text(focus) or "", "bouton qui a le focus"))
        default = win32_controls.default_button(target_hwnd) if kind != "press" else 0
        if default:
            out.append((win32_controls.get_text(default) or "", "bouton par défaut de la fenêtre"))
    if uia_fast is None:
        return out
    try:
        nodes = _window_tree(target_hwnd, max_nodes=MAX_UIA_NODES, time_budget=1.5).nodes
    except Exception:  # noqa: BLE001 - arbre illisible : seules les sources Win32 comptent
        return out
    if kind.startswith("alt+"):
        for node in nodes:
            if _live_trigger(node) and _plain(node.props.get("access_key")) == _plain(kind):
                out.append((node.name, f"raccourci {node.props.get('access_key')}"))
        return out
    for node in nodes:
        if node.props.get("focus") and _live_trigger(node):
            out.append((node.name, "élément qui a le focus"))
    if kind == "press":
        return out
    if kind == "send":
        out += [(node.name, "bouton d'action de la fenêtre") for node in nodes if _live_trigger(node)]
        return out
    probes = 0
    for node in nodes:  # bouton par défaut exposé par UIA (WPF, XAML, MSAA)
        if node.control_type not in ("Button", "SplitButton") or probes >= MAX_DEFAULT_PROBES:
            continue
        if not confirm_word(node.name, target_hwnd):
            continue  # seul un libellé à confirmer compte : pas de lecture inutile
        probes += 1
        try:
            state = int(node.element.GetCurrentPropertyValue(UIA_LEGACY_STATE) or 0)
        except Exception:  # noqa: BLE001
            continue
        if state & STATE_SYSTEM_DEFAULT:
            out.append((node.name, "bouton par défaut de la fenêtre"))
    if not info and native:
        own = win32_controls.keyboard_target(target_hwnd)
        info = {"hwnd": own} if own != target_hwnd else {}
    if not info:
        index = next((i for i, node in enumerate(nodes) if node.props.get("focus")), -1)
    else:
        index = _field_node(nodes, info)
    out += [(node.name, "bouton d'action voisin du champ") for node in _neighbors(nodes, index)]
    return out


def require_key_confirmation(
    target_hwnd: int,
    keys: str,
    confirm: bool,
    field: Any = None,
    accord: str = "",
    approved: set[str] | None = None,
    gesture: str = "",
) -> None:
    """Refuse une touche qui déclencherait une action critique (bouton au focus, bouton par défaut,
    bouton d'envoi voisin du champ, raccourci Alt d'un bouton).
    - Geste sortant : confirm=true ET accord=<jeton> lié à l'action exacte.
    - Destruction locale : confirm=true seul.
    NEXUS_AGY_CONFIRM=off : jamais."""
    kind = _key_kind(keys)
    if not kind or not CONFIRM_PATTERNS or not confirmation_enabled():
        return
    gesture = gesture or f"touche « {keys} »"
    for label, source in _key_triggers(target_hwnd, field, kind):
        outward = outward_word(label, target_hwnd)
        if outward:
            content_lines = field_contents(target_hwnd)
            title = _window_title_raw(target_hwnd) or _window_title_plain(target_hwnd)
            proc = _window_process_name(target_hwnd)
            context_str = f"{proc} — {title}" if proc and title else (proc or title)
            act_desc = garde_fous.action(
                "windows",
                gesture,
                f"{str(label).strip()} ({source})",
                content="\n".join(content_lines),
                context=context_str,
            )
            fp = garde_fous.fingerprint(act_desc)
            if approved is not None and fp in approved:
                continue
            acc = get_accords()
            answer = acc.check(act_desc, confirm, accord)
            if not answer:
                if approved is not None:
                    approved.add(fp)
                continue
            raise ConfirmationRequiredError(
                f"{gesture} : déclencherait « {label.strip()[:60]} » ({source}), action sortante (« {outward} »).\n"
                f"Julien doit valider cette action exacte :\n{answer}"
            )
        if not confirm:
            word = confirm_word(label, target_hwnd)
            if word:
                raise ConfirmationRequiredError(
                    f"{gesture} : déclencherait « {label.strip()[:60]} » ({source}), irréversible ou chez un "
                    f"tiers (« {word} ») ; rien n'a été fait. Julien l'a demandé explicitement : renvoyer cette étape avec "
                    "confirm=true ; sinon (ton initiative), lui demander d'abord son oui."
                )


# -----------------------------------------------------------------------------
# Champs mot de passe : remplis comme les autres ; valeur masquée, jamais relue ni rendue
# -----------------------------------------------------------------------------
PASSWORD_NAME_RE = re.compile(r"\b(mot de passe|password|passwort|passcode|contrasena|code pin|pin|mdp)\b")
PASSWORD_NOTE = "champ mot de passe : contenu remplacé, valeur masquée jamais relue (vérifier sur l'image)"


def is_password_field(info: dict[str, Any] | None) -> bool:
    """Champ mot de passe : UIA IsPassword, style ES_PASSWORD d'un Edit Win32, classe PasswordBox (WPF/WinUI), ou
    champ de saisie nommé « mot de passe », « password », « code PIN ». Sa valeur n'est jamais relue ni rendue."""
    info = info or {}
    props = info.get("props") or {}
    if props.get("password") or info.get("password"):
        return True
    own = int(info.get("hwnd") or 0)
    if own and win32_controls.is_password_edit(own):
        return True
    cls = str(info.get("class_name") or props.get("class_name") or "")
    if "passwordbox" in cls.lower():
        return True
    if str(info.get("type") or "") in ("Edit", "Document", ""):
        label = f"{info.get('name') or ''} {info.get('automation_id') or props.get('automation_id') or ''}"
        return bool(PASSWORD_NAME_RE.search(_plain(label)))
    return False


# In-memory element cache with window-affinity validation
_element_cache: dict[int, Any] = {}
_element_info: dict[int, dict[str, Any]] = {}  # propriétés lues dans le cache UIA (type, nom, hwnd, famille…)
_cached_window_hwnd: int = 0
_cached_window_title: str = ""


def _wrap_element(element: Any, info: dict[str, Any]) -> Any:
    """Pointeur IUIAutomationElement brut (lecture en cache) → uiautomation.Control, sans aller-retour de plus : le
    type de contrôle vient du cache. L'élément garde le réglage AutoSetFocus=False du client qui l'a lu."""
    if uia is None or hasattr(element, "GetInvokePattern") or not hasattr(element, "GetCachedPropertyValue"):
        return element
    try:
        constructors = uia.uiautomation.ControlConstructors
        type_id = int(info.get("type_id") or 0)
        if type_id in constructors:
            return constructors[type_id](element=element)
        return uia.Control.CreateControlFromElement(element) or element
    except Exception:  # noqa: BLE001
        return element


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
    wrapped = _wrap_element(ctrl, _element_info.get(element_index, {}))
    if wrapped is not ctrl:
        _element_cache[element_index] = ctrl = wrapped
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


def _open_clipboard() -> bool:
    for attempt in range(10):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.005 * (attempt + 1))
    return False


def get_clipboard_text() -> str | None:
    """Texte Unicode du presse-papiers (None s'il n'y en a pas ou s'il est verrouillé)."""
    if not _open_clipboard():
        return None
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


# Presse-papiers de Julien : TOUS ses formats sont sauvés puis rendus à l'identique (image, fichiers copiés, texte
# riche), vide s'il était vide. Les formats qui sont des poignées GDI ou de métafichier ne se copient pas : s'ils ne
# sont pas recréés par Windows à partir d'un format copié (CF_BITMAP depuis CF_DIB), la sauvegarde est incomplète et
# le collage n'est pas utilisé (frappe à la place). Le texte posé par NexusAGY porte les formats qui l'excluent de
# l'historique Win+V, du presse-papiers cloud et des gestionnaires de presse-papiers.
CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, CF_DIB, CF_ENHMETAFILE, CF_DIBV5 = 2, 3, 9, 8, 14, 17
CLIPBOARD_HANDLE_FORMATS = {CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, CF_ENHMETAFILE, 0x80, 0x82, 0x83, 0x8E}
CLIPBOARD_REBUILT_FROM_DIB = {CF_BITMAP, CF_PALETTE}
CLIPBOARD_MAX_BYTES = 64 * 1024 * 1024
CLIPBOARD_PRIVACY_FORMATS = (
    ("ExcludeClipboardContentFromMonitorProcessing", b"\x00\x00\x00\x00"),
    ("CanIncludeInClipboardHistory", b"\x00\x00\x00\x00"),
    ("CanUploadToCloudClipboard", b"\x00\x00\x00\x00"),
)


class ClipboardSnapshot:
    """Contenu complet du presse-papiers à un instant : (format, octets) ; `complete` faux si un format n'a pas pu
    être copié (raison dans `reason`)."""

    def __init__(self, formats: list[tuple[int, bytes]], complete: bool = True, reason: str = "") -> None:
        self.formats = formats
        self.complete = complete
        self.reason = reason

    @property
    def empty(self) -> bool:
        return not self.formats and self.complete


def _privacy_formats() -> list[tuple[int, bytes]]:
    out = []
    for name, data in CLIPBOARD_PRIVACY_FORMATS:
        fmt = int(user32.RegisterClipboardFormatW(name) or 0)
        if fmt:
            out.append((fmt, data))
    return out


def clipboard_snapshot() -> ClipboardSnapshot:
    """Sauvegarde de tous les formats du presse-papiers (copie des données, poignées GDI exceptées)."""
    if not _open_clipboard():
        return ClipboardSnapshot([], complete=False, reason="presse-papiers verrouillé par une autre application")
    formats: list[tuple[int, bytes]] = []
    skipped: list[int] = []
    total = 0
    try:
        fmt = int(user32.EnumClipboardFormats(0) or 0)
        while fmt:
            if fmt in CLIPBOARD_HANDLE_FORMATS or 0x200 <= fmt <= 0x3FF:
                skipped.append(fmt)
            else:
                handle = user32.GetClipboardData(fmt)
                size = int(kernel32.GlobalSize(handle) or 0) if handle else 0
                ptr = kernel32.GlobalLock(handle) if size else None
                if ptr:
                    try:
                        formats.append((fmt, ctypes.string_at(ptr, size)))
                        total += size
                    finally:
                        kernel32.GlobalUnlock(handle)
                elif handle:
                    skipped.append(fmt)
            if total > CLIPBOARD_MAX_BYTES:
                return ClipboardSnapshot([], complete=False, reason="presse-papiers trop lourd pour être sauvé")
            fmt = int(user32.EnumClipboardFormats(fmt) or 0)
    finally:
        user32.CloseClipboard()
    kept = {fmt for fmt, _ in formats}
    lost = [f for f in skipped if not (f in CLIPBOARD_REBUILT_FROM_DIB and kept & {CF_DIB, CF_DIBV5})]
    if lost:
        return ClipboardSnapshot(formats, complete=False, reason=f"formats non copiables {lost}")
    return ClipboardSnapshot(formats)


def _put_formats(formats: list[tuple[int, bytes]]) -> bool:
    """Vide le presse-papiers puis y pose les formats donnés (presse-papiers ouvert par l'appelant)."""
    user32.EmptyClipboard()
    ok = True
    for fmt, data in formats:
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(1, len(data)))
        ptr = kernel32.GlobalLock(h_mem) if h_mem else None
        if not ptr:
            if h_mem:
                kernel32.GlobalFree(h_mem)
            ok = False
            continue
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h_mem)
        if not user32.SetClipboardData(fmt, h_mem):
            kernel32.GlobalFree(h_mem)
            ok = False
    return ok


def clipboard_restore(snapshot: ClipboardSnapshot) -> bool:
    """Rend le presse-papiers sauvé, à l'identique (vide s'il était vide), sans entrée de plus dans l'historique."""
    if not _open_clipboard():
        return False
    try:
        if not snapshot.formats:
            return bool(user32.EmptyClipboard())
        present = {fmt for fmt, _ in snapshot.formats}
        extra = [(fmt, data) for fmt, data in _privacy_formats() if fmt not in present]
        return _put_formats(list(snapshot.formats) + extra)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> bool:
    """Pose du texte (hors historique Win+V et presse-papiers cloud), relu ensuite."""
    data = text.encode("utf-16-le") + b"\x00\x00"
    if not _open_clipboard():
        return False
    try:
        if not _put_formats([(CF_UNICODETEXT, data), *_privacy_formats()]):
            return False
    finally:
        user32.CloseClipboard()
    return get_clipboard_text() == text


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
    Restores the original active window and cursor position after the action by default,
    acquires a cooperative multi-agent foreground lock, and pauses for a natural typing idle threshold."""

    def __init__(
        self,
        target_hwnd: int | None = None,
        restore: bool = True,
        wait_idle: bool = True,
        use_lock: bool = True,
        purpose: str = "action physique",
    ):
        self.target_hwnd = target_hwnd
        self.restore = restore
        self.wait_idle = wait_idle
        self.use_lock = use_lock
        self.purpose = purpose
        self.fg_lock = None
        self.orig_fg = 0
        self.orig_pt = POINT(0, 0)

    def __enter__(self):
        emergency_stop.check()  # arrêt d'urgence de Julien : aucune entrée physique
        if self.use_lock:
            self.fg_lock = _take_foreground_token(self.purpose)  # protocole commun : jamais d'action sans le jeton

        curr_fg = user32.GetForegroundWindow()
        if self.wait_idle and (not self.target_hwnd or curr_fg != self.target_hwnd):
            if not wait_for_user_idle(threshold_s=1.5, max_wait_s=5.0):
                if self.fg_lock:
                    self.fg_lock.release()
                    self.fg_lock = None
                raise TimeoutError(
                    "Julien est en train de taper au clavier ou d'utiliser la souris : "
                    "action reportée pour ne pas interrompre son travail"
                )
        try:
            emergency_stop.check()  # l'attente de pause a pu durer : relire l'arrêt avant d'agir
        except emergency_stop.EmergencyStopError:
            if self.fg_lock:
                self.fg_lock.release()
                self.fg_lock = None
            raise
        self.orig_fg = user32.GetForegroundWindow()
        user32.GetCursorPos(ctypes.byref(self.orig_pt))
        # Repère des gestes de Julien : toute entrée physique après ce point interrompt l'action (_checkpoint).
        stack = getattr(_guard_tokens, "stack", None)
        if stack is None:
            stack = _guard_tokens.stack = []
        stack.append(stack[0] if stack else physical_input.mark())  # garde imbriquée : repère de la plus ancienne
        self._token_pushed = True
        try:
            if self.target_hwnd:
                if self.orig_fg != self.target_hwnd:
                    focus_window(hwnd=self.target_hwnd)
                # Mise au premier plan RELUE : Windows peut la refuser sans erreur ; rien ne part alors.
                if not _wait_front(self.target_hwnd):
                    front = int(user32.GetForegroundWindow() or 0)
                    raise ForegroundLostError(
                        f"La fenêtre visée ({self.target_hwnd}) n'est pas passée au premier plan (fenêtre {front} "
                        "devant) : aucune vraie souris ni vrai clavier envoyé."
                    )
                targets = getattr(_front_local, "stack", None)
                if targets is None:
                    targets = _front_local.stack = []
                targets.append(int(self.target_hwnd))
                self._target_pushed = True
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        interrupted = exc_type is not None and issubclass(exc_type, UserInterruptError)
        try:
            if getattr(self, "_target_pushed", False):
                self._target_pushed = False
                targets = getattr(_front_local, "stack", None)
                if targets:
                    targets.pop()
            if self.restore and not interrupted:
                # Curseur toujours rendu (même quand la cible était déjà devant) ; jamais pendant que Julien s'en sert.
                user32.SetCursorPos(self.orig_pt.x, self.orig_pt.y)
            if self.restore and self.orig_fg and self.orig_fg != self.target_hwnd and user32.IsWindow(self.orig_fg):
                restore_foreground(self.orig_fg)
            elif interrupted and self.orig_fg and user32.IsWindow(self.orig_fg):
                restore_foreground(self.orig_fg)  # interruption : la main est rendue même sans restore_focus
        finally:
            if getattr(self, "_token_pushed", False):
                self._token_pushed = False
                stack = getattr(_guard_tokens, "stack", None)
                if stack:
                    stack.pop()
            if self.fg_lock:
                self.fg_lock.release()
                self.fg_lock = None


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


user32.FindWindowExW.argtypes = [HWND, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = HWND


def uwp_core_window(hwnd: int) -> int:
    """CoreWindow de l'application UWP hébergée par un cadre ApplicationFrameWindow (0 sinon). Le cadre appartient à
    ApplicationFrameHost.exe ; l'application (calculatorapp.exe…) est le processus de sa CoreWindow."""
    if not hwnd:
        return 0
    buf = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, buf, 64)
    if buf.value != "ApplicationFrameWindow":
        return 0
    return int(user32.FindWindowExW(hwnd, None, "Windows.UI.Core.CoreWindow", None) or 0)


def app_pid(hwnd: int) -> int:
    """Processus de l'APPLICATION d'une fenêtre : celui de sa CoreWindow pour une application UWP, sinon le sien."""
    core = uwp_core_window(hwnd)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(core or hwnd, ctypes.byref(pid))
    return pid.value


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
GW_OWNER = 4


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

        pid = wintypes.DWORD(app_pid(hwnd))
        full_path, proc_name = get_process_image_path(pid.value)

        # Ignore known internal background tool windows
        if visible_only and proc_name.lower() in {"explorer.exe"} and not title:
            return True

        entry = {
            "hwnd": hwnd,
            "title": title,
            "process_id": pid.value,
            "process_name": proc_name,
            "process_path": full_path,
            "bounds": rect,
            "is_foreground": (hwnd == fg_hwnd),
        }
        # Boîte possédée (« Ouvrir » de Chrome, #32770 sans WS_EX_APPWINDOW) : listée avec sa fenêtre propriétaire.
        owner = int(user32.GetWindow(hwnd, GW_OWNER) or 0)
        if owner:
            entry["dialog_of"] = owner
        windows.append(entry)
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


WINDOW_UNNAMED = (
    "Fenêtre non précisée : indiquer hwnd (numéro de windows, titre ou processus). La fenêtre de devant "
    "n'est jamais prise par défaut (c'est souvent Antigravity elle-même ou la fenêtre de travail de Julien)."
)


def _window_line(w: dict[str, Any]) -> str:
    owner = f" [boîte de {w['dialog_of']}]" if w.get("dialog_of") else ""
    return f"[{w['hwnd']}] « {str(w.get('title') or '')[:50]} » ({w.get('process_name') or '?'}){owner}"


def _pick_window(windows: list[dict[str, Any]], query: str, keys: tuple[str, ...]) -> int:
    """Fenêtre unique qui correspond : exacte d'abord, sinon partielle ; plusieurs → refus avec les candidates."""
    q = " ".join(query.split()).casefold()
    if not q:
        raise ValueError(WINDOW_UNNAMED)

    def values(w: dict[str, Any]) -> list[str]:
        out = [" ".join(str(w.get(k) or "").split()).casefold() for k in keys]
        if "process_name" in keys:
            out.append(out[keys.index("process_name")].removesuffix(".exe"))
        return out

    exact = [w for w in windows if q in values(w)]
    chosen = exact or [w for w in windows if any(q in v for v in values(w))]
    if len(chosen) > 1 and "process_name" in keys:
        # Nom de processus exact : la fenêtre principale passe avant les boîtes qu'elle possède (visées par leur titre).
        process = str(chosen[0].get("process_name") or "").casefold()
        same_process = all(str(w.get("process_name") or "").casefold() == process for w in chosen)
        main = [w for w in chosen if not w.get("dialog_of")]
        if same_process and q in (process, process.removesuffix(".exe")) and len(main) == 1:
            return int(main[0]["hwnd"])
    if len(chosen) == 1:
        return int(chosen[0]["hwnd"])
    if chosen:
        listed = " ; ".join(_window_line(w) for w in chosen[:8])
        raise ValueError(
            f"« {query} » désigne {len(chosen)} fenêtres ({'exactes' if exact else 'partielles'}) : {listed}. "
            "Préciser hwnd par son numéro."
        )
    raise ValueError(f"Aucune fenêtre ouverte ne correspond à '{query}'.")


def resolve_window(target: int | str | None = None) -> int:
    """Fenêtre visée : numéro (hwnd), ou titre / nom de processus qui n'en désigne qu'une. Sans cible : refus (jamais
    la fenêtre de devant implicitement) ; cible ambiguë : refus avec la liste des candidates."""
    ensure_default_desktop()
    if isinstance(target, bool):
        raise ValueError(WINDOW_UNNAMED)
    if isinstance(target, int):
        return target
    if target is None or (isinstance(target, str) and not target.strip()):
        raise ValueError(WINDOW_UNNAMED)
    if isinstance(target, str):
        target_str = target.strip()
        if target_str.isdigit():
            return int(target_str)
        return _pick_window(list_windows(visible_only=True), target_str, ("title", "process_name"))
    raise ValueError(WINDOW_UNNAMED)


def focus_window(
    hwnd: int | str | None = None,
    title: str | None = None,
    process_name: str | None = None,
) -> dict[str, Any]:
    """Brings the target application window to the foreground and restores if minimized.

    Mise au premier plan voulue = jeton commun (NexusWindows/commun/foreground-token.md) : déjà tenu quand une garde l'appelle
    (réentrant), sinon pris ici ; tenu par un autre agent → rien n'est fait, le détenteur est nommé. Fenêtre
    toujours désignée sans ambiguïté (jamais celle de devant par défaut)."""
    emergency_stop.check()
    ensure_default_desktop()
    if hwnd is not None:
        target_hwnd = resolve_window(hwnd)
    elif title:
        target_hwnd = _pick_window(list_windows(visible_only=True), title, ("title",))
    elif process_name:
        target_hwnd = _pick_window(list_windows(visible_only=True), process_name, ("process_name",))
    else:
        raise ValueError(WINDOW_UNNAMED)

    if not target_hwnd:
        raise ValueError("Fenêtre introuvable avec les critères spécifiés.")

    token = _take_foreground_token("mise au premier plan (computer_focus_window)")
    try:
        _activate_window(target_hwnd)
    finally:
        token.release()

    success = _wait_front(target_hwnd)  # relu : SetForegroundWindow peut répondre oui sans effet
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


def _take_foreground_token(purpose: str):
    """Prend le jeton commun souris/premier plan pour NexusAGY (réentrant) ; refuse si un autre agent le tient au-delà
    de l'attente ou s'il est inaccessible : jamais de mise au premier plan sans lui."""
    try:
        shared_dir = Path(__file__).resolve().parent.parent.parent / "commun"
        if shared_dir.exists() and str(shared_dir) not in sys.path:
            sys.path.insert(0, str(shared_dir))
        from foreground_lock import ForegroundLock, holder

        token = ForegroundLock(owner="NexusAGY", purpose=purpose, abort=emergency_stop.check)
        held = token.acquire()
    except Exception as error:  # noqa: BLE001
        raise RuntimeError(
            f"Jeton commun souris/premier plan inaccessible ({error}) : action physique refusée, rien n'a été fait"
        ) from error
    if not held:
        who = holder() or {}
        raise TimeoutError(
            f"{who.get('owner') or 'un autre agent'} tient la souris et le premier plan "
            f"({who.get('purpose') or 'action physique'}) : action reportée, rien n'a été fait"
        )
    return token


def _activate_window(target_hwnd: int) -> bool:
    """Restaure et active la fenêtre (droits d'activation hérités du fil au premier plan). Appelant : jeton tenu."""
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
        return bool(user32.SetForegroundWindow(target_hwnd))
    finally:
        try:
            if attached_fg and fg_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, False)
            if attached_target and target_tid:
                user32.AttachThreadInput(cur_tid, target_tid, False)
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Screen & Window Capture (Anti-Crash 400 Guaranteed < 200 KB)
# -----------------------------------------------------------------------------
SCREENSHOT_KEEP = 50  # captures gardées au plus (README : « at most 50 »)
SCREENSHOT_MAX_AGE_H = 24.0  # âge maximal d'une capture


def screenshot_dir() -> Path:
    """Dossier local (hors OneDrive) des captures écrites par défaut."""
    return Path.home() / ".nexusagy" / "screenshots"


def save_screenshot(data: bytes, prefix: str) -> Path:
    """Écrit une capture dans screenshot_dir() PUIS nettoie : jamais plus de SCREENSHOT_KEEP fichiers ensuite
    (nettoyer avant l'écriture en laissait SCREENSHOT_KEEP + 1, relecture de Codex du 23/10)."""
    cache_dir = screenshot_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{prefix}_{int(time.time() * 1000)}.webp"
    dest.write_bytes(data)
    cleanup_screenshot_cache(cache_dir=cache_dir)
    return dest.resolve()


def cleanup_screenshot_cache(
    max_files: int = SCREENSHOT_KEEP, max_age_hours: float = SCREENSHOT_MAX_AGE_H, cache_dir: Path | None = None
) -> int:
    """Prunes older screenshots (WebP du bureau, PNG du navigateur) from ~/.nexusagy/screenshots to prevent disk bloat.
    Appelé après chaque capture écrite et au démarrage du serveur."""
    cache_dir = cache_dir or screenshot_dir()
    if not cache_dir.exists():
        return 0
    try:
        files = sorted(
            [*cache_dir.glob("*.webp"), *cache_dir.glob("*.png")],
            key=lambda p: (p.stat().st_mtime, p.name),
        )
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


def close_window(hwnd: int | str) -> dict[str, Any]:
    """Closes target window gracefully using UI Automation WindowPattern.Close() with WM_CLOSE fallback.

    Ensures clean termination across standard Win32, WPF, and UWP/WinUI applications (Calculator, Settings, etc.).
    Verifies postcondition to eliminate false success.
    """
    emergency_stop.check()
    ensure_default_desktop()
    target_hwnd = resolve_window(hwnd)
    if not target_hwnd or not user32.IsWindow(target_hwnd):
        raise ValueError(f"HWND {hwnd} invalide ou fenêtre déjà fermée.")

    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Fermeture interdite sur {reason}.")

    # 1. Background-first: Try UIA WindowPattern (essential for modern UWP/Store apps that ignore WM_CLOSE).
    # Motif absent (attesté AVANT l'appel) : WM_CLOSE. Close() lancé puis réponse COM perdue : rien n'est rejoué, la
    # fermeture est seulement relue (relecture de Codex : deux demandes de fermeture sinon).
    visible_before = bool(user32.IsWindowVisible(target_hwnd))
    win_pat = None
    if uia is not None:
        try:
            ctrl = uia.ControlFromHandle(target_hwnd)
            win_pat = ctrl.GetPattern(uia.PatternId.WindowPattern) if ctrl else None
        except Exception:
            win_pat = None
    method_used = "uia_window_close" if win_pat else "wm_close"
    close_error = ""
    if win_pat:
        try:
            win_pat.Close()
        except Exception as error:  # noqa: BLE001 - issue incertaine : relue, jamais rejouée
            close_error = f"{type(error).__name__}: {error}"
    else:
        wm_close = 0x0010
        user32.PostMessageW(target_hwnd, wm_close, 0, 0)

    # 2. Strict postcondition verification : fenêtre détruite, ou visible avant et masquée après. Une fenêtre déjà
    # masquée avant la demande ne prouve rien en restant masquée (relecture de Codex).
    deadline = time.monotonic() + 2.0  # UWP : la fermeture du cadre peut prendre plus d'une demi-seconde
    while time.monotonic() < deadline:
        gone = not user32.IsWindow(target_hwnd)
        if gone or (visible_before and not user32.IsWindowVisible(target_hwnd)):
            result = {"success": True, "verified": True, "closed": True, "hwnd": target_hwnd, "method": method_used}
            if not gone:
                result["hidden"] = True  # cadre UWP masqué par Windows plutôt que détruit
            return result
        time.sleep(0.04)

    if not visible_before or close_error:
        return {
            "success": None,
            "closed": None,
            "hwnd": target_hwnd,
            "method": method_used,
            "message": (
                "~ fermeture non relue : "
                + ("fenêtre déjà masquée avant la demande" if not visible_before else f"réponse perdue ({close_error})")
                + " ; regarder avant de recommencer."
            ),
        }
    return {
        "success": False,
        "closed": False,
        "hwnd": target_hwnd,
        "method": method_used,
        "message": "La fenêtre ne s'est pas fermée (boîte modale d'enregistrement en attente ou fermeture annulée).",
    }


OPEN_WAIT_S = 6.0
ASSOCF_INIT_IGNOREUNKNOWN = 0x400  # type inconnu : erreur plutôt que « Ouvrir avec » (OpenWith.exe)
ASSOCSTR_EXECUTABLE = 2


def _assoc_executable(path: str) -> str:
    """Exécutable (nom en minuscules, « notepad.exe ») de l'application associée au document ou au dossier
    (AssocQueryStringW, comme ShellExecute) ; « » si aucune n'est connue (association d'application du Store
    sans exécutable, type inconnu)."""
    target = Path(path)
    assoc = "Folder" if target.is_dir() else target.suffix
    if not assoc:
        return ""
    try:
        query = ctypes.windll.shlwapi.AssocQueryStringW
        query.argtypes = (
            ctypes.c_uint, ctypes.c_uint, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )  # fmt: skip
        query.restype = ctypes.c_long
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if query(ASSOCF_INIT_IGNOREUNKNOWN, ASSOCSTR_EXECUTABLE, assoc, None, buf, ctypes.byref(size)) != 0:
            return ""
    except (OSError, AttributeError):
        return ""
    name = os.path.basename(buf.value).lower()
    return "" if name == "openwith.exe" else name


def _title_names_file(title: Any, file_name: str) -> bool:
    """Le titre porte le nom du fichier : nom entier ou sans extension, ou début du nom tronqué par « … » / « ... »
    (au moins 6 caractères, ou le nom entier s'il est plus court)."""
    plain_title = _plain(title)
    if any(n and n in plain_title for n in {_plain(file_name), _plain(Path(file_name).stem)}):
        return True
    raw = str(title or "").casefold()
    wanted = file_name.casefold()
    for mark in re.finditer(r"…|\.\.\.", raw):
        before = raw[: mark.start()]
        for start in range(len(before)):
            piece = before[start:].lstrip()
            if piece and len(piece) >= min(6, len(wanted)) and wanted.startswith(piece):
                return True
    return False


# Application Chromium/Electron lancée recouverte (recette commune, NexusWindows/commun/benchmarks/windows/RECETTES.md, 24/10) : sans ces
# commutateurs, Chromium ne dessine ni ne publie à l'accessibilité une fenêtre recouverte dès son démarrage (Logi
# Options+ resté sur son écran de démarrage violet derrière Claude agrandi ; banc « lancement recouvert » : bouton
# introuvable, 0/3). Chromium ne retient que le DERNIER --disable-features : un seul, fusionné.
CHROMIUM_OCCLUSION_FEATURE = "CalculateNativeWinOcclusion"
CHROMIUM_A11Y_SWITCH = "--force-renderer-accessibility"
STARTF_USESHOWWINDOW, SW_SHOWNOACTIVATE = 0x1, 4
OPEN_GIVE_BACK_S = 1.0  # l'application peut s'activer après l'apparition de sa fenêtre (affichage différé)


def is_chromium_app(exe: str) -> bool:
    """Chromium ou Electron, reconnu à ses ressources à côté de l'exécutable (jamais à son nom)."""
    folder = Path(exe).parent
    return Path(exe).suffix.lower() == ".exe" and (
        (folder / "resources" / "app.asar").exists()
        or (folder / "resources" / "app").is_dir()
        or (folder / "chrome_100_percent.pak").exists()
    )


def _shortcut_target(path: str) -> tuple[str, str] | None:
    """Cible et arguments d'un raccourci .lnk (WScript.Shell) ; None s'il est illisible."""
    try:
        import comtypes.client

        link = comtypes.client.CreateObject("WScript.Shell", dynamic=True).CreateShortcut(path)
        return str(link.TargetPath or ""), str(link.Arguments or "")
    except Exception:  # noqa: BLE001 - raccourci illisible : ouvert tel quel par le shell
        return None


def chromium_launch_target(path: str) -> str:
    """Exécutable Chromium/Electron à lancer soi-même avec les commutateurs : le programme, ou la cible d'un raccourci
    SANS arguments propres (un profil, un port… ne sont jamais remplacés ni complétés). « » sinon."""
    if Path(path).suffix.lower() == ".lnk":
        found = _shortcut_target(path)
        if not found or found[1].strip():
            return ""
        path = found[0]
    return path if path and Path(path).is_file() and is_chromium_app(path) else ""


def _start_chromium(exe: str) -> None:
    """Démarre l'exécutable sans activation demandée, avec le suivi d'occlusion coupé et l'accessibilité forcée."""
    import subprocess

    info = subprocess.STARTUPINFO()
    info.dwFlags |= STARTF_USESHOWWINDOW
    info.wShowWindow = SW_SHOWNOACTIVATE
    subprocess.Popen(  # noqa: S603 - chemin vérifié par _path_problem, aucun argument venu du modèle
        [exe, f"--disable-features={CHROMIUM_OCCLUSION_FEATURE}", CHROMIUM_A11Y_SWITCH],
        cwd=str(Path(exe).parent), startupinfo=info, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, close_fds=True,
    )  # fmt: skip


def _give_back_after_open(seen: dict[str, Any] | None, front_before: int) -> bool:
    """Premier plan rendu à Julien si l'application ouverte le prend, y compris un peu APRÈS l'apparition de sa
    fenêtre (Electron s'active à l'affichage). Le détenteur le rend lui-même (_hand_back, WM_SYSCOMMAND SC_HOTKEY) :
    SetForegroundWindow seul est refusé à un processus d'arrière-plan (banc du 24/10 : 460 ms, jamais rendu)."""
    if not seen or not front_before:
        return _restore_if_stolen(front_before)
    top = win32_controls.root_of(int(seen["hwnd"])) or int(seen["hwnd"])
    stolen = False
    deadline = time.monotonic() + OPEN_GIVE_BACK_S
    while time.monotonic() < deadline:
        fg = int(user32.GetForegroundWindow() or 0)
        if fg and fg != front_before and win32_controls.root_of(fg) == top and not _other_agent_holds_token():
            stolen = True
            if not _hand_back(top, front_before):
                restore_foreground(front_before)
        time.sleep(0.02)
    return _restore_if_stolen(front_before) or stolen


def _is_protocol(path: str) -> bool:
    """Protocole d'activation Windows (ms-settings:, shell:, calculator:…), pas une lettre de lecteur ni une URL web."""
    return bool(re.match(r"^[a-z][a-z0-9+.-]+:(?![\\/])", path, re.IGNORECASE)) and "://" not in path


def _resolve_program(path: str) -> str:
    """Nom nu de programme (« notepad.exe », « mspaint ») résolu comme le fait Démarrer > Exécuter : PATH (alias
    d'applications Store de WindowsApps compris), puis App Paths du registre. Rien trouvé, ou chemin déjà existant
    ou portant un dossier : inchangé (passe 2 du 22/10 : notepad.exe et mspaint.exe refusés, « introuvables »)."""
    if (
        not path
        or Path(path).exists()
        or os.sep in path
        or "/" in path
        or _is_protocol(path)
        or Path(path).suffix.lower() not in ("", ".exe")
    ):
        return path
    import shutil
    import winreg

    found = shutil.which(path)
    if found:
        return found
    name = path if path.lower().endswith(".exe") else f"{path}.exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}") as key:
                value = os.path.expandvars(str(winreg.QueryValue(key, None) or "").strip().strip('"'))
        except OSError:
            continue
        if value and Path(value).exists():
            return value
    return path


def _path_problem(path: str) -> str:
    """Raison de refuser l'ouverture (« » pour tout chemin existant : document, dossier, programme, script,
    raccourci). Une adresse web ou un protocole n'est pas un chemin : la page passe par nexus-browser."""
    if re.match(r"^(https?|ftp)://", path, re.IGNORECASE):
        return "adresse web (URL) : une page web passe par nexus-browser"
    if _is_protocol(path):  # ms-settings:, shell:, calculator:… : activation du shell Windows, ouverte telle quelle
        return ""
    if path.startswith("\\\\?\\") or path.startswith("\\\\.\\"):
        return "chemin de périphérique (\\\\?\\, \\\\.\\) : on ne sait pas ce qu'il ouvrirait"
    if not Path(path).exists():
        return "chemin introuvable"
    return ""


def open_path(path_or_url: str) -> dict[str, Any]:
    """Ouvre un chemin existant (document, dossier, programme, script, raccourci) comme un double-clic
    (ShellExecute). Refus : URL et protocoles (pages web : nexus-browser), chemins de périphérique, chemin introuvable.

    Ouverture relue : NOUVELLE fenêtre de l'application associée (AssocQueryString ; le programme lui-même pour un
    .exe) ou portant le nom du fichier ; sinon (Windows 11 à onglets : document ajouté comme onglet) fenêtre déjà ouverte de l'application
    associée dont le titre porte le nom, même tronqué. Rien de tel : « ouverture non vérifiée », sans fenêtre désignée
    (jamais une notification ou une bulle apparue entre-temps). Premier plan rendu à Julien si l'application le
    prend : la fenêtre ouverte reste en arrière-plan, une étape foreground=True la ramène elle-même devant."""
    emergency_stop.check()
    ensure_default_desktop()
    path_expanded = os.path.expandvars(os.path.expanduser(str(path_or_url or "").strip().strip('"')))
    path_expanded = _resolve_program(path_expanded)
    problem = _path_problem(path_expanded)
    if problem:
        raise PermissionError(f"Ouverture refusée de « {path_or_url} » : {problem}. Rien n'a été ouvert.")
    target = Path(path_expanded)
    chromium = chromium_launch_target(path_expanded)
    app = (
        Path(chromium).name.lower()
        if chromium
        else target.name.lower()
        if target.suffix.lower() == ".exe"
        else _assoc_executable(path_expanded)
    )
    before = {w["hwnd"] for w in list_windows(visible_only=True)}
    front_before = int(user32.GetForegroundWindow() or 0)
    if chromium:
        _start_chromium(chromium)
    else:
        os.startfile(path_expanded)
    seen: dict[str, Any] | None = None
    verified_by = ""
    deadline = time.monotonic() + OPEN_WAIT_S
    while seen is None and time.monotonic() < deadline:
        time.sleep(0.15)
        windows = list_windows(visible_only=True)
        for w in windows:  # 1. nouvelle fenêtre : de l'application associée, ou portant le nom du fichier
            of_app = bool(app) and str(w.get("process_name") or "").lower() == app
            if w["hwnd"] not in before and (of_app or _title_names_file(w.get("title"), target.name)):
                seen, verified_by = w, "nouvelle fenêtre de l'ouverture relue"
                break
        if seen is None and app:  # 2. onglet ajouté à une fenêtre déjà ouverte de l'application associée
            for w in windows:
                of_app = str(w.get("process_name") or "").lower() == app
                if w["hwnd"] in before and of_app and _title_names_file(w.get("title"), target.name):
                    seen, verified_by = w, "fenêtre de l'application associée portant le nom (onglet)"
                    break
    stolen = _give_back_after_open(seen, front_before)
    result: dict[str, Any] = {"success": True if seen else None, "verified": bool(seen) or None, "path": path_expanded}
    if app:
        result["application"] = app
    if chromium:
        result["chromium"] = "dessinée et lisible même recouverte (suivi d'occlusion coupé, accessibilité forcée)"
    if seen:
        result.update(hwnd=seen["hwnd"], title=seen["title"], verified_by=verified_by)
    else:
        result["message"] = (
            f"~ ouverture non vérifiée : aucune fenêtre de {app or 'l’application associée'} portant le nom relue en "
            f"{OPEN_WAIT_S:g} s ; aucune fenêtre désignée, vérifier (windows)."
        )
    if stolen:
        result["focus_stolen_restored"] = True
    return result


def _dwm_crop_box(window_rect: dict[str, int], frame_rect: dict[str, int]) -> tuple[int, int, int, int]:
    """Boîte de recadrage (gauche, haut, droite, bas), relative à l'image PrintWindow du rectangle Win32, qui ne
    garde que le cadre DWM visible (DWMWA_EXTENDED_FRAME_BOUNDS). Sans cadre DWM exploitable : image entière."""
    width = window_rect["right"] - window_rect["left"]
    height = window_rect["bottom"] - window_rect["top"]
    left = max(0, frame_rect["left"] - window_rect["left"])
    top = max(0, frame_rect["top"] - window_rect["top"])
    right = min(width, frame_rect["right"] - window_rect["left"])
    bottom = min(height, frame_rect["bottom"] - window_rect["top"])
    if right <= left or bottom <= top:
        return (0, 0, width, height)
    return (left, top, right, bottom)


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
    # PrintWindow rend le rectangle Win32 complet, bordures invisibles de redimensionnement comprises (~7 px) ;
    # on recadre sur le cadre DWM visible, le même repère que get_window_rect et les box_2d.
    crop_box = _dwm_crop_box(
        {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
        get_window_rect(hwnd),
    )

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
        img = Image.frombuffer("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1)
        if crop_box != (0, 0, w, h):
            img = img.crop(crop_box)

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


@overload
def capture_window_image(
    hwnd: int | str | None = ...,
    full_screen: bool = ...,
    max_dimension: int = ...,
    zoom: list[int] | None = ...,
    return_meta: Literal[False] = ...,
    elements_to_annotate: list[dict[str, Any]] | None = ...,
) -> bytes: ...
@overload
def capture_window_image(
    hwnd: int | str | None = ...,
    full_screen: bool = ...,
    max_dimension: int = ...,
    zoom: list[int] | None = ...,
    *,
    return_meta: Literal[True],
    elements_to_annotate: list[dict[str, Any]] | None = ...,
) -> tuple[bytes, dict[str, Any]]: ...


# Règle image commune des produits Nexus (NexusShared/images.md, 24/10) : côté long ≤ 1568 px et ≤ 1,15 Mpx (Gemini 3,
# Claude et GPT-5.x lisent cette taille sans la réduire), WebP sans perte jusqu'à 200 Ko, puis qualité 85, 70…
# jusqu'à tenir 500 Ko : au-delà, Antigravity échoue en 400 (crash vu avant le 24/10).
IMAGE_MAX_SIDE = 1568
IMAGE_MAX_PIXELS = 1_150_000
IMAGE_LOSSLESS_BUDGET = 200 * 1024
IMAGE_LIMIT = 500 * 1024
ZOOM_MAX_ENLARGE = 2.0  # zone zoomée agrandie au plus ×2 (lecture d'un petit texte), dans les mêmes plafonds


def encode_webp(img: Image.Image) -> bytes:
    """Image envoyée au modèle : WebP sans perte si ≤ 200 Ko, sinon qualité décroissante jusqu'à ≤ 500 Ko (à 0, un
    écran entier de bruit pèse moins de 100 Ko). Mêmes dimensions : l'échelle annoncée reste juste."""
    rgb = img.convert("RGB")

    def encode(**options: Any) -> bytes:
        buffer = io.BytesIO()
        rgb.save(buffer, format="WEBP", method=4, **options)
        return buffer.getvalue()

    data = encode(lossless=True)
    if len(data) <= IMAGE_LOSSLESS_BUDGET:
        return data
    for quality, budget in ((85, IMAGE_LOSSLESS_BUDGET), (70, IMAGE_LIMIT), (50, IMAGE_LIMIT), (30, IMAGE_LIMIT),
                            (10, IMAGE_LIMIT), (0, IMAGE_LIMIT)):  # fmt: skip
        data = encode(quality=quality)
        if len(data) <= budget:
            return data
    return data


def image_print(img: Image.Image) -> str:
    """Empreinte EXACTE d'une image (dimensions et pixels RGB) : même écran que la dernière image envoyée = pas de
    double. Pas l'empreinte grise 64×64 de NexusShared/images.md : un voyant rouge devenu vert y garde le même gris
    (relecture de Codex du 24/10) et disparaîtrait de la réponse."""
    rgb = img.convert("RGB")
    return hashlib.sha256(f"{rgb.width}x{rgb.height}:".encode() + rgb.tobytes()).hexdigest()


def _fit(img: Image.Image, max_dimension: int, enlarge: float = 1.0) -> Image.Image:
    """Taille envoyée : côté long ≤ max_dimension (1568 au plus) et ≤ 1,15 Mpx ; agrandie au plus de `enlarge`."""
    width, height = img.size
    side = min(max_dimension, IMAGE_MAX_SIDE)
    scale = min(enlarge, side / max(width, height), (IMAGE_MAX_PIXELS / (width * height)) ** 0.5)
    if abs(scale - 1.0) < 1e-6:
        return img
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return img.resize(size, Image.Resampling.LANCZOS)


def capture_window_image(
    hwnd: int | str | None = None,
    full_screen: bool = False,
    max_dimension: int = IMAGE_MAX_SIDE,
    zoom: list[int] | None = None,
    return_meta: bool = False,
    elements_to_annotate: list[dict[str, Any]] | None = None,
) -> bytes | tuple[bytes, dict[str, Any]]:
    """Captures the target window or full screen as WebP (common image rule: ≤ 1568 px, ≤ 1.15 Mpx, ≤ 500 KB).

    zoom: box_2d [ymin, xmin, ymax, xmax] (0-1000) of the window, captured at full resolution and enlarged up to ×2
    (no marks drawn: the window's box_2d stay those of the whole image).
    Supports multi-monitor desktop setups, negative coordinates, and visual Set-of-Marks overlay.
    """
    ensure_default_desktop()
    target_hwnd: int | None = None
    if not full_screen:
        target_hwnd = resolve_window(hwnd)
        ensure_readable(target_hwnd)
    else:
        ensure_screen_readable()

    img: Image.Image | None = None
    region: dict[str, Any] = {}

    # Background-first GDI offscreen capture (does not steal focus and captures covered windows)
    if not full_screen and target_hwnd and target_hwnd != user32.GetForegroundWindow():
        img = capture_window_background_gdi(target_hwnd)
        if img is not None:
            rect = get_window_rect(target_hwnd)
            region = {
                "left": rect["left"],
                "top": rect["top"],
                "width": rect["width"],
                "height": rect["height"],
            }

    if img is None:
        with mss.MSS() as sct:
            if full_screen or not target_hwnd:
                mon = sct.monitors[0]  # All monitors combined in MSS
                region = {"left": mon["left"], "top": mon["top"], "width": mon["width"], "height": mon["height"]}
            else:
                rect = get_window_rect(target_hwnd)
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

    zoom_box: list[int] | None = None
    # Zone de la FENÊTRE (pixels de fenêtre) que couvre l'image envoyée : origine et tailles réelles après arrondis,
    # d'où deux échelles exactes (relecture de Codex du 24/10 : une seule échelle théorique ratait de 238 px).
    raw_width, raw_height = img.size
    covered = (0.0, 0.0, float(region["width"]), float(region["height"]))
    if zoom is not None:
        if len(zoom) != 4:
            raise ValueError("zoom : box_2d [ymin, xmin, ymax, xmax] entre 0 et 1000.")
        ymin, xmin, ymax, xmax = (max(0, min(1000, int(v))) for v in zoom)
        if ymax <= ymin or xmax <= xmin:
            raise ValueError("zoom : zone vide (ymax > ymin et xmax > xmin attendus, 0-1000).")
        zoom_box = [ymin, xmin, ymax, xmax]
        width, height = img.size
        box = (xmin * width // 1000, ymin * height // 1000, -(-xmax * width // 1000), -(-ymax * height // 1000))
        img = img.crop(box)
        to_x, to_y = region["width"] / raw_width, region["height"] / raw_height
        covered = (box[0] * to_x, box[1] * to_y, (box[2] - box[0]) * to_x, (box[3] - box[1]) * to_y)
        img = _fit(img, max_dimension, enlarge=ZOOM_MAX_ENLARGE)
        elements_to_annotate = None  # numéros de la fenêtre entière : faux sur une zone
    else:
        img = _fit(img, max_dimension)

    # Visual Set-of-Marks overlay annotations (Stanford SoM style)
    if elements_to_annotate:
        try:
            from PIL import ImageDraw

            draw = ImageDraw.Draw(img)
            for el in elements_to_annotate:
                box = el.get("box_2d")
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

    data = encode_webp(img)

    if return_meta:
        meta = {
            "original_bounds": region,
            "original_size": (region["width"], region["height"]),
            "captured_size": img.size,
            "scale_factor": round(img.size[0] / max(1.0, covered[2]), 4),
            # x fenêtre = image_origin[0] + x image / scale_x ; y fenêtre = image_origin[1] + y image / scale_y
            "image_origin": (round(covered[0], 2), round(covered[1], 2)),
            "scale_x": round(img.size[0] / max(1.0, covered[2]), 4),
            "scale_y": round(img.size[1] / max(1.0, covered[3]), 4),
            "zoom": zoom_box,
            "image_print": image_print(img),
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
    "ListControl",
}
MAX_UIA_NODES = 4000  # borne de l'arbre lu en un appel ; au-delà : lecture signalée « truncated »


def _box_2d(rect: tuple[int, int, int, int], win_rect: dict[str, int]) -> list[int]:
    w_width = max(1, win_rect["width"])
    w_height = max(1, win_rect["height"])
    left, top, right, bottom = rect
    rel_l, rel_t = left - win_rect["left"], top - win_rect["top"]
    rel_r, rel_b = right - win_rect["left"], bottom - win_rect["top"]
    return [
        max(0, min(1000, int(rel_t / w_height * 1000))),
        max(0, min(1000, int(rel_l / w_width * 1000))),
        max(0, min(1000, int(rel_b / w_height * 1000))),
        max(0, min(1000, int(rel_r / w_width * 1000))),
    ]


def _outside(rect: tuple[int, int, int, int], win_rect: dict[str, int]) -> bool:
    left, top, right, bottom = rect
    return (
        right <= win_rect["left"] or bottom <= win_rect["top"] or left >= win_rect["right"] or top >= win_rect["bottom"]
    )


def _element_entry(idx: int, ctype: str, name: str, value: str, rect, win_rect, extra: dict[str, Any]) -> dict:
    left, top, right, bottom = rect
    entry: dict[str, Any] = {
        "index": idx,
        "type": ctype,
        "name": name[:60],
        "value": value[:60],
        "relative_center": {
            "x": left - win_rect["left"] + (right - left) // 2,
            "y": top - win_rect["top"] + (bottom - top) // 2,
        },
        "box_2d": _box_2d(rect, win_rect),
    }
    entry.update(extra)
    return entry


def _fast() -> Any:
    """Module UIA rapide, ou erreur claire s'il est indisponible."""
    if uia_fast is None:
        raise RuntimeError("UI Automation indisponible")
    return uia_fast


_WEB_DOCUMENTS: dict[int, Any] = {}  # fenêtre Chromium → son document racine (publication des changements)


def flush_chromium(hwnd: int) -> None:
    """Recette commune (NexusClaude, banc NexusWindows du 21/10) : une fenêtre Chromium recouverte ne publie ses
    changements d'accessibilité qu'à une action d'accessibilité ; ScrollIntoView sur son document racine (sans effet
    visible) les fait publier. Sans cela, un champ ou les options d'une liste dépliée restent absents de l'arbre."""
    if uia is None or not hwnd or not win32_controls.class_name(hwnd).startswith("Chrome_WidgetWin_"):
        return
    if win32_controls.root_of(int(user32.GetForegroundWindow() or 0)) == hwnd:
        return
    document: Any = _WEB_DOCUMENTS.get(hwnd)
    try:
        if document is None:
            root: Any = uia.ControlFromHandle(hwnd)
            document = root.DocumentControl(searchDepth=6) if root is not None else None
            if document is None:
                return
            if not document.Exists(0, 0):
                return
            _WEB_DOCUMENTS[hwnd] = document
        document.GetPattern(uia.PatternId.ScrollItemPattern).ScrollIntoView()
    except Exception:  # noqa: BLE001 - document remplacé (navigation) ou motif absent : arbre peut-être en retard
        _WEB_DOCUMENTS.pop(hwnd, None)


def _take_focus_quiet(ctrl: Any, target_hwnd: int, timeout_s: float = 0.5, front: int = 0) -> bool:
    """Focus DOM de l'élément sans activer la fenêtre : action MSAA accSelect(SELFLAG_TAKEFOCUS) (UIA SetFocus, lui,
    active la fenêtre ; mesuré par NexusClaude). Relu : sans focus prouvé, rien ne doit être tapé. front : fenêtre de
    Julien, rendue aussitôt si la cible prend le premier plan pendant l'attente."""
    top = win32_controls.root_of(target_hwnd) or target_hwnd
    ctrl.GetLegacyIAccessiblePattern().Select(1)
    deadline = time.monotonic() + timeout_s
    while True:
        if front:
            _hand_back(top, front)
        flush_chromium(target_hwnd)
        try:
            if ctrl.HasKeyboardFocus:
                return True
        except Exception:  # noqa: BLE001
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.03)


_SIM_PRIMED: set[int] = set()  # processus Chromium déjà passés par une activation simulée
WM_SYSCOMMAND, SC_HOTKEY = 0x0112, 0xF150


def _hand_back(top: int, front: int, timeout_s: float = 0.4) -> bool:
    """Rend le premier plan à Julien quand la cible l'a pris (recette NexusClaude, foreground._hand_over) : notre
    SetForegroundWindow est refusé à un processus d'arrière-plan ; on demande au fil QUI DÉTIENT le premier plan de
    le rendre lui-même (WM_SYSCOMMAND SC_HOTKEY, traité par DefWindowProc en SetForegroundWindow(lParam) : 2 à 3 ms,
    mesuré). Seulement si la fenêtre au premier plan est celle de la cible, jamais une fenêtre de Julien."""
    fg = int(user32.GetForegroundWindow() or 0)
    if not front or front == top or not user32.IsWindow(front) or win32_controls.root_of(fg) != top:
        return False
    user32.PostMessageW(fg, WM_SYSCOMMAND, SC_HOTKEY, front)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        current = int(user32.GetForegroundWindow() or 0)
        if current == front:
            return True
        if win32_controls.root_of(current) != top:
            return False  # Julien a choisi une autre fenêtre entre-temps : on ne la lui prend pas
        time.sleep(0.01)
    if win32_controls.root_of(int(user32.GetForegroundWindow() or 0)) != top:
        return False
    return restore_foreground(front)


def _settle_first_activation(top: int, front: int) -> bool:
    """Première activation simulée d'un processus (recette NexusClaude, mesurée le 20/10) : une application lancée
    depuis le programme au premier plan garde le droit de prendre le premier plan une fois, et sa première prise de
    focus l'utilise. On attend ce vol (0,6 s au plus), on rend le premier plan à Julien, puis l'activation simulée
    est renvoyée. Vrai si elle l'a été (le focus est alors à reprendre). Banc commun du 21/10 : sans cela, Electron
    gardait le premier plan 2 s, non rendu."""
    pid = app_pid(top)
    if not pid or pid in _SIM_PRIMED:
        return False
    _SIM_PRIMED.add(pid)
    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        if win32_controls.root_of(int(user32.GetForegroundWindow() or 0)) == top:
            break
        time.sleep(0.01)
    else:
        return False
    _hand_back(top, front)
    give_back = time.monotonic() + 0.5
    while win32_controls.root_of(int(user32.GetForegroundWindow() or 0)) == top and time.monotonic() < give_back:
        time.sleep(0.01)
    win32_controls.send(top, win32_controls.WM_NCACTIVATE, 1, 0)
    win32_controls.send(top, win32_controls.WM_ACTIVATE, 1, 0)
    return True


def _give_back_after_simulation(top: int, front: int) -> None:
    """Filet de sécurité en fin d'activation simulée : si la cible tient le premier plan, il est rendu à Julien."""
    _hand_back(top, front)


def _caret_to_end(ctrl: Any) -> bool:
    """Caret en fin de texte, sans sélection (TextPattern : plage vide à la fin, sélectionnée). Faux si impossible."""
    try:
        document = ctrl.GetTextPattern().DocumentRange
        document.MoveEndpointByRange(0, document, 1)  # début ← fin : plage vide en fin de texte
        document.Select()
        return True
    except Exception:  # noqa: BLE001
        return False


def _chromium_simulated_typing(
    target_hwnd: int, ctrl: Any, text: str, done: Callable[[], bool], caret_to_end: bool = False
) -> bool | None:
    """Frappe Chromium sans activation réelle (recette commune) : activation simulée, focus accSelect relu, WM_CHAR
    à la fenêtre de premier niveau, effet relu. True relu, None envoyé sans effet relu (jamais renvoyé)."""
    top = win32_controls.root_of(target_hwnd) or target_hwnd
    front = user32.GetForegroundWindow()
    try:
        with win32_controls.simulated_activation(top):
            _take_focus_quiet(ctrl, target_hwnd, front=front)
            _settle_first_activation(top, front)
            # Focus repris et prouvé JUSTE avant l'envoi (relecture de Codex : un script de la page a pu le déplacer
            # pendant l'attente du premier plan), caret mis en fin de texte (ajout, jamais au début ni sur une
            # sélection) ; sans l'un ou l'autre, rien n'est tapé.
            if not _take_focus_quiet(ctrl, target_hwnd, front=front):
                raise win32_controls.MessageError("focus sans activation non relu : rien n'a été tapé")
            if caret_to_end and not _caret_to_end(ctrl):
                raise win32_controls.MessageError("caret non placé en fin de texte : rien n'a été tapé")
            emergency_stop.check()
            win32_controls.post_chars(top, text)
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                time.sleep(0.05)
                flush_chromium(target_hwnd)
                if done():
                    return True
        return None
    finally:
        _give_back_after_simulation(top, front)


def _window_tree(hwnd: int, max_nodes: int = 3000, time_budget: float = 2.0) -> Any:
    """Arbre UIA d'une fenêtre ; ses listes déroulantes Win32/WinForms OUVERTES sont lues sans leur sous-arbre (qui
    ferait échouer toute la lecture après ~8 s, mesuré le 16/10). Chromium recouvert : changements publiés d'abord."""
    flush_chromium(hwnd)
    return _fast().reader().read_tree(hwnd, max_nodes=max_nodes, time_budget=time_budget,
                                       skip_subtrees=_open_combos(hwnd))  # fmt: skip


def _open_combos(hwnd: int) -> list[int]:
    if not hwnd or win32_controls.family(hwnd) not in win32_controls.NATIVE_FAMILIES:
        return []
    try:
        return [combo for combo, _drop in win32_controls.open_combo_lists(hwnd)]
    except Exception:  # noqa: BLE001 - fenêtre disparue : lecture normale
        return []


def _list_owner(nodes: list[Any], node: Any) -> Any:
    """Liste déroulante UIA (ComboBox) qui porte une option, d'après l'arbre lu (None si l'option n'en a pas)."""
    parent = node.parent
    for _ in range(8):
        if parent is None or parent < 0 or parent >= len(nodes):
            return None
        if nodes[parent].control_type == "ComboBox":
            return nodes[parent].element
        parent = nodes[parent].parent
    return None


def _open_combo_items(target_hwnd: int) -> list[tuple[Any, dict[str, Any]]]:
    """Options des listes déroulantes Win32/WinForms OUVERTES de la fenêtre.

    Leur liste est une ComboLBox, fenêtre de premier niveau à part, absente de l'arbre UIA de la fenêtre (banc du
    16/10 : « Bravo introuvable »). Libellés et rangs lus par LB_GETTEXT sur la ComboLBox possédée ; l'élément UIA de
    même rang et même libellé donne la position. Rend [(nœud UIA, info)] ; info["combo_hwnd"] = liste déroulante."""
    if uia_fast is None or not target_hwnd or win32_controls.family(target_hwnd) not in win32_controls.NATIVE_FAMILIES:
        return []
    out: list[tuple[Any, dict[str, Any]]] = []
    fam = win32_controls.family(target_hwnd)
    for combo, drop in win32_controls.open_combo_lists(target_hwnd):
        labels = [" ".join(text.split()) for text in win32_controls.listbox_items(drop)]
        try:
            tree = uia_fast.reader().read_tree(drop, max_nodes=600, time_budget=0.8)
        except Exception:  # noqa: BLE001 - liste illisible : pas d'options, jamais d'options inventées
            continue
        items = [node for node in tree.nodes if node.control_type == "ListItem"]
        for rank, node in enumerate(items):
            if rank >= len(labels) or node.name != labels[rank] or node.rect is None:
                continue  # rang contrôlé par le libellé lu par messages
            info = _node_info(node)
            info.update(framework=fam, combo_hwnd=combo, item_index=rank, open_list=True)
            out.append((node, info))
    return out


def _read_uia_elements(
    target_hwnd: int,
    win_rect: dict[str, int],
    max_elements: int = 80,
    max_depth: int = 30,
    time_budget: float = 2.0,
    query: str | None = None,
) -> dict[str, Any]:
    """Éléments interactifs de la fenêtre : lecture en cache UIA (un aller-retour), repli pas à pas si elle échoue.

    Rend {"elements", "controls" (index → élément), "infos" (index → propriétés), "report"} ; report["status"] vaut
    ok, truncated (bornes atteintes : éléments manquants) ou failed (rien de lisible), avec la raison."""
    elements: list[dict[str, Any]] = []
    controls: dict[int, Any] = {}
    infos: dict[int, dict[str, Any]] = {}
    report: dict[str, Any] = {"method": "uia_cache_subtree", "status": "ok"}
    t0 = time.perf_counter()
    cache_error = ""
    if uia_fast is not None:
        try:
            tree = _window_tree(target_hwnd, max_nodes=MAX_UIA_NODES, time_budget=time_budget)
        except Exception as error:  # noqa: BLE001
            tree = None
            cache_error = f"{type(error).__name__}: {error}"
        if tree is not None and tree.status != "failed":
            report["method"] = getattr(tree, "method", "uia_cache_subtree")
            report["nodes"] = len(tree.nodes)
            if tree.status == "truncated":
                report["status"] = "truncated"
                report["reason"] = tree.reason
            depth_cut = False
            for tree_index, node in enumerate(tree.nodes[1:], start=1):
                ctype = node.control_type
                rect = node.rect
                if f"{ctype}Control" not in INTERACTIVE_CONTROL_TYPES or rect is None or _outside(rect, win_rect):
                    continue
                if node.depth > max_depth:
                    depth_cut = True
                    continue
                name = node.name
                value = " ".join(str(node.props.get("value") or "").split())
                if query and query not in f"{name} {value} {ctype}".lower():
                    continue
                if len(elements) >= max_elements:
                    report["status"] = "truncated"
                    report["reason"] = (
                        f"Limite de {max_elements} éléments atteinte : d'autres existent (augmenter max_elements "
                        "ou préciser query)."
                    )
                    break
                idx = len(elements) + 1
                extra: dict[str, Any] = {}
                if node.props.get("has_toggle") and node.props.get("toggle") is not None:
                    extra["checked"] = int(node.props["toggle"]) == 1
                if node.props.get("has_selection_item") and node.props.get("selected") is not None:
                    extra["selected"] = bool(node.props["selected"])
                if node.props.get("enabled") is False:
                    extra["enabled"] = False
                elements.append(_element_entry(idx, ctype, name, value, rect, win_rect, extra))
                controls[idx] = node.element
                infos[idx] = {
                    "type": ctype,
                    "type_id": int(node.props.get("control_type") or 0),
                    "name": name,
                    "automation_id": str(node.props.get("automation_id") or ""),
                    "hwnd": int(node.props.get("hwnd") or 0),
                    "host_hwnd": int(node.host_hwnd or 0),
                    "framework": node.framework,
                    "class_name": str(node.props.get("class_name") or ""),
                    "props": node.props,
                    "tree_index": tree_index,
                }
                parent = node.parent
                if ctype == "Edit" and parent is not None and 0 <= parent < len(tree.nodes):
                    if tree.nodes[parent].control_type == "ComboBox":
                        infos[idx]["combo_parent"] = parent  # champ d'une liste déroulante modifiable
                if ctype == "ListItem":
                    owner = _list_owner(tree.nodes, node)
                    if owner is not None:
                        infos[idx]["list_owner"] = owner
            if depth_cut and report["status"] == "ok":
                report["status"] = "truncated"
                report["reason"] = f"Éléments plus profonds que max_depth={max_depth} ignorés."
            report["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            return {"elements": elements, "controls": controls, "infos": infos, "report": report}
        if tree is not None:
            cache_error = tree.reason

    # Repli : parcours pas à pas (un aller-retour par nœud), borné par le temps.
    report = {"method": "uia_walk_fallback", "status": "ok"}
    if cache_error:
        report["cache_error"] = cache_error
    if uia is None:
        report["status"] = "failed"
        report["reason"] = "UI Automation indisponible (module uiautomation absent)."
        return {"elements": elements, "controls": controls, "infos": infos, "report": report}
    walked = _legacy_walk(target_hwnd, win_rect, max_elements, max_depth, time_budget, query)
    for idx, (entry, ctrl) in enumerate(walked["items"], start=1):
        entry["index"] = idx
        elements.append(entry)
        controls[idx] = ctrl
        infos[idx] = walked["infos"][idx - 1]
    report.update(walked["report"])
    if report["status"] == "ok" and cache_error and not elements:
        report["status"] = "failed"
        report["reason"] = f"Lecture en cache en échec ({cache_error}) et parcours sans élément."
    report["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return {"elements": elements, "controls": controls, "infos": infos, "report": report}


def _legacy_walk(
    target_hwnd: int,
    win_rect: dict[str, int],
    max_elements: int,
    max_depth: int,
    time_budget: float,
    query: str | None,
) -> dict[str, Any]:
    """Ancien parcours (GetChildren + GetValuePattern par nœud) : repli et point de comparaison des mesures."""
    items: list[tuple[dict[str, Any], Any]] = []
    infos: list[dict[str, Any]] = []
    report: dict[str, Any] = {"status": "ok"}
    start_time = time.perf_counter()
    if uia is None:
        return {"items": items, "infos": infos, "report": {"status": "failed", "reason": "UI Automation indisponible"}}
    try:
        root_ctrl = uia.ControlFromHandle(target_hwnd)
    except Exception as error:  # noqa: BLE001
        return {"items": items, "infos": infos, "report": {"status": "failed", "reason": str(error)}}
    if not root_ctrl:
        return {"items": items, "infos": infos, "report": {"status": "failed", "reason": "Fenêtre invisible à UIA."}}

    def over_budget() -> bool:
        if (time.perf_counter() - start_time) > time_budget:
            report["status"] = "truncated"
            report["reason"] = f"Budget de lecture de {time_budget:g} s dépassé : des éléments manquent."
            return True
        return False

    def walk(ctrl: Any, depth: int = 0) -> None:
        if depth > max_depth or len(items) >= max_elements or over_budget():
            return
        try:
            children = ctrl.GetChildren()
        except Exception:  # noqa: BLE001
            return
        for child in children:
            if len(items) >= max_elements or over_budget():
                break
            try:
                c_rect = child.BoundingRectangle
                rect = (c_rect.left, c_rect.top, c_rect.right, c_rect.bottom)
            except Exception:  # noqa: BLE001
                continue
            if _outside(rect, win_rect):
                continue
            ctype_full = child.ControlTypeName
            if ctype_full in INTERACTIVE_CONTROL_TYPES and rect[2] > rect[0] and rect[3] > rect[1]:
                c_name = child.Name or ""
                val_str = ""
                try:
                    val_pattern = child.GetValuePattern()
                    if val_pattern:
                        val_str = val_pattern.Value or ""
                except Exception:  # noqa: BLE001
                    pass
                ctype = ctype_full.replace("Control", "")
                if not query or query in f"{c_name} {val_str} {ctype}".lower():
                    items.append((_element_entry(0, ctype, c_name, val_str, rect, win_rect, {}), child))
                    infos.append({"type": ctype, "name": " ".join(c_name.split()), "hwnd": 0, "host_hwnd": 0})
            walk(child, depth + 1)

    walk(root_ctrl)
    if len(items) >= max_elements and report["status"] == "ok":
        report["status"] = "truncated"
        report["reason"] = f"Limite de {max_elements} éléments atteinte."
    return {"items": items, "infos": infos, "report": report}


def get_window_state(
    hwnd: int | str | None = None,
    max_elements: int = 80,
    capture_screenshot: bool = False,
    output_path: str | None = None,
    max_depth: int = 30,
    time_budget: float = 2.0,
    include_data_url: bool = False,
    annotate_screenshot: bool = False,
    query: str | None = None,
    zoom: list[int] | None = None,
) -> dict[str, Any]:
    """Extracts compact UI Automation interactive elements and optional WebP screenshot.

    Equips Antigravity with Set-of-Marks markers [#1], [#2] and Gemini box_2d coordinates.
    Bounded by max_depth and time budget with spatial pruning and optional visual SoM overlay.
    Optional query filters elements by substring in name, value, or control type.
    """
    global _element_cache, _cached_window_hwnd, _cached_window_title
    ensure_default_desktop()

    target_hwnd = resolve_window(hwnd)
    if not target_hwnd:
        raise ValueError("Aucune fenêtre active détectée.")
    ensure_readable(target_hwnd)

    win_rect = get_window_rect(target_hwnd)

    length = user32.GetWindowTextLengthW(target_hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(target_hwnd, buf, length + 1)
    title = buf.value

    _, proc_name = get_process_image_path(app_pid(target_hwnd))

    _element_cache.clear()
    _element_info.clear()
    _cached_window_hwnd = target_hwnd
    _cached_window_title = title

    q_lower = query.lower().strip() if query else None
    read = _read_uia_elements(
        target_hwnd, win_rect, max_elements=max_elements, max_depth=max_depth, time_budget=time_budget, query=q_lower
    )
    elements = read["elements"]
    for element in elements:
        idx = element["index"]
        _element_cache[idx] = read["controls"][idx]
        _element_info[idx] = read["infos"][idx]
    # Liste déroulante Win32/WinForms ouverte : ses options (fenêtre ComboLBox à part) sont ajoutées à la fin.
    for node, info in _open_combo_items(target_hwnd):
        if q_lower and q_lower not in f"{info['name']} listitem".lower():
            continue
        idx = len(elements) + 1
        elements.append(_element_entry(idx, "ListItem", info["name"], "", node.rect, win_rect, {"open_list": True}))
        _element_cache[idx] = node.element
        _element_info[idx] = info

    result: dict[str, Any] = {
        "hwnd": target_hwnd,
        "title": title,
        "process_name": proc_name,
        "family": win32_controls.family(target_hwnd),
        "bounds": win_rect,
        "element_count": len(elements),
        "elements": elements,
        "uia": read["report"],
    }
    if browser_note(proc_name):
        result["note"] = BROWSER_NOTE
    if read["report"]["status"] != "ok":
        # Jamais de liste vide silencieuse : une lecture tronquée ou en échec est dite.
        result["warning"] = read["report"].get("reason") or "Lecture UI Automation incomplète."

    if capture_screenshot or output_path:
        annotate_list = elements if annotate_screenshot else None
        webp_bytes, meta = capture_window_image(
            target_hwnd, zoom=zoom, return_meta=True, elements_to_annotate=annotate_list
        )
        result["image_dimensions"] = meta.get("captured_size")
        result["scale_factor"] = meta.get("scale_factor")
        result["image_origin"] = meta.get("image_origin")
        result["scale_x"], result["scale_y"] = meta.get("scale_x"), meta.get("scale_y")
        result["image_print"] = meta.get("image_print")
        if meta.get("zoom"):
            result["zoom"] = meta["zoom"]

        if output_path:
            dest = Path(output_path).expanduser().resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(webp_bytes)
        else:
            dest = save_screenshot(webp_bytes, "window_state")
        result["screenshot_path"] = str(dest)

        if include_data_url:
            result["screenshot_data_url"] = f"data:image/webp;base64,{base64.b64encode(webp_bytes).decode('ascii')}"

    return result


# -----------------------------------------------------------------------------
# Relecture : chaque action dit ce qu'elle a constaté (verified), jamais « envoyé » seul
# -----------------------------------------------------------------------------
EFFECT_WAIT_S = 0.35  # attente d'un effet visible après une action sans état relisible
CHECK_SETTLE_S = 1.6  # case lente (WinForms, applis chargées) : relecture patiente avant de conclure « sans effet »
EFFECT_POLL_S = 0.05
EXPECT_TIMEOUT_S = 1.5  # attente par défaut d'une postcondition `expect`
STATEFUL_SELECT_ROLES = {"ListItem", "TabItem", "RadioButton", "TreeItem", "DataItem"}


def _success(verified: bool | None) -> bool | None:
    """`success` suit la relecture : vrai seulement si l'effet est constaté, faux s'il est constaté absent, None si
    la commande est partie sans effet lisible (à relire par look avant de poursuivre)."""
    if verified is True:
        return True
    if verified is False:
        return False
    return None


def _window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _process_windows(pid: int) -> tuple[int, ...]:
    """Fenêtres visibles de premier niveau du processus (une boîte de dialogue ou un menu apparu est un effet)."""
    found: list[int] = []

    def cb(hwnd: int, _: int) -> bool:
        if user32.IsWindowVisible(hwnd) and _window_pid(hwnd) == pid:
            found.append(int(hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return tuple(sorted(found))


CARET_MAX_W, CARET_MAX_H = 3, 48  # changement confiné à une barre aussi fine : clignotement du curseur de saisie
PIXEL_DELTA = 32  # écart de gris en deçà duquel un pixel n'a pas changé (lissage, rendu sous-pixel)


TREE_DIGEST_NODES = 1500


def _tree_digest(hwnd: int) -> str | None:
    """Empreinte de l'arbre UI Automation (types, noms, valeurs, coches, sélections, états) : un clic dont l'effet
    n'est pas dessiné à temps (ou fenêtre que PrintWindow ne rend pas) se voit quand même dans l'arbre."""
    if uia_fast is None or not hwnd or not user32.IsWindow(hwnd):
        return None
    try:
        tree = _window_tree(hwnd, max_nodes=TREE_DIGEST_NODES, time_budget=0.8)
    except Exception:  # noqa: BLE001
        return None
    if tree.status == "failed":
        return None
    keys = ("value", "toggle", "selected", "expand", "enabled")
    parts = [(n.control_type, n.name, *(str(n.props.get(k)) for k in keys)) for n in tree.nodes]
    return hashlib.blake2b(repr(parts).encode("utf-8", "replace"), digest_size=16).hexdigest()


def window_fingerprint(hwnd: int, with_tree: bool = False) -> dict[str, Any] | None:
    """Empreinte d'une fenêtre : titre, fenêtres de son processus, image en niveaux de gris (PrintWindow, sans la
    mettre devant), et au besoin l'empreinte de son arbre UIA (relue une fois, à l'échéance). None si la fenêtre
    n'existe pas."""
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    image = None
    try:
        img = capture_window_background_gdi(hwnd)
        if img is not None:
            image = img.convert("L")
    except Exception:  # noqa: BLE001
        image = None
    rect = get_window_rect(hwnd)
    out = {
        "title": _window_text(hwnd),
        "windows": _process_windows(app_pid(hwnd)),
        "image": image,
        "rect": (rect["left"], rect["top"], rect["width"], rect["height"]),
    }
    if with_tree:
        out["tree"] = _tree_digest(hwnd)
    return out


def _fingerprint_changed(before: dict[str, Any] | None, after: dict[str, Any] | None) -> str:
    """Ce qui a changé entre deux empreintes (« » si rien). Image : pixels nettement changés, à pleine résolution
    (un chiffre d'une étiquette suffit) ; un changement confiné à une barre de 3 px de large au plus est le
    clignotement d'un curseur de saisie, ignoré."""
    if before is None or after is None:
        return ""
    if before["title"] != after["title"]:
        return "titre de la fenêtre"
    if before["windows"] != after["windows"]:
        return "fenêtres de l'application"
    # Taille : le RECTANGLE de la fenêtre, jamais la taille de deux captures (banc du 21/10, 23:42 : deux captures de
    # tailles différentes d'une fenêtre recouverte ont validé un clic que le labo n'avait pas reçu).
    if before.get("rect") is not None and after.get("rect") is not None and before["rect"] != after["rect"]:
        return "taille de la fenêtre"
    a, b = before.get("image"), after.get("image")
    if a is not None and b is not None:
        if a.size != b.size:
            return ""  # captures incomparables : rien n'est prouvé
        from PIL import ImageChops

        def threshold(v: int) -> int:
            return 255 if v > PIXEL_DELTA else 0

        box = ImageChops.difference(a, b).point(threshold).getbbox()
        if box and (box[2] - box[0] > CARET_MAX_W or box[3] - box[1] > CARET_MAX_H):
            return "image de la fenêtre"
    return ""


PIXEL_EFFECT = "image de la fenêtre"
PIXEL_ONLY_NOTE = "seule l'image a changé (animation possible) : effet non prouvé, vérifier sur l'image"


STRUCTURAL = ("titre de la fenêtre", "fenêtres de l'application", "taille de la fenêtre")


def _wait_window_effect(
    hwnd: int, before: dict[str, Any] | None, timeout: float = EFFECT_WAIT_S, structural_only: bool = False
):
    """(True, ce qui a changé) dès qu'un effet PROUVÉ apparaît (titre, fenêtres de l'application, taille, arbre UI
    Automation) ; des pixels changés seuls ne prouvent rien (animation, survol, curseur) : (None, note) ; (None, "")
    sans effet visible — l'issue reste inconnue, jamais affirmée. ``structural_only`` : seuls titre, fenêtres et
    taille prouvent (double clic posté : son premier clic sélectionne l'élément, ce qui change l'arbre sans prouver le
    double clic ; banc du 21/10, 23:42 : sélection seule prise pour un double clic réussi)."""
    if before is None:
        return None, ""
    deadline = time.monotonic() + timeout
    pixels = False
    while True:
        what = _fingerprint_changed(before, window_fingerprint(hwnd))
        if what and what != PIXEL_EFFECT and (not structural_only or what in STRUCTURAL):
            return True, what
        pixels = pixels or what == PIXEL_EFFECT
        if time.monotonic() >= deadline:
            tree_before = None if structural_only else before.get("tree")
            if tree_before is not None:
                tree_after = _tree_digest(hwnd)
                if tree_after is not None and tree_after != tree_before:
                    return True, "arbre UI Automation (texte, valeur ou état changé)"
            return None, (PIXEL_ONLY_NOTE if pixels else "")
        time.sleep(EFFECT_POLL_S)


def _other_agent_holds_token() -> bool:
    """Vrai si un AUTRE agent tient le jeton commun (il a mis sa fenêtre devant : ne pas la lui reprendre)."""
    try:
        shared_dir = Path(__file__).resolve().parent.parent.parent / "commun"
        if shared_dir.exists() and str(shared_dir) not in sys.path:
            sys.path.insert(0, str(shared_dir))
        from foreground_lock import holder

        who = holder()
    except Exception:  # noqa: BLE001 - jeton illisible : prudence, ne pas toucher au premier plan
        return True
    return who is not None and who.get("owner") != "NexusAGY"


def _restore_if_stolen(front_before: int) -> bool:
    """Rend le premier plan à Julien si une technique d'arrière-plan l'a pris. Vrai si un vol a été réparé. Jamais
    pendant qu'un autre agent tient le jeton commun (foreground-token.md) : sa fenêtre est devant à bon droit."""
    if _other_agent_holds_token():
        return False
    if front_before and user32.GetForegroundWindow() != front_before and user32.IsWindow(front_before):
        restore_foreground(front_before)
        return True
    return False


def _element_family(info: dict[str, Any] | None, target_hwnd: int) -> str:
    """Famille d'interface de l'élément (FrameworkId UIA, sinon classe de la fenêtre)."""
    fw = str((info or {}).get("framework") or "")
    if fw in ("Win32", "WinForms", "WPF", "XAML", "DirectUI"):
        return fw
    if fw.lower() == "chrome":
        return "Chromium"
    return win32_controls.family(target_hwnd) if target_hwnd and user32.IsWindow(target_hwnd) else "Inconnue"


def _native_kind(hwnd: int) -> str:
    """Nature d'un contrôle Win32/WinForms par sa classe : button, checkbox, radio, edit, combo, listbox ou « »."""
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    cls = win32_controls.base_class(hwnd)
    if cls in win32_controls.BUTTON_CLASSES:
        kind = win32_controls.button_kind(hwnd)
        if kind in win32_controls.CHECKBOX_KINDS:
            return "checkbox"
        if kind in win32_controls.RADIO_KINDS:
            return "radio"
        return "button"
    if cls in win32_controls.EDIT_CLASSES:
        return "edit"
    if cls in win32_controls.COMBO_CLASSES:
        return "combo"
    if cls in win32_controls.LISTBOX_CLASSES:
        return "listbox"
    return ""


def _read_state(ctrl: Any, info: dict[str, Any] | None) -> dict[str, Any]:
    """État actuel d'un élément : messages Win32 pour les contrôles natifs (valeur, coche, sélection), propriétés UIA
    fraîches (un aller-retour) pour le reste. `exists` faux si l'élément a disparu."""
    info = info or {}
    state: dict[str, Any] = {}
    own = int(info.get("hwnd") or 0)
    kind = _native_kind(own)
    if kind == "edit":
        state["value"] = win32_controls.get_text(own)
    elif kind in ("checkbox", "radio"):
        state["toggle"] = win32_controls.get_check(own)
    elif kind == "combo":
        state["value"] = win32_controls.combo_selected(own)
    elif kind == "listbox":
        state["value"] = win32_controls.listbox_selected(own)
    if uia_fast is not None and ctrl is not None:
        try:
            props = uia_fast.refresh(ctrl)
            state["exists"] = True
            for key in ("value", "toggle", "selected", "expand", "name", "enabled"):
                if key in props and state.get(key) is None:
                    state[key] = props[key]
        except uia_fast.UIAReadError:
            state.setdefault("exists", False)
        except Exception:  # noqa: BLE001
            pass
    return state


def _norm_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


SYNCHRONIZE = 0x00100000
RPC_S_CALLPENDING = -2147417835  # 0x80010115 : délai écoulé
_ole32 = ctypes.WinDLL("ole32")
_ole32.CoWaitForMultipleHandles.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.ULONG,
    ctypes.POINTER(wintypes.HANDLE),
    ctypes.POINTER(wintypes.DWORD),
]
_ole32.CoWaitForMultipleHandles.restype = ctypes.c_long
kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenThread.restype = wintypes.HANDLE


def _com_wait_thread(t: threading.Thread, timeout_s: float) -> bool:
    """Attend la fin du fil en pompant les appels COM entrants (fil STA : un proxy MSAA/WinForms qui rappelle ce fil
    ne se bloque pas). Faux si l'attente COM n'a pas eu lieu (COM absent sur ce fil, poignée refusée) : join alors."""
    if not t.native_id:
        return False
    handle = kernel32.OpenThread(SYNCHRONIZE, False, t.native_id)
    if not handle:
        return False
    try:
        handles = (wintypes.HANDLE * 1)(handle)
        index = wintypes.DWORD()
        hr = _ole32.CoWaitForMultipleHandles(0, max(1, int(timeout_s * 1000)), 1, handles, ctypes.byref(index))
    finally:
        kernel32.CloseHandle(handle)
    return hr in (0, RPC_S_CALLPENDING)


def _invoke_with_timeout(ctrl: Any) -> str:
    """UIA Invoke sur un fil borné : « invoked », ou « pending » si Invoke ne revient pas (fenêtre modale ouverte)."""
    invoke_pat = ctrl.GetInvokePattern()
    if not invoke_pat:
        raise LookupError("Motif Invoke absent.")
    invoke_err: list[Exception] = []

    def _do_invoke() -> None:
        try:
            ctypes.windll.ole32.CoInitialize(None)
            invoke_pat.Invoke()
        except Exception as ex:  # noqa: BLE001
            invoke_err.append(ex)
        finally:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:  # noqa: BLE001
                pass

    t = threading.Thread(target=_do_invoke, daemon=True)
    t.start()
    if not _com_wait_thread(t, INVOKE_TIMEOUT_S):
        t.join(timeout=INVOKE_TIMEOUT_S)
    if t.is_alive():
        return "pending"
    if invoke_err:
        raise invoke_err[0]
    return "invoked"


def _pattern_call(getter: str, call: Callable[[Any], Any]) -> Callable[[Any], str]:
    def run(ctrl: Any) -> str:
        pattern = getattr(ctrl, getter)()
        if not pattern:
            raise LookupError(f"Motif {getter[3:-7]} absent.")
        call(pattern)
        return "uia"

    return run


_UIA_TOGGLE = _pattern_call("GetTogglePattern", lambda p: p.Toggle())
_UIA_SELECT = _pattern_call("GetSelectionItemPattern", lambda p: p.Select())


def _uia_expand_or_collapse(ctrl: Any) -> str:
    pattern = ctrl.GetExpandCollapsePattern()
    if not pattern:
        raise LookupError("Motif ExpandCollapse absent.")
    if getattr(pattern, "ExpandCollapseState", 0) == 1:
        pattern.Collapse()
    else:
        pattern.Expand()
    return "uia"


POSTED_NO_RETRY = frozenset({"BN_CLICKED"})  # banc commun du 21/10 : bouton qui ouvre une boîte modale


def _run_chain(
    chain: list[tuple[str, Callable[[], Any]]],
    verify: Callable[[Any], tuple[bool | None, str]],
    front_before: int,
) -> dict[str, Any]:
    """Essaie les techniques dans l'ordre. Une technique qui lève ne s'applique pas (suivante) ; une technique dont
    l'effet est relu ABSENT (état inchangé, donc sans effet de bord) laisse la place à la suivante ; un effet relu ou
    inconnu arrête la chaîne (jamais de double activation)."""
    tried: list[dict[str, str]] = []
    for name, run in chain:
        try:
            detail = run()
        except (emergency_stop.EmergencyStopError, UserInterruptError):
            raise
        except win32_controls.PartialSendError as error:
            # Une partie est partie : issue inconnue, jamais une technique de plus (elle referait l'action).
            return {"technique": name, "detail": str(error), "verified": None, "pending": True, "tried": tried}
        except Exception as error:  # noqa: BLE001 - technique inapplicable : la suivante
            tried.append({"technique": name, "error": f"{type(error).__name__}: {error}"})
            continue
        stolen = _restore_if_stolen(front_before)
        if detail == "pending":
            return {"technique": name, "detail": detail, "verified": None, "pending": True, "tried": tried}
        if detail == "already":
            return {"technique": name, "detail": detail, "verified": True, "verified_by": "état déjà voulu",
                    "already": True, "tried": tried}  # fmt: skip
        verified, how = verify(detail)
        if verified is False and name in POSTED_NO_RETRY:
            # Message posté : traité plus tard, et son effet peut être ailleurs (boîte modale ouverte). « Absent »
            # n'est pas prouvé : inconnu, jamais une seconde technique (elle doublerait l'action).
            verified, how = None, "message posté, effet non relu (aucune autre technique tentée)"
        if verified is False and how != "partial":
            tried.append({"technique": name, "error": f"sans effet relu ({how})" if how else "sans effet relu"})
            continue
        out = {"technique": name, "detail": detail, "verified": verified, "verified_by": how, "tried": tried}
        if stolen:
            out["focus_stolen_restored"] = True
        return out
    return {"technique": None, "tried": tried}


# Déclencheur d'un sélecteur de fichiers (bouton d'<input type=file>, zone de dépôt, « Parcourir ») : Chromium n'ouvre
# ce sélecteur que sur une vraie activation de l'utilisateur ; UIA Invoke est accepté sans rien ouvrir, et le survol ou
# le focus changent l'image et l'arbre (relevé par NexusWindows pour Claude le 25/10 dans Chrome : faux succès).
FILE_PICKER = re.compile(
    r"\b(choose (a |your )?files?|select (a |the |your )?files?|browse|upload|attach|add (a )?files?|drop|"
    r"choisi(r|ssez) (un |des |les |votre |vos )?fichiers?|selectionne(r|z) (un |des |les |votre |vos )?fichiers?|"
    r"parcouri?r|parcourez|televers(er|ez)|import(er|ez)|joindre|ajoute(r|z) (un |des |votre |vos )?fichiers?|"
    r"depos(er|ez)|gliss(er|ez))\b"
)
PICKER_ROLES = {"Button", "Hyperlink", "Group", "Custom", "Text", "Image", "Pane", "SplitButton"}
FILE_DIALOG_S = 2.0  # le sélecteur de Windows s'ouvre en ~0,3 s (mesuré par Claude) ; au-delà, il ne viendra plus


def opens_file_picker(role: str, name: str) -> bool:
    """L'élément ouvre-t-il un sélecteur de fichiers (d'après son libellé, anglais ou français) ?"""
    return role in PICKER_ROLES and bool(FILE_PICKER.search(" ".join(_plain(name).split())))


def owned_dialogs(hwnd: int) -> set[int]:
    """Fenêtres visibles que possède la fenêtre `hwnd` (boîtes de dialogue, sélecteur de fichiers)."""
    found: set[int] = set()

    def enum_cb(child: int, _: int) -> bool:
        if user32.GetWindow(child, GW_OWNER) == hwnd and user32.IsWindowVisible(child) and not is_window_cloaked(child):
            found.add(int(child))
        return True

    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return found


def _click_plan(
    ctrl: Any, info: dict[str, Any], target_hwnd: int
) -> tuple[str, list[tuple[str, Callable[[], Any]]], Callable[[Any], tuple[bool | None, str]]]:
    """Techniques d'arrière-plan d'un clic sur un élément, dans l'ordre de sa famille d'interface, et sa relecture.

    Win32 natif : messages d'abord (BN_CLICKED, LB_SETCURSEL, WM_COMMAND de menu), jamais UIA Invoke sur un bouton
    Win32 (son proxy appelle SetForegroundWindow) ni UIA Select sur une liste Win32/WinForms (silencieux).
    WinForms : UIA puis messages. WPF, UWP/WinUI, Chromium/Electron : UIA seulement."""
    fam = _element_family(info, target_hwnd)
    role = str(info.get("type") or "")
    name = str(info.get("name") or "")
    props = info.get("props") or {}
    own = int(info.get("hwnd") or 0)
    host = int(info.get("host_hwnd") or 0)
    own_kind = _native_kind(own)
    native = fam in win32_controls.NATIVE_FAMILIES

    def has(key: str) -> bool:
        return bool(props.get(key)) if props else True  # propriétés inconnues : on essaie

    messages: list[tuple[str, Callable[[], Any]]] = []
    if native and own_kind in ("button", "checkbox", "radio"):
        kind = win32_controls.button_kind(own)
        # WinForms : BN_CLICKED est sans effet sur les cases (mesuré) → seulement pour les boutons poussoirs. Les
        # cases et boutons radio WinForms sont aussi BS_OWNERDRAW : le rôle UIA « Button » les distingue.
        pushbutton = kind in (win32_controls.BS_PUSHBUTTON, win32_controls.BS_DEFPUSHBUTTON) or (
            kind == win32_controls.BS_OWNERDRAW and role == "Button"
        )
        if fam == "Win32" or pushbutton:
            messages.append(("BN_CLICKED", lambda: win32_controls.button_click(own)))
    if native and role == "ListItem" and _native_kind(host) == "listbox" and name:
        messages.append(("LB_SETCURSEL", lambda: win32_controls.listbox_select(host, name)))
    # Option d'une liste déroulante ouverte (ComboLBox) : choix par la liste déroulante, refermée, valeur relue.
    item_combo = int(info.get("combo_hwnd") or 0) if native and role == "ListItem" else 0
    if native and role == "ListItem" and not item_combo and win32_controls.is_class(host, ("combolbox",)):
        item_combo = win32_controls.combo_owning(host, target_hwnd)
    if item_combo and name:
        messages.append(("CB_SETCURSEL", lambda: win32_controls.combo_select(item_combo, name)))
    # Liste déroulante elle-même, ou son bouton « Ouvrir » : CB_SHOWDROPDOWN (jamais l'action MSAA du bouton).
    toggle_combo = 0
    if native and not item_combo:
        if own_kind == "combo":
            toggle_combo = own
        elif role == "Button" and not own and _native_kind(host) == "combo":
            toggle_combo = host
    dropped_before = win32_controls.combo_dropped(toggle_combo) if toggle_combo else None
    if toggle_combo and dropped_before is not None:
        messages.append(
            ("CB_SHOWDROPDOWN", lambda: win32_controls.combo_show_dropdown(toggle_combo, not dropped_before))
        )
    if fam == "Win32" and role == "MenuItem" and name:
        top = win32_controls.root_of(own or host or target_hwnd) or target_hwnd
        messages.append(("WM_COMMAND menu", lambda: win32_controls.menu_command(top, name)))

    uia_chain: list[tuple[str, Callable[[], Any]]] = []
    win32_button = fam == "Win32" and own_kind in ("button", "checkbox", "radio")
    # Élément de liste hors Win32/WinForms (WPF, Chromium…) : UIA Select seul, idempotent et relu. Invoke puis Select
    # sélectionnait deux fois (banc commun du 21/10 : « liste Bravo » reçu deux fois en Electron, déclaré ✓).
    list_select = role == "ListItem" and not native and has("has_selection_item")
    if (
        has("has_invoke")
        and not win32_button
        and not (native and role == "ListItem")
        and not toggle_combo
        and not list_select
    ):
        uia_chain.append(("UIA Invoke", lambda: _invoke_with_timeout(ctrl)))
    if has("has_toggle"):
        uia_chain.append(("UIA Toggle", lambda: _UIA_TOGGLE(ctrl)))
    if has("has_selection_item") and not native:
        uia_chain.append(("UIA Select", lambda: _UIA_SELECT(ctrl)))
    if has("has_expand"):
        uia_chain.append(("UIA Expand/Collapse", lambda: _uia_expand_or_collapse(ctrl)))

    # Bouton poussoir WinForms : BN_CLICKED POSTÉ d'abord. UIA Invoke est synchrone : un bouton qui ouvre une boîte
    # modale le bloque, puis le repli BN_CLICKED rouvrait la boîte (banc commun du 21/10 : « modale ouverte » ×2).
    winforms_push = fam == "WinForms" and any(name == "BN_CLICKED" for name, _ in messages)
    if fam == "Win32" or item_combo or toggle_combo or winforms_push:
        chain = messages + uia_chain
    elif fam == "WinForms":
        chain = uia_chain + messages
    else:
        chain = uia_chain

    before = _read_state(ctrl, info)
    toggle_before = before.get("toggle")
    expand_before = before.get("expand")
    stateful_toggle = own_kind in ("checkbox", "radio") or role in ("CheckBox", "RadioButton")
    stateful_select = role in STATEFUL_SELECT_ROLES
    stateful_expand = role == "ComboBox" and expand_before is not None
    stateful = stateful_toggle or stateful_select or stateful_expand or bool(item_combo or toggle_combo)
    fingerprint = None if stateful else window_fingerprint(target_hwnd, with_tree=True)
    picker = fam == "Chromium" and opens_file_picker(role, name)
    dialogs_before = owned_dialogs(target_hwnd) if picker else set()

    def verify(_detail: Any) -> tuple[bool | None, str]:
        if picker:
            # Seule une boîte de dialogue ouverte par la fenêtre prouve le clic ; sans elle, rien ne s'est ouvert
            # (relu absent) : la suite de la chaîne, puis la vraie souris (foreground=true).
            deadline = time.monotonic() + FILE_DIALOG_S
            while True:
                fresh = owned_dialogs(target_hwnd) - dialogs_before
                if fresh:
                    return True, f"boîte de fichiers « {_window_text(min(fresh))[:40]} » ouverte"
                if time.monotonic() >= deadline:
                    return False, "aucune boîte de fichiers ouverte (Chromium exige une vraie activation)"
                time.sleep(EFFECT_POLL_S)
        if item_combo and _detail == "cb_setcursel":
            label = win32_controls.combo_selected(item_combo)
            dropped = win32_controls.combo_dropped(item_combo)
            if label is not None and " ".join(label.split()).lower() == " ".join(name.split()).lower() and not dropped:
                return True, f"option relue « {label} », liste refermée"
            return False, f"option relue « {label} »" + (", liste encore ouverte" if dropped else "")
        if toggle_combo and _detail == "cb_showdropdown":
            after = win32_controls.combo_dropped(toggle_combo)
            if after is not None and after != dropped_before:
                return True, f"liste {'ouverte' if after else 'fermée'} (relu CB_GETDROPPEDSTATE)"
            return False, "état ouvert/fermé inchangé"
        if stateful_toggle and toggle_before is not None:
            deadline = time.monotonic() + CHECK_SETTLE_S
            while True:
                after = _read_state(ctrl, info).get("toggle")
                if after is not None and after != toggle_before:
                    return True, f"coche relue ({toggle_before} → {after})"
                if time.monotonic() >= deadline:
                    # « Sans effet » seulement relu tel ; illisible = inconnu (jamais de seconde bascule à l'aveugle).
                    return (False, "coche inchangée") if after is not None else (None, "coche illisible")
                time.sleep(EFFECT_POLL_S)
        if stateful_select:
            deadline = time.monotonic() + EFFECT_WAIT_S
            while True:
                state = _read_state(ctrl, info)
                if state.get("selected") is True:
                    return True, "élément relu sélectionné"
                if _native_kind(host) == "listbox" and name and win32_controls.listbox_selected(host) == name:
                    return True, "sélection de la liste relue"
                if time.monotonic() >= deadline:
                    # Chromium publie son arbre en retard : « non sélectionné » relu n'y prouve pas l'absence d'effet
                    # (banc commun du 22/10 : UIA Select reçu, relu faux, puis clic physique = « liste Bravo » ×2).
                    if state.get("selected") is False and fam != "Chromium":
                        return False, "non sélectionné"
                    return None, "sélection non relue à temps (Chromium)" if fam == "Chromium" else ""
                time.sleep(EFFECT_POLL_S)
        if stateful_expand:
            after = _read_state(ctrl, info).get("expand")
            if after is not None and after != expand_before:
                return True, f"liste {'ouverte' if after == 1 else 'fermée'} (relu)"
            return False, "état ouvert/fermé inchangé"
        return _wait_window_effect(target_hwnd, fingerprint)

    return fam, chain, verify


def _log(action: str, method: str, hwnd: int, t0: float, result: dict[str, Any], details: dict[str, Any]) -> None:
    status = {True: "SUCCESS", False: "FAILURE", None: "UNVERIFIED"}[result.get("success")]
    computer_logger.log_action(action, method, hwnd, (time.perf_counter() - t0) * 1000, status, details)


# -----------------------------------------------------------------------------
# Input Simulation (Hardware-level via SendInput)
# -----------------------------------------------------------------------------
MOUSE_RELEASE_FLAGS = MOUSEEVENTF_LEFTUP | MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_MIDDLEUP


def _is_release(inp: INPUT) -> bool:
    """Relâchement (touche levée, bouton relâché) : toujours envoyé, même premier plan perdu (jamais de touche ni de
    bouton laissé enfoncé)."""
    if inp.type == INPUT_KEYBOARD:
        return bool(inp.union.ki.dwFlags & KEYEVENTF_KEYUP)
    if inp.type == INPUT_MOUSE:
        flags = int(inp.union.mi.dwFlags)
        return bool(flags) and not flags & ~MOUSE_RELEASE_FLAGS
    return False


def _send_inputs(inputs: list[INPUT]) -> int:
    """SendInput, cible relue au premier plan JUSTE AVANT l'envoi (relâchements exceptés) ; fenêtre d'injection notée
    pour le repli GetLastInputInfo."""
    ensure_default_desktop()
    if not all(_is_release(inp) for inp in inputs):
        _require_front("entrée physique (SendInput)")
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    with physical_input.injecting():
        return user32.SendInput(n, arr, ctypes.sizeof(INPUT))


def _move_cursor(x: int, y: int) -> None:
    """Déplacement du vrai curseur pour un geste : cible relue au premier plan d'abord."""
    _require_front("déplacement du curseur")
    user32.SetCursorPos(int(x), int(y))


def _cursor_pos() -> tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def mouse_click(
    x: int,
    y: int,
    button: str = "left",
    click_count: int = 1,
) -> bool:
    """Positions cursor and dispatches mouse click(s) at screen coordinates (x, y). Le bouton est toujours relâché."""
    ensure_default_desktop()
    _checkpoint()
    _move_cursor(x, y)
    time.sleep(0.02)

    btn = button.lower()
    down_flag = MOUSEEVENTF_LEFTDOWN
    up_flag = MOUSEEVENTF_LEFTUP
    if btn == "right":
        down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif btn == "middle":
        down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP

    for _ in range(click_count):
        _checkpoint()
        down_input = INPUT(type=INPUT_MOUSE)
        down_input.union.mi.dwFlags = down_flag
        up_input = INPUT(type=INPUT_MOUSE)
        up_input.union.mi.dwFlags = up_flag

        _send_inputs([down_input])
        try:
            time.sleep(0.02)
        finally:
            _send_inputs([up_input])
        if click_count > 1:
            time.sleep(0.05)

    return True


def mouse_move(
    x: int,
    y: int,
    hwnd: int | str | None = None,
    smooth: bool = True,
    steps: int = 12,
    duration_ms: int = 40,
    foreground: bool = False,
    coords: str = "auto",
    restore_focus: bool = True,
) -> dict[str, Any]:
    """Moves mouse cursor to coordinates (x, y) with smooth Bézier/easing trajectory.

    coords: 'auto' (default: 'screen' if hwnd is None, 'window' if hwnd is specified),
            'screen' (absolute screen coordinates across multi-monitors),
            'window' (window-relative coordinates).
    Vraie souris : passe par FocusGuard (jeton commun, attente d'une pause de Julien, arrêt d'urgence, interruption si
    Julien reprend la main). restore_focus=True remet la fenêtre active et le curseur de Julien en place à la fin ;
    False laisse le curseur sur la cible (survol persistant). `verified` : position du curseur relue sur la cible.
    """
    emergency_stop.check()
    ensure_default_desktop()
    # Vraie souris : toujours une fenêtre visée (premier plan relu) et foreground=True, jamais d'office.
    target_hwnd = resolve_window(hwnd)
    if coords == "screen":
        target_screen_x = x
        target_screen_y = y
    else:
        win_rect = get_window_rect(target_hwnd)
        target_screen_x = win_rect["left"] + x
        target_screen_y = win_rect["top"] + y

    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Déplacement de souris interdit sur {reason}.")
    _physical_gate(target_hwnd, foreground, "survol (vraie souris : aucun équivalent d'arrière-plan)")

    with FocusGuard(target_hwnd, restore=restore_focus):
        if not smooth or steps <= 1:
            _checkpoint()
            _move_cursor(target_screen_x, target_screen_y)
        else:
            start_x, start_y = _cursor_pos()
            step_delay = (duration_ms / 1000.0) / max(1, steps)
            for i in range(1, steps + 1):
                _checkpoint()
                t = i / steps
                # Smooth step ease-in-out: 3*t^2 - 2*t^3
                ease = 3 * (t**2) - 2 * (t**3)
                cur_x = int(start_x + (target_screen_x - start_x) * ease)
                cur_y = int(start_y + (target_screen_y - start_y) * ease)
                _move_cursor(cur_x, cur_y)
                time.sleep(step_delay)
        at = _cursor_pos()
        verified = abs(at[0] - target_screen_x) <= 1 and abs(at[1] - target_screen_y) <= 1

    return {
        "success": _success(verified),
        "verified": verified,
        "verified_by": "position du curseur relue",
        "target": (x, y),
        "screen_coords": (target_screen_x, target_screen_y),
        "smooth": bool(smooth and steps > 1),
        "focus_restored": restore_focus,
    }


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


def _physical_click_at(
    target_hwnd: int, sx: int, sy: int, button: str, click_count: int, restore_focus: bool, check_occlusion: bool
) -> None:
    with FocusGuard(target_hwnd, restore=restore_focus):
        if target_hwnd and check_occlusion and is_point_occluded(sx, sy, target_hwnd):
            focus_window(hwnd=target_hwnd)
        mouse_click(sx, sy, button=button, click_count=click_count)


TEXT_ROLES = ("Edit", "Document")
HIT_ROLES = (
    "Edit",
    "Document",
    "Button",
    "SplitButton",
    "CheckBox",
    "RadioButton",
    "ComboBox",
    "ListItem",
    "MenuItem",
    "TabItem",
    "Hyperlink",
    "TreeItem",
    "DataItem",
)
DESIGNATION_TTL_S = 120.0
_designated: dict[str, Any] = {}


def _node_info(node: Any) -> dict[str, Any]:
    """Propriétés d'un nœud lu en cache, au format de _element_info (type, nom, fenêtre, famille…)."""
    return {
        "type": node.control_type,
        "type_id": int(node.props.get("control_type") or 0),
        "name": node.name,
        "automation_id": str(node.props.get("automation_id") or ""),
        "hwnd": int(node.props.get("hwnd") or 0),
        "host_hwnd": int(node.host_hwnd or 0),
        "framework": node.framework,
        "class_name": str(node.props.get("class_name") or ""),
        "props": node.props,
    }


def _hit_test(target_hwnd: int, sx: int, sy: int) -> tuple[Any, dict[str, Any]] | None:
    """Élément interactif de la fenêtre cible sous le point écran (sx, sy), lu dans SON arbre UIA : marche fenêtre
    recouverte (un ElementFromPoint rendrait la fenêtre de Julien qui la couvre). Le plus petit élément l'emporte."""
    if uia_fast is None or not target_hwnd or not user32.IsWindow(target_hwnd):
        return None
    for node, info in _open_combo_items(target_hwnd):  # liste ouverte (toujours au-dessus) : prioritaire
        rect = node.rect
        if rect and rect[0] <= sx < rect[2] and rect[1] <= sy < rect[3]:
            return _wrap_element(node.element, info), info
    try:
        tree = _window_tree(target_hwnd, max_nodes=MAX_UIA_NODES, time_budget=1.5)
    except Exception:  # noqa: BLE001
        return None
    if tree.status == "failed":
        return None
    chromium = win32_controls.family(target_hwnd) == "Chromium"
    win_rect = get_window_rect(target_hwnd)
    # UIA dit « hors champ » tout contrôle WinForms d'une fenêtre recouverte ou affichée sans activation : accepté s'il
    # est dans la fenêtre, mais seulement à défaut d'un élément visible (une ligne masquée par le défilement d'une
    # liste reste dans la fenêtre et passerait devant le vrai contrôle par sa petite taille).
    best, best_area, hidden, hidden_area = None, 0, None, 0
    for node in tree.nodes[1:]:
        if node.control_type not in HIT_ROLES or (chromium and node.control_type == "Document"):
            continue
        rect = node.rect
        if rect is None or not (rect[0] <= sx < rect[2] and rect[1] <= sy < rect[3]):
            continue
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        if not node.props.get("offscreen"):
            if best is None or area < best_area:
                best, best_area = node, area
        elif not _outside(rect, win_rect) and (hidden is None or area < hidden_area):
            hidden, hidden_area = node, area
    best = best or hidden
    if best is None:
        return None
    info = _node_info(best)
    return _wrap_element(best.element, info), info


BUTTON_LABEL_MAX_WORDS = 4  # au-delà, un texte est une phrase (« Ne pas oublier d'envoyer… »), pas un bouton dessiné


def _label_at(target_hwnd: int, sx: int, sy: int) -> str:
    """Nom du plus petit élément UIA nommé (tout rôle, racine exclue) sous le point écran, s'il est court comme un
    libellé de bouton (≤ BUTTON_LABEL_MAX_WORDS mots) ; « » sinon ou si rien n'est lisible (canevas sans UIA)."""
    if uia_fast is None or not target_hwnd or not user32.IsWindow(target_hwnd):
        return ""
    try:
        tree = _window_tree(target_hwnd, max_nodes=MAX_UIA_NODES, time_budget=1.5)
    except Exception:  # noqa: BLE001
        return ""
    best, best_area = "", 0
    for node in tree.nodes[1:]:
        rect = node.rect
        if not node.name or rect is None or not (rect[0] <= sx < rect[2] and rect[1] <= sy < rect[3]):
            continue
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        if not best or area < best_area:
            best, best_area = node.name, area
    return best if len(best.split()) <= BUTTON_LABEL_MAX_WORDS else ""


def _chromium_single_line(ctrl: Any, info: dict[str, Any]) -> bool:
    """Champ <input> d'une ligne dans Chromium/Electron : UIA Value y émet les événements input (mesuré par le banc
    commun NexusWindows et NexusClaude). Jamais un champ multiligne ni un éditeur riche : indiscernables pour UIA, la
    valeur y serait posée sans que la page le sache (faux succès)."""
    if info.get("type") != "Edit" or not (info.get("props") or {}).get("has_value"):
        return False
    try:
        aria = str(getattr(ctrl, "AriaProperties", "") or "").lower()
    except Exception:  # noqa: BLE001 - propriété illisible : prudence
        return False
    return "multiline=true" not in aria


def _background_writable(ctrl: Any, info: dict[str, Any], target_hwnd: int) -> bool:
    """Champ qu'on sait remplir en arrière-plan (Edit natif, ou motif Value hors Chromium/Electron)."""
    if info.get("type") not in TEXT_ROLES:
        return False
    if info.get("type") == "Document" and _element_family(info, target_hwnd) == "Chromium":
        return False
    if _native_kind(int(info.get("hwnd") or 0)) == "edit":
        return True
    props = info.get("props") or {}
    if props.get("readonly"):
        return False
    return bool(props.get("has_value")) and (not is_electron_window(target_hwnd) or _chromium_single_line(ctrl, info))


def _designate(target_hwnd: int, ctrl: Any, info: dict[str, Any]) -> None:
    _designated.clear()
    _designated.update(hwnd=target_hwnd, ctrl=ctrl, info=dict(info), replace=False, t=time.monotonic())


def _designated_field(target_hwnd: int) -> dict[str, Any] | None:
    """Champ retenu par le dernier clic sur un champ de cette fenêtre (encore vivant), sinon None."""
    if not _designated or _designated.get("hwnd") != target_hwnd:
        return None
    if time.monotonic() - _designated["t"] > DESIGNATION_TTL_S:
        _designated.clear()
        return None
    if _read_state(_designated["ctrl"], _designated["info"]).get("exists") is False:
        _designated.clear()
        return None
    return _designated


def _describe(info: dict[str, Any]) -> str:
    name = str(info.get("name") or "").strip()
    return f"{info.get('type') or 'élément'}" + (f" « {name[:40]} »" if name else "")


def _aim_point(
    target_hwnd: int,
    hwnd: int | str | None,
    x: int | None,
    y: int | None,
    box_2d: Any,
    coords: str,
) -> tuple[int, int, str]:
    """Point écran visé par box_2d Gemini (0-1000) ou par (x, y), et le nom de la méthode de visée."""
    if box_2d is not None:
        sx, sy = resolve_box_2d_coords(box_2d, target_hwnd)
        return sx, sy, "box_2d"
    if x is None or y is None:
        raise ValueError("Indiquez un 'element_index', un 'box_2d' Gemini ou des coordonnées relatives (x, y).")
    if (coords == "screen") or (coords == "auto" and hwnd is None):
        return int(x), int(y), "screen_coordinates"
    win_rect = get_window_rect(target_hwnd)
    return win_rect["left"] + int(x), win_rect["top"] + int(y), "relative_coordinates"


def click(
    hwnd: int | str | None = None,
    element_index: int | None = None,
    x: int | None = None,
    y: int | None = None,
    box_2d: list[int] | tuple[int, int, int, int] | None = None,
    button: str = "left",
    click_count: int = 1,
    foreground: bool = False,
    restore_focus: bool = True,
    coords: str = "auto",
    confirm: bool = False,
    accord: str = "",
    approved: set[str] | None = None,
) -> dict[str, Any]:
    """Clicks an element by index [#N], Gemini box_2d [ymin, xmin, ymax, xmax], or relative coords (x, y).

    Arrière-plan d'abord, même visé par coordonnées : le point est rapporté à l'élément de la fenêtre qu'il désigne
    (arbre UIA, fenêtre recouverte comprise), puis techniques d'arrière-plan selon la famille (messages Win32, UI
    Automation), effet relu. Un clic sur un champ de saisie le RETIENT pour la saisie suivante (aucun clic envoyé).
    Vraie souris seulement en repli et avec foreground=True ; sinon refus explicite (NeedsForegroundError).
    Geste sortant (Envoyer, Payer, Publier…) : refus sans confirm=true ET accord (ConfirmationRequiredError)."""
    t0 = time.perf_counter()
    emergency_stop.check()
    ensure_default_desktop()
    target_hwnd = resolve_window(hwnd)

    # Security check: Block interaction with Windows Logon, Taskbar, or UAC elevation
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Action de clic interdite sur {reason}.")

    origin: dict[str, Any] = {}
    point: tuple[int, int] | None = None
    if element_index is not None:
        ctrl = get_cached_element(element_index, target_hwnd)
        info = _element_info.get(element_index, {}) if _cached_window_hwnd == target_hwnd else {}
    else:
        sx, sy, aim = _aim_point(target_hwnd, hwnd, x, y, box_2d, coords)
        point = (sx, sy)
        origin = {"aimed_with": aim, "screen_coords": (sx, sy)}
        if box_2d is not None:
            origin["box_2d"] = box_2d
        hit = _hit_test(target_hwnd, sx, sy)
        if hit is None:
            # Aucun contrôle interactif sous le point : le texte lu là (bouton dessiné, div web) compte quand même.
            require_confirmation(
                _label_at(target_hwnd, sx, sy),
                confirm,
                "clic par coordonnées",
                hwnd=target_hwnd,
                accord=accord,
                approved=approved,
            )
            return _physical_point_click(target_hwnd, sx, sy, aim, origin, button, click_count, restore_focus,
                                         foreground, t0)  # fmt: skip
        ctrl, info = hit
        origin["hit_test"] = _describe(info)
    require_confirmation(
        info.get("name") or getattr(ctrl, "Name", "") or "",
        confirm,
        "clic",
        str(info.get("type") or ""),
        target_hwnd,
        accord=accord,
        approved=approved,
    )
    return _click_element(target_hwnd, ctrl, info, element_index, point, origin, button, click_count, restore_focus,
                          foreground, t0)  # fmt: skip


def _physical_point_click(
    target_hwnd: int,
    sx: int,
    sy: int,
    aim: str,
    origin: dict[str, Any],
    button: str,
    click_count: int,
    restore_focus: bool,
    foreground: bool,
    t0: float,
) -> dict[str, Any]:
    """Point sans élément connu (canevas, application sans UIA) : clic par messages en Win32/WinForms (recette
    commune du banc NexusWindows, premier plan intact), sinon vraie souris, en repli autorisé seulement."""
    if win32_controls.family(target_hwnd) in win32_controls.MESSAGE_CLICK_FAMILIES:
        before = window_fingerprint(target_hwnd, with_tree=True)
        try:
            hit = win32_controls.post_click(target_hwnd, sx, sy, button, click_count)
        except win32_controls.PartialSendError:
            hit = -1  # envoi partiel : issue inconnue, relue ci-dessous, jamais de vraie souris par-dessus
        except win32_controls.MessageError:
            hit = 0
        if hit:
            # Envoyé : jamais renvoyé par la vraie souris (un effet lent serait doublé), même non relu.
            verified, how = _wait_window_effect(
                target_hwnd, before, structural_only=click_count > 1 or button != "left"
            )
            result = {"success": _success(verified), "method": "win32_post_click", "technique": "clic par messages",
                      "physical": False, **origin, "verified": verified,
                      "timing_ms": round((time.perf_counter() - t0) * 1000, 2)}  # fmt: skip
            if how:
                result["verified_by"] = how
            _log("click", "win32_post_click", target_hwnd, t0, result, {"screen_coords": (sx, sy)})
            return result
    if win32_controls.family(target_hwnd) == "Tk":
        # Tk (canevas, boutons dessinés) : clic ENVOYÉ avec le bouton simulé pour son seul fil (recette de NexusClaude
        # du 23/10). Envoyé, même en partie : jamais de vraie souris par-dessus.
        before = window_fingerprint(target_hwnd, with_tree=True)
        top = win32_controls.root_of(target_hwnd) or target_hwnd
        sent, partial = True, False
        try:
            win32_controls.tk_click(top, sx, sy, button, click_count, check=emergency_stop.check)
        except win32_controls.PartialSendError:
            partial = True  # issue inconnue : jamais promue en succès par une empreinte changée
        except win32_controls.MessageError:
            sent = False
        if sent:
            verified, how = _wait_window_effect(
                target_hwnd, before, structural_only=click_count > 1 or button != "left"
            )
            if partial:
                verified, how = None, "envoi partiel : issue inconnue, vérifier l'image"
            result = {"success": _success(verified), "method": "tk_held_click", "partial": partial,
                      "technique": "clic envoyé, bouton simulé pour le fil de Tk", "physical": False, **origin,
                      "verified": verified, "timing_ms": round((time.perf_counter() - t0) * 1000, 2)}  # fmt: skip
            if how:
                result["verified_by"] = how
            _log("click", "tk_held_click", target_hwnd, t0, result, {"screen_coords": (sx, sy)})
            return result
    _physical_gate(target_hwnd, foreground, "clic par coordonnées sur une zone sans élément UI Automation")
    before = window_fingerprint(target_hwnd, with_tree=True)
    _physical_click_at(target_hwnd, sx, sy, button, click_count, restore_focus, aim != "screen_coordinates")
    verified, how = _wait_window_effect(target_hwnd, before)
    result = {
        "success": _success(verified),
        "method": aim,
        "physical": True,
        **origin,
        "verified": verified,
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
        "focus_restored": restore_focus,
    }
    if how:
        result["verified_by"] = how
    _log("click", aim, target_hwnd, t0, result, {"screen_coords": (sx, sy)})
    return result


def _click_element(
    target_hwnd: int,
    ctrl: Any,
    info: dict[str, Any],
    element_index: int | None,
    point: tuple[int, int] | None,
    origin: dict[str, Any],
    button: str,
    click_count: int,
    restore_focus: bool,
    foreground: bool,
    t0: float,
) -> dict[str, Any]:
    left_single = button.lower() == "left" and click_count == 1
    base: dict[str, Any] = dict(origin)
    if element_index is not None:
        base["element_index"] = element_index
    details = {"element_index": element_index} if element_index is not None else {"target": _describe(info)}

    if left_single and _background_writable(ctrl, info, target_hwnd):
        _designate(target_hwnd, ctrl, info)
        result: dict[str, Any] = {
            "success": True,
            "verified": True,
            "method": "field_designation",
            "technique": "champ retenu",
            "family": _element_family(info, target_hwnd),
            **base,
            "verified_by": "champ retenu : la saisie suivante sans cible ira dans ce champ, en arrière-plan "
            "(aucun clic envoyé)",
            "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
        _log("click", "field_designation", target_hwnd, t0, result, details)
        return result

    if not left_single and win32_controls.family(target_hwnd) in win32_controls.MESSAGE_MOUSE_FAMILIES:
        # Clic droit et double clic en Win32/WinForms : messages postés au centre de l'élément (recette commune du
        # banc NexusWindows : le menu contextuel WinForms s'ouvre sans toucher au premier plan, sa commande se choisit
        # ensuite par libellé). Envoyé une fois : jamais renvoyé par la vraie souris.
        try:
            r = ctrl.BoundingRectangle
            cx, cy = point or ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
            before = window_fingerprint(target_hwnd, with_tree=True)
            try:
                win32_controls.post_click(target_hwnd, cx, cy, button.lower(), click_count)
            except win32_controls.PartialSendError:
                pass  # envoi partiel : issue inconnue, relue ci-dessous, jamais d'autre technique par-dessus
        except (win32_controls.MessageError, AttributeError):
            pass
        else:
            # double clic / clic droit : la sélection ou le focus nés du premier clic ne prouvent rien
            verified, how = _wait_window_effect(target_hwnd, before, structural_only=True)
            posted = {"success": _success(verified), "verified": verified, "method": "win32_post_click",
                      "technique": "clic par messages", "physical": False, **base,
                      "timing_ms": round((time.perf_counter() - t0) * 1000, 2)}  # fmt: skip
            if how:
                posted["verified_by"] = how
            _log("click", "win32_post_click", target_hwnd, t0, posted, details)
            return posted

    fam, chain, verify = _click_plan(ctrl, info, target_hwnd)
    base["family"] = fam
    tried: list[dict[str, str]] = []
    if left_single:
        out = _run_chain(chain, verify, user32.GetForegroundWindow())
        tried = out["tried"]
        if out["technique"]:
            result = {
                "success": _success(out["verified"]),
                "method": _method_slug(out["technique"]),
                "technique": out["technique"],
                **base,
                "verified": out["verified"],
                "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
            }
            for key in ("verified_by", "already", "focus_stolen_restored", "pending"):
                if out.get(key):
                    result[key] = out[key]
            if out["verified"] is True and info.get("list_owner") is not None:
                closed = _collapse_owner(info)
                if closed is not None:
                    result["list_closed"] = closed
            if tried:
                result["techniques_tried"] = tried
            if out.get("pending"):
                result["message"] = (
                    f"Invoke envoyé sans retour après {INVOKE_TIMEOUT_S:g} s (souvent une fenêtre modale "
                    "ouverte) : aucun clic physique enchaîné pour éviter une double activation. "
                    "Relire l'état (look) avant de poursuivre."
                )
            elif out["verified"] is None:
                result["message"] = "Commande envoyée sans effet visible relu : vérifier sur l'image."
            _log("click", result["method"], target_hwnd, t0, result, details)
            return result

    # Aucune technique d'arrière-plan applicable : vraie souris, en repli autorisé seulement.
    what = f"clic sur {_describe(info)}"
    if not left_single:
        what = f"{'double-clic' if click_count > 1 else 'clic ' + button.lower()} sur {_describe(info)} (aucun équivalent d'arrière-plan : vraie souris seulement)"
    if tried:
        what += " (" + "; ".join(f"{t['technique']} : {t['error']}" for t in tried)[:200] + ")"
    _physical_gate(target_hwnd, foreground, what)
    if point is None:
        rect = ctrl.BoundingRectangle
        point = ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
    cx, cy = point
    _physical_click_at(target_hwnd, cx, cy, button, click_count, restore_focus, True)
    verified, how = verify("physical")
    result = {
        "success": _success(verified),
        "method": "element_center" if element_index is not None or not origin else origin.get("aimed_with"),
        "physical": True,
        **base,
        "coords": (cx, cy),
        "verified": verified,
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
        "focus_restored": restore_focus,
    }
    if how:
        result["verified_by"] = how
    if tried:
        result["techniques_tried"] = tried
        invoke_error = next((t["error"] for t in tried if t["technique"] == "UIA Invoke"), None)
        if invoke_error:
            result["invoke_error"] = invoke_error  # Invoke refusé d'emblée : clic physique de repli
    _log("click", result["method"], target_hwnd, t0, result, {**details, "coords": (cx, cy)})
    return result


def _collapse_owner(info: dict[str, Any]) -> bool | None:
    """Option UIA choisie : sa liste déroulante, si elle est restée ouverte, est refermée (relu). None : sans objet."""
    try:
        owner = _wrap_element(info["list_owner"], {"type_id": 50003})  # ComboBox
        pattern = owner.GetExpandCollapsePattern()
        if not pattern or getattr(pattern, "ExpandCollapseState", 0) != 1:
            return None
        pattern.Collapse()
        return getattr(owner.GetExpandCollapsePattern(), "ExpandCollapseState", 1) == 0
    except Exception:  # noqa: BLE001 - liste disparue avec le choix : rien à refermer
        return None


def _method_slug(technique: str) -> str:
    return {
        "BN_CLICKED": "win32_bn_clicked",
        "LB_SETCURSEL": "win32_lb_setcursel",
        "CB_SETCURSEL": "win32_cb_setcursel",
        "CB_SHOWDROPDOWN": "win32_cb_showdropdown",
        "WM_COMMAND menu": "win32_menu_command",
        "BM_SETCHECK": "win32_bm_setcheck",
        "EM_REPLACESEL": "win32_em_replacesel",
        "UIA Invoke": "uia_invoke",
        "UIA Toggle": "uia_toggle",
        "UIA Select": "uia_select",
        "UIA Expand/Collapse": "uia_expand_collapse",
        "UIA Value": "uia_set_value",
    }.get(technique, technique.lower().replace(" ", "_"))


def _focused_props() -> dict[str, Any] | None:
    """Propriétés de l'élément qui a le focus clavier (UIA, un aller-retour), None si illisible."""
    if uia_fast is None:
        return None
    try:
        reader = uia_fast.reader()
        element = reader.uia.GetFocusedElementBuildCache(reader.cache_one)
        return reader.props(element)
    except Exception:  # noqa: BLE001
        return None


def _focused_is_password() -> bool:
    """Le champ qui a le focus (juste avant une vraie frappe) est-il un champ mot de passe ?"""
    props = _focused_props()
    if not props:
        return False
    type_name = _fast().control_type_name(props.get("control_type")) if uia_fast is not None else ""
    info = {"type": type_name, "name": props.get("name"), "hwnd": int(props.get("hwnd") or 0), "props": props}
    return is_password_field(info)


def _focused_value() -> str | None:
    """Valeur de l'élément qui a le focus clavier, pour relire une frappe physique avant de rendre le premier plan.
    None si illisible (ou champ mot de passe)."""
    props = _focused_props()
    value = None if props is None else props.get("value")
    return None if value is None else _norm_text(value)


def _same_text(read: Any, expected: Any) -> bool:
    """Égalité du texte relu et du texte voulu, espaces normalisés (jamais une simple inclusion)."""
    return " ".join(_norm_text(read).split()) == " ".join(_norm_text(expected).split())


def _text_matches(read: str | None, expected: str) -> bool | None:
    """Vrai si le texte relu est EXACTEMENT celui voulu (espaces normalisés), None si illisible. « Julien » relu
    « Alice Martin » est faux."""
    if read is None:
        return None
    return _same_text(read, expected)


def _text_plan(
    ctrl: Any,
    info: dict[str, Any],
    target_hwnd: int,
    text: str,
    clear_first: bool,
    method: str,
    secret: bool = False,
) -> tuple[str, list[tuple[str, Callable[[], Any]]], Callable[[Any], tuple[bool | None, str]], str]:
    """Techniques d'arrière-plan pour remplacer/compléter le texte d'un champ, et sa relecture. secret=True (champ
    mot de passe) : valeur masquée, un texte relu différent n'est jamais un échec (inconnu, la chaîne s'arrête)."""
    fam = _element_family(info, target_hwnd)
    own = int(info.get("hwnd") or 0)
    is_edit = _native_kind(own) == "edit"
    before = _read_state(ctrl, info).get("value")
    before_text = _norm_text(before)
    expected = text if clear_first else before_text + text

    def uia_value() -> str:
        pattern = ctrl.GetValuePattern()
        if not pattern:
            raise LookupError("Motif Value absent.")
        if getattr(pattern, "IsReadOnly", False):
            raise PermissionError("Champ en lecture seule.")
        pattern.SetValue(expected)
        return "uia"

    message: tuple[str, Callable[[], Any]] = (
        "EM_REPLACESEL",
        lambda: win32_controls.edit_set_text(own, text, append=not clear_first),
    )
    uia_tech: tuple[str, Callable[[], Any]] = ("UIA Value", uia_value)
    chain: list[tuple[str, Callable[[], Any]]]
    if method == "uia":
        chain = [uia_tech]
    elif method == "message":
        chain = [message] if is_edit else []
    elif fam == "Win32":
        chain = [message, uia_tech] if is_edit else [uia_tech]
    elif fam == "WinForms":
        chain = [uia_tech, message] if is_edit else [uia_tech]
    else:
        chain = [uia_tech]

    def verify(_detail: Any) -> tuple[bool | None, str]:
        deadline = time.monotonic() + EFFECT_WAIT_S
        while True:
            read = _read_state(ctrl, info).get("value")
            ok = _text_matches(read, expected)
            if ok:
                return True, "valeur relue"
            if secret:  # valeur masquée (illisible d'un autre processus) : jamais « sans effet », jamais relue
                return None, ""
            if time.monotonic() >= deadline:
                if ok is None:
                    return None, ""
                return False, ("partial" if _norm_text(read) != before_text else "valeur inchangée")
            time.sleep(EFFECT_POLL_S)

    return fam, chain, verify, expected


PASTE_MIN_CHARS = 300  # repli physique : frappe Unicode jusqu'ici, presse-papiers au-delà (ou texte multiligne)


def type_text(
    text: str,
    hwnd: int | str | None = None,
    element_index: int | None = None,
    x: int | None = None,
    y: int | None = None,
    box_2d: list[int] | tuple[int, int, int, int] | None = None,
    clear_first: bool = False,
    submit: bool = False,
    method: str = "auto",
    foreground: bool = False,
    restore_clipboard: bool = True,
    restore_focus: bool = True,
    confirm: bool = False,
    accord: str = "",
    approved: set[str] | None = None,
) -> dict[str, Any]:
    """Saisit du texte, en arrière-plan d'abord, valeur relue (égalité exacte, espaces normalisés). Champ mot de
    passe : rempli comme les autres (contenu remplacé), valeur masquée jamais relue ni rendue (effet ~ à vérifier).

    Champ visé par element_index, par box_2d / (x, y) (rapportés au champ sous le point), ou — sans cible — le champ
    RETENU par le dernier clic sur un champ de la fenêtre (un Ctrl+A envoyé entre les deux fait remplacer le texte).

    Modes :
    - 'auto' (défaut) : techniques d'arrière-plan selon la famille (Win32 : EM_REPLACESEL puis UIA Value ; WinForms :
      UIA Value puis EM_REPLACESEL ; WPF/UWP : UIA Value), valeur relue. Repli physique seulement si foreground=True :
      frappe Unicode (SendInput), presse-papiers en DERNIER recours (texte multiligne ou de plus de 300 caractères).
    - 'uia' / 'message' : forcer UI Automation ValuePattern / EM_REPLACESEL (jamais de repli physique).
    - 'paste' : collage presse-papiers (Ctrl+V), presse-papiers de Julien restauré (restore_clipboard=True).
    - 'typing' : frappe caractère par caractère via SendInput Unicode (interrompue si Julien reprend la main).
    submit=True : Entrée après la saisie ; restore_focus=True : premier plan et curseur rendus à Julien.
    Entrée (submit, ou retour à la ligne tapé) qui déclencherait « Envoyer », « Payer »… : refus avant toute saisie
    sans confirm=true et accord éventuel (ConfirmationRequiredError), comme le clic.
    """
    t0 = time.perf_counter()
    emergency_stop.check()
    ensure_default_desktop()
    target_hwnd = resolve_window(hwnd)
    if approved is None:
        approved = set()

    # Security check: Block typing into critical Windows auth/system surfaces
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Saisie de texte interdite sur {reason}.")

    # Normalize newlines so Windows \r\n does not duplicate
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    ctrl: Any = None
    info: dict[str, Any] = {}
    source = ""
    designated = None
    point: tuple[int, int] | None = None
    if element_index is not None:
        ctrl = get_cached_element(element_index, target_hwnd)
        info = _element_info.get(element_index, {}) if _cached_window_hwnd == target_hwnd else {}
        source = "element_index"
    elif box_2d is not None or (x is not None and y is not None):
        sx, sy, _aim = _aim_point(target_hwnd, target_hwnd, x, y, box_2d, "window")
        point = (sx, sy)
        hit = _hit_test(target_hwnd, sx, sy)
        if hit is not None and hit[1].get("type") in TEXT_ROLES:
            ctrl, info = hit
            source = "point"
    else:
        designated = _designated_field(target_hwnd)
        if designated is not None:
            ctrl, info = designated["ctrl"], designated["info"]
            clear_first = clear_first or bool(designated.get("replace"))
            source = "champ retenu"
    if submit:  # avant toute saisie : rien n'est tapé si Entrée doit être confirmée
        require_key_confirmation(
            target_hwnd, "enter", confirm, (ctrl, info) if ctrl is not None else None, accord=accord, approved=approved
        )
    secret = ctrl is not None and is_password_field(info)
    if secret:
        clear_first = True  # valeur masquée : on ne sait pas ce qu'elle contient, jamais d'ajout à l'aveugle

    # 1. Arrière-plan : messages Win32 / UIA Value selon la famille, valeur relue (aucun vol de focus)
    tried: list[dict[str, str]] = []
    if ctrl is not None and (
        method in ("uia", "message")
        or (method == "auto" and (not is_electron_window(target_hwnd) or _chromium_single_line(ctrl, info)))
    ):
        fam, chain, verify, expected = _text_plan(ctrl, info, target_hwnd, text, clear_first, method, secret)
        out = _run_chain(chain, verify, user32.GetForegroundWindow())
        tried = out["tried"]
        if out["technique"]:
            if designated is not None:
                designated["replace"] = False
            result: dict[str, Any] = {
                "success": _success(out["verified"]),
                "method": _method_slug(out["technique"]),
                "technique": out["technique"],
                "family": fam,
                "target": _describe(info),
                "char_count": len(text),
                "verified": out["verified"],
            }
            if secret:
                result["note"] = PASSWORD_NOTE
            else:
                result["current_value"] = _read_state(ctrl, info).get("value")
            if element_index is not None:
                result["element_index"] = element_index
            if source != "element_index":
                result["field_from"] = source
            if out.get("verified_by"):
                result["verified_by"] = out["verified_by"]
            if out["tried"]:
                result["techniques_tried"] = out["tried"]
            if out.get("focus_stolen_restored"):
                result["focus_stolen_restored"] = True
            if submit and out["verified"] is not False:
                try:
                    key = press_key(
                        "enter",
                        hwnd=target_hwnd,
                        foreground=foreground,
                        restore_focus=restore_focus,
                        verify=False,
                        field=(ctrl, info),
                        confirm=True,
                        accord=accord,
                        approved=approved,
                    )
                except NeedsForegroundError as error:
                    raise NeedsForegroundError(
                        f"Texte saisi et relu, mais Entrée non envoyée : {error}",
                        what=f"texte saisi et relu, mais Entrée non envoyée ({error.what})",
                    ) from error
                result["submit"] = True
                result["submit_method"] = key.get("method", "sendinput_enter")
                result["submit_sent"] = bool(key.get("sent"))
            result["timing_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            _log("type_text", result["method"], target_hwnd, t0, result, {"target": result["target"]})
            return result
        if method in ("uia", "message"):
            errors = "; ".join(f"{t['technique']} : {t['error']}" for t in out["tried"]) or "aucune technique"
            raise RuntimeError(f"L'élément {_describe(info)} ne prend pas la saisie en arrière-plan ({errors}).")

    # 1 bis. Chromium (éditeur riche, champ multiligne) : frappe sous activation simulée (recette commune), en ajout
    # seulement (remplacer exigerait une sélection préalable). Envoyé une fois, jamais renvoyé par le vrai clavier.
    if (
        ctrl is not None
        and not secret
        and not submit
        and "\n" not in text
        and "\r" not in text
        and method == "auto"
        and win32_controls.is_chromium_top(win32_controls.root_of(target_hwnd) or target_hwnd)
    ):
        before_value = _norm_text(_read_state(ctrl, info).get("value"))
        if not clear_first or not before_value:
            wanted = _norm_text(before_value + text)
            try:
                done = _chromium_simulated_typing(
                    target_hwnd,
                    ctrl,
                    text,
                    lambda: _norm_text(_read_state(ctrl, info).get("value")) == wanted,
                    caret_to_end=bool(before_value),
                )
            except win32_controls.PartialSendError as error:
                # Une partie est partie : issue inconnue, rendue telle quelle ; jamais de repli physique par-dessus.
                partial: dict[str, Any] = {
                    "success": None, "method": "chromium_simulated_typing", "verified": None,
                    "technique": "frappe sans activation (activation simulée)", "family": "Chromium",
                    "target": _describe(info), "message": f"Envoi partiel : {error}. Regarder avant toute reprise.",
                    "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
                }  # fmt: skip
                _log("type_text", "chromium_simulated_typing", target_hwnd, t0, partial, {"target": _describe(info)})
                return partial
            except win32_controls.MessageError as error:
                tried.append({"technique": "frappe sans activation", "error": str(error)})
            else:
                sim_result: dict[str, Any] = {
                    "success": _success(done), "method": "chromium_simulated_typing",
                    "technique": "frappe sans activation (activation simulée)", "family": "Chromium",
                    "target": _describe(info), "char_count": len(text), "verified": done,
                    "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
                }  # fmt: skip
                if done:
                    sim_result["verified_by"] = "texte relu dans le champ"
                _log("type_text", "chromium_simulated_typing", target_hwnd, t0, sim_result, {"target": _describe(info)})
                return sim_result

    # 2. Repli physique (foreground=True seulement) : frappe Unicode, presse-papiers en dernier recours
    what = f"saisie dans {_describe(info)}" if ctrl is not None else "saisie sans champ connu (aucun champ retenu)"
    if tried:
        what += " (" + "; ".join(f"{t['technique']} : {t['error']}" for t in tried)[:200] + ")"
    _physical_gate(target_hwnd, foreground, what)
    if method not in ("paste", "typing"):
        method = "paste" if ("\n" in text or len(text) > PASTE_MIN_CHARS) else "typing"
    if method == "typing" and "\n" in text and not submit:  # chaque retour à la ligne tapé est une vraie Entrée
        # Le résumé (refus, accord) nomme le champ où part le saut de ligne, pas seulement ce qu'il déclencherait.
        field_name = str(info.get("name") or "").strip()[:40] if ctrl is not None else ""
        require_key_confirmation(
            target_hwnd, "enter", confirm, (ctrl, info) if ctrl is not None else None, accord=accord,
            approved=approved,
            gesture=f"saut de ligne tapé dans « {field_name} »" if field_name else "saut de ligne tapé dans le champ",
        )  # fmt: skip
    if point is None and ctrl is not None:
        crect = ctrl.BoundingRectangle
        point = ((crect.left + crect.right) // 2, (crect.top + crect.bottom) // 2)
    value_before = _read_state(ctrl, info).get("value") if ctrl is not None else None
    clipboard_note = ""
    snapshot: ClipboardSnapshot | None = None
    if method == "paste" and restore_clipboard:
        # Presse-papiers de Julien sauvé en entier ; s'il ne peut pas l'être (image GDI, verrou), pas de collage.
        snapshot = clipboard_snapshot()
        if not snapshot.complete:
            clipboard_note = f"presse-papiers de Julien non sauvable ({snapshot.reason}) : frappe au lieu du collage"
            snapshot = None
            method = "typing"

    def note_if_password() -> None:
        """Juste avant la vraie frappe : champ mot de passe au focus → valeur jamais relue (masquée)."""
        nonlocal secret
        secret = secret or _focused_is_password()

    if method == "paste":
        focused_read: str | None = None
        try:
            with FocusGuard(target_hwnd, restore=restore_focus):
                if point is not None:
                    mouse_click(*point)
                    time.sleep(0.02)
                _checkpoint()
                note_if_password()
                if clear_first:
                    press_key("ctrl+a", hwnd=target_hwnd, foreground=True, verify=False, background=False)
                    press_key("backspace", hwnd=target_hwnd, foreground=True, verify=False, background=False)
                    time.sleep(0.01)

                # Strict clipboard set verification (Eliminates Codex's 'échec du presse-papier ignoré')
                clip_ok = set_clipboard_text(text)
                if not clip_ok:
                    raise RuntimeError(
                        "Échec de mise à jour du presse-papier Windows (verrouillé par une autre application). "
                        "Collage annulé afin d'éviter l'injection de données périmées ou corrompues."
                    )

                _checkpoint()
                press_key("ctrl+v", hwnd=target_hwnd, foreground=True, verify=False, background=False)

                # Give application message pump brief moment to consume clipboard data before restoring
                time.sleep(0.06)
                focused_read = _focused_value()  # relu avant de rendre le premier plan

                if submit:
                    _checkpoint()
                    press_key("enter", hwnd=target_hwnd, foreground=True, verify=False, background=False, confirm=True)
        finally:
            # Presse-papiers de Julien rendu à l'identique, même en cas d'erreur (vide s'il était vide).
            if snapshot is not None:
                clipboard_restore(snapshot)
        physical_method = "clipboard_paste"
    else:
        focused_read = None
        with FocusGuard(target_hwnd, restore=restore_focus):
            if point is not None:
                mouse_click(*point)
                time.sleep(0.02)
            note_if_password()
            if clear_first:
                press_key("ctrl+a", hwnd=target_hwnd, foreground=True, verify=False, background=False)
                press_key("backspace", hwnd=target_hwnd, foreground=True, verify=False, background=False)

            for char in text:
                _checkpoint()  # à chaque caractère : arrêt d'urgence ou reprise en main par Julien
                if char == "\n":
                    press_key("enter", hwnd=target_hwnd, foreground=True, verify=False, background=False, confirm=True)
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

            time.sleep(0.03)
            focused_read = _focused_value()
            if submit:
                time.sleep(0.02)
                press_key("enter", hwnd=target_hwnd, foreground=True, verify=False, background=False, confirm=True)
        physical_method = "sendinput_unicode"

    # Postcondition EXACTE : valeur du champ visé (texte d'avant + saisie, ou saisie seule après effacement), sinon
    # celle du champ qui avait le focus quand le champ a été vidé d'abord ; sinon inconnue, jamais « contient ».
    verified = None
    expected_value = text if clear_first else (None if value_before is None else _norm_text(value_before) + text)
    if ctrl is not None and expected_value is not None:
        read_val = _read_state(ctrl, info).get("value")
        if read_val is not None:
            verified = _text_matches(read_val, expected_value)
    if verified is None and focused_read is not None and clear_first:
        verified = _text_matches(focused_read, text)
    if secret and verified is not True:
        verified = None  # valeur masquée : un texte relu vide ou différent ne prouve rien

    result = {
        "success": _success(verified),
        "method": physical_method,
        "physical": True,
        "char_count": len(text),
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
        "submit": submit,
        "verified": verified,
        "focus_restored": restore_focus,
    }
    if ctrl is not None:
        result["target"] = _describe(info)
    if clipboard_note:
        result["clipboard"] = clipboard_note
    if secret:
        result["note"] = PASSWORD_NOTE
    if verified is None:
        result["message"] = "Texte envoyé sans valeur relisible exactement : vérifier sur l'image."
    _log("type_text", physical_method, target_hwnd, t0, result, {"char_count": len(text), "submit": submit})
    return result


KEY_MESSAGE_FAMILIES = {"Win32", "WinForms", "WPF"}  # touches simples postées lues (mesuré par NexusClaude)
NO_KEYBOARD_BACKGROUND = {
    "UWP": "UWP/WinUI ignore les touches envoyées en arrière-plan (mesuré)",
    "WinUI": "UWP/WinUI ignore les touches envoyées en arrière-plan (mesuré)",
    "Chromium": "Chromium/Electron ignore le clavier d'une fenêtre inactive (mesuré)",
    "Firefox": "Firefox ignore le clavier d'une fenêtre inactive",
    "Tk": "Tk ignore les touches envoyées par messages (mesuré)",
}


def _key_entries(parts: list[str]) -> list[tuple[int, bool]]:
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
    return vk_entries


def _select_all_text_pattern(ctrl: Any) -> bool:
    """Ctrl+A d'un champ UIA sans focus : tout le texte sélectionné par TextPattern, sélection RELUE (vrai seulement
    si elle couvre tout le texte)."""
    try:
        pattern = ctrl.GetTextPattern()
        if not pattern:
            return False
        document = pattern.DocumentRange
        whole = document.GetText(-1)
        document.Select()
        ranges = pattern.GetSelection() or []
        selected = "".join(str(r.GetText(-1)) for r in ranges)
        return isinstance(whole, str) and bool(ranges) and selected == whole
    except Exception:  # noqa: BLE001 - motif absent ou refusé : sélection non prouvée
        return False


def _background_keys(
    target_hwnd: int, keys: str, parts: list[str], vk_entries: list[tuple[int, bool]], field: Any
) -> dict[str, Any] | None:
    """Touches en arrière-plan : raccourcis d'édition du champ retenu (Ctrl+A, Ctrl+V, Effacer après Ctrl+A) traduits
    en techniques d'arrière-plan relues ; touche simple postée (WM_KEYDOWN/UP) en Win32, WinForms et WPF. None si
    rien ne s'applique (le repli physique décide)."""
    combo = "+".join("ctrl" if p == "control" else p for p in parts)
    designated = _designated_field(target_hwnd)
    if field is None and designated is not None:
        field = (designated["ctrl"], designated["info"])
    mods = [p for p in parts if p in MODIFIER_NAMES]
    main = [p for p in parts if p not in MODIFIER_NAMES]

    if combo == "ctrl+a" and field is not None:
        ctrl, info = field
        if designated is not None and ctrl is designated["ctrl"]:
            designated["replace"] = True
        own = int(info.get("hwnd") or 0)
        method = "field_select_all"
        verified: bool | None = None
        how = "sélection notée (la saisie suivante remplacera le texte du champ), sélection réelle non relue"
        if _native_kind(own) == "edit":
            try:
                win32_controls.edit_select_all(own)
                method, how, verified = "win32_em_setsel", "texte du champ sélectionné (EM_GETSEL relu)", True
            except win32_controls.MessageError:
                pass
        elif _select_all_text_pattern(ctrl):
            method, how, verified = "uia_text_select", "texte du champ sélectionné (TextPattern relu)", True
        return {"success": _success(verified), "verified": verified, "method": method, "verified_by": how,
                "keys": keys, "target": _describe(info), "sent": True}  # fmt: skip
    edit_text = None
    if combo in ("backspace", "delete") and designated is not None and designated.get("replace"):
        edit_text = ""
    elif combo == "ctrl+v" and designated is not None:
        edit_text = get_clipboard_text()  # coller = écrire le contenu du presse-papiers, sans y toucher
    if edit_text is not None:
        try:
            with _no_physical():
                res = type_text(edit_text, hwnd=target_hwnd, method="auto", foreground=False)
        except NeedsForegroundError:
            return None
        res.update(keys=keys, sent=True)
        if combo == "ctrl+v":
            res["pasted_from_clipboard"] = True
        return res

    fam = win32_controls.family(target_hwnd)
    top = win32_controls.root_of(target_hwnd) or target_hwnd
    if len(main) == 1 and win32_controls.is_chromium_top(top):
        # Chromium : touche ou raccourci sous activation simulée (recette commune ; Ctrl tenu le temps que Chromium
        # occulté lise l'état clavier). Envoyé une fois, jamais renvoyé par le vrai clavier.
        before = window_fingerprint(target_hwnd, with_tree=True)
        mod_vks = [vk for vk, _ext in vk_entries[:-1]]
        front = int(user32.GetForegroundWindow() or 0)
        try:
            with win32_controls.simulated_activation(top):
                _settle_first_activation(top, front)
                if mod_vks:
                    method = win32_controls.post_shortcut(top, vk_entries[-1][0], mod_vks,
                                                          win32_controls.SIM_MODIFIERS_HOLD_S)  # fmt: skip
                else:
                    method = win32_controls.post_key(top, vk_entries[-1][0])
        except win32_controls.PartialSendError:
            method = "envoi partiel"  # issue inconnue, relue ci-dessous, jamais le vrai clavier par-dessus
        except win32_controls.MessageError:
            return None
        finally:
            _give_back_after_simulation(top, front)
        verified, how = _wait_window_effect(target_hwnd, before)
        chromium_keys: dict[str, Any] = {"success": _success(verified), "verified": verified, "method": method,
                                         "technique": "touches sans activation (activation simulée)", "keys": keys,
                                         "sent": True}  # fmt: skip
        if how:
            chromium_keys["verified_by"] = how
        return chromium_keys
    if fam == "Tk" and len(main) == 1 and field is None:
        # Tk : touche ou raccourci par focus simulé (WM_SETFOCUS envoyé, jamais WM_ACTIVATE ; recette de NexusClaude du
        # 23/10). Envoyé, même en partie : jamais le vrai clavier par-dessus.
        mod_vks = [vk for vk, _ext in vk_entries[:-1]]
        before = window_fingerprint(target_hwnd, with_tree=True)
        top = win32_controls.root_of(target_hwnd) or target_hwnd
        partial = False
        try:
            method = win32_controls.tk_keys(top, vk_entries[-1][0], mod_vks, check=emergency_stop.check)
        except win32_controls.PartialSendError:
            method, partial = "envoi partiel", True
        except win32_controls.MessageError:
            return None
        verified, how = _wait_window_effect(target_hwnd, before)
        if partial:  # issue inconnue : jamais promue en succès par une empreinte changée
            verified, how = None, "envoi partiel : issue inconnue, vérifier l'image"
        tk_result: dict[str, Any] = {"success": _success(verified), "verified": verified, "method": method,
                                     "partial": partial,
                                     "technique": "touches par focus simulé (Tk)", "keys": keys, "sent": True}  # fmt: skip
        if how:
            tk_result["verified_by"] = how
        return tk_result
    if mods and len(main) == 1 and fam in win32_controls.MESSAGE_SHORTCUT_FAMILIES:
        # Raccourci Ctrl/Alt/Maj : état clavier du fil cible simulé (recette commune du banc NexusWindows).
        mod_vks = [vk for vk, _ext in vk_entries[:-1]]
        target = win32_controls.keyboard_target(target_hwnd)
        before = window_fingerprint(target_hwnd, with_tree=True)
        try:
            method = win32_controls.post_shortcut(target, vk_entries[-1][0], mod_vks)
        except win32_controls.PartialSendError:
            method = "envoi partiel"  # issue inconnue, relue ci-dessous, jamais le vrai clavier par-dessus
        except win32_controls.MessageError:
            return None
        verified, how = _wait_window_effect(target_hwnd, before)
        shortcut: dict[str, Any] = {"success": _success(verified), "verified": verified, "method": method,
                                    "technique": "raccourci par messages", "keys": keys, "sent": True}  # fmt: skip
        if how:
            shortcut["verified_by"] = how
        return shortcut
    if mods or len(main) != 1 or fam not in KEY_MESSAGE_FAMILIES:
        return None
    vk = vk_entries[-1][0]
    target = 0
    value_before = None
    if field is not None:
        ctrl, info = field
        target = int(info.get("hwnd") or 0)
        value_before = _read_state(ctrl, info).get("value")
    if not target:
        target = target_hwnd if fam == "WPF" else win32_controls.keyboard_target(target_hwnd)
    before = window_fingerprint(target_hwnd, with_tree=True)
    try:
        win32_controls.post_key(target, vk)
    except win32_controls.MessageError:
        return None
    verified, how = _wait_window_effect(target_hwnd, before)
    if not verified and field is not None:
        after = _read_state(field[0], field[1]).get("value")
        if after is not None and after != value_before:
            verified, how = True, "valeur du champ changée"
    result: dict[str, Any] = {
        "success": _success(verified),
        "method": "win32_post_key",
        "technique": "WM_KEYDOWN/WM_KEYUP postés",
        "family": fam,
        "keys": keys,
        "sent": True,
        "verified": verified,
    }
    if how:
        result["verified_by"] = how
    return result


def press_key(
    keys: str,
    hwnd: int | str | None = None,
    foreground: bool = False,
    restore_focus: bool = True,
    verify: bool = True,
    field: Any = None,
    background: bool = True,
    confirm: bool = False,
    accord: str = "",
    approved: set[str] | None = None,
) -> dict[str, Any]:
    """Presses key combination (e.g. 'ctrl+c', 'alt+f4', 'win+r', 'enter', 'ctrl+,').

    Entrée / Espace qui déclencheraient « Envoyer », « Payer »… (bouton au focus, bouton par défaut, bouton d'envoi
    voisin du champ) : refus sans confirm=true ET accord (ConfirmationRequiredError), comme le clic.

    Arrière-plan d'abord : Ctrl+A / Ctrl+V / Effacer sur le champ retenu par un clic (traduits en saisie d'arrière-plan
    relue), touche simple postée en Win32, WinForms et WPF. Vraie touche (SendInput) en repli, foreground=True
    seulement ; sinon refus explicite (UWP/WinUI et Chromium ignorent le clavier en arrière-plan).
    verify=True : effet relu sur la fenêtre cible (titre, fenêtres, image, arbre) ; sans effet visible, success=None."""
    t0 = time.perf_counter()
    emergency_stop.check()
    ensure_default_desktop()
    target_hwnd = resolve_window(hwnd)

    parts = [k.strip().lower() for k in keys.split("+") if k.strip()]
    if not parts:
        raise ValueError("Combinaison de touches vide.")
    vk_entries = _key_entries(parts)
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Touches interdites sur {reason}.")
    require_key_confirmation(target_hwnd, keys, confirm, field, accord=accord, approved=approved)

    if background and target_hwnd and user32.IsWindow(target_hwnd):
        out = _background_keys(target_hwnd, keys, parts, vk_entries, field)
        if out is not None:
            out["timing_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            _log("press_key", out.get("method", "background"), target_hwnd, t0, out, {"keys": keys})
            return out

    fam = win32_controls.family(target_hwnd) if target_hwnd and user32.IsWindow(target_hwnd) else "Inconnue"
    reason = NO_KEYBOARD_BACKGROUND.get(fam)
    if reason is None and fam == "WPF":
        reason = "WPF ignore les raccourcis Ctrl/Alt envoyés par messages (mesuré)"
    _physical_gate(target_hwnd, foreground, f"touches « {keys} »" + (f" : {reason}" if reason else ""))

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

    before = window_fingerprint(target_hwnd, with_tree=True) if verify else None
    with FocusGuard(target_hwnd, restore=restore_focus):
        _checkpoint()
        held: list[tuple[int, bool]] = []
        try:
            # 1. Hold down all modifier keys
            for vk, is_ext in modifiers:
                _send_inputs([_make_key_input(vk, is_ext, is_up=False)])
                held.append((vk, is_ext))
            if modifiers:
                time.sleep(0.015 if actions else 0.020)
            # 2. Press and release action keys (relâchement garanti, même premier plan perdu entre les deux)
            for vk, is_ext in actions:
                _send_inputs([_make_key_input(vk, is_ext, is_up=False)])
                try:
                    time.sleep(0.015)
                finally:
                    _send_inputs([_make_key_input(vk, is_ext, is_up=True)])
                time.sleep(0.010 if modifiers else 0.005)
            if modifiers and actions:
                time.sleep(0.010)
        finally:
            # 3. Release modifier keys in reverse order : toujours, jamais de touche laissée enfoncée
            for vk, is_ext in reversed(held):
                _send_inputs([_make_key_input(vk, is_ext, is_up=True)])

    verified, how = _wait_window_effect(target_hwnd, before) if verify else (None, "")
    result = {
        "success": _success(verified),
        "sent": True,
        "method": "sendinput",
        "physical": True,
        "keys": keys,
        "vk_codes": [v[0] for v in vk_entries],
        "verified": verified,
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
    if how:
        result["verified_by"] = how
    computer_logger.log_action("press_key", "sendinput", target_hwnd, (time.perf_counter() - t0) * 1000,
                               "SUCCESS" if verified else "UNVERIFIED", {"keys": keys})  # fmt: skip
    return result


def scroll(
    delta_y: int = 0,
    delta_x: int = 0,
    hwnd: int | str | None = None,
    x: int | None = None,
    y: int | None = None,
    element_index: int | None = None,
    foreground: bool = False,
    coords: str = "auto",
    restore_focus: bool = True,
) -> dict[str, Any]:
    """Scrolls via background UI Automation ScrollPattern or mouse wheel.

    ScrollPattern : position de défilement relue avant/après (`verified`). Molette physique : FocusGuard (jeton
    commun, pause de Julien, restauration du focus et du curseur), effet relu sur l'image de la fenêtre.
    """
    emergency_stop.check()
    ensure_default_desktop()
    target_hwnd = resolve_window(hwnd)  # toujours une fenêtre nommée (jamais celle de devant par défaut)

    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Défilement interdit sur {reason}.")

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
            except Exception:  # noqa: BLE001
                pass
            try:
                current = current.GetParentControl()
            except Exception:  # noqa: BLE001
                break

        if scroll_pat:

            def position() -> tuple[Any, Any]:
                try:
                    return (scroll_pat.HorizontalScrollPercent, scroll_pat.VerticalScrollPercent)
                except Exception:  # noqa: BLE001
                    return (None, None)

            before_pos = position()
            # ScrollAmount: SmallDecrement=1, NoAmount=2, SmallIncrement=4
            v_amt = 1 if delta_y > 0 else (4 if delta_y < 0 else 2)
            h_amt = 4 if delta_x > 0 else (1 if delta_x < 0 else 2)
            steps = abs(delta_y) or abs(delta_x) or 1
            for _ in range(min(steps, 20)):
                emergency_stop.check()
                scroll_pat.Scroll(h_amt, v_amt)
            after_pos = position()
            verified = None if None in before_pos + after_pos else before_pos != after_pos
            result = {
                "success": _success(verified),
                "method": "uia_scroll",
                "element_index": element_index,
                "delta_y": delta_y,
                "delta_x": delta_x,
                "verified": verified,
                "scroll_percent": {"before": before_pos, "after": after_pos},
            }
            if verified is False:
                result["message"] = "Position de défilement inchangée (déjà en butée ?)."
            return result

    # 1 bis. Point donné, interface qui ignore la molette postée (WPF, UWP, WinUI…) : défilement SÉMANTIQUE du
    # conteneur défilable sous le point, cherché dans le sous-arbre de la fenêtre (recette commune du banc NexusWindows,
    # comme Claude et Codex ; banc du 21/10, 23:42). Refus (rien envoyé) : on continue ; envoyé : jamais une autre
    # technique ensuite.
    family = win32_controls.family(target_hwnd)
    if (
        (delta_y or delta_x)
        and x is not None
        and y is not None
        and family not in (win32_controls.MESSAGE_MOUSE_FAMILIES | {"Chromium"})
    ):
        if coords == "screen":
            sem_point = (int(x), int(y))
        else:
            rect = get_window_rect(target_hwnd)
            sem_point = (rect["left"] + int(x), rect["top"] + int(y))
        try:
            outcome = uia_scroll.at_point(
                win32_controls.root_of(target_hwnd) or target_hwnd, sem_point[0], sem_point[1], delta_y, delta_x,
                app_pid(target_hwnd),
            )  # fmt: skip
        except uia_scroll.NotApplicable:
            outcome = None
        if outcome is not None:
            result = {"success": _success(outcome["verified"]), "method": "uia_scroll_at_point",
                      "technique": "défilement UI Automation au point", "physical": False, "delta_y": delta_y,
                      "delta_x": delta_x, "verified": outcome["verified"],
                      "scroll_percent": {"before": outcome.get("before"), "after": outcome.get("after")}}  # fmt: skip
            if outcome.get("message"):
                result["message"] = outcome["message"]
            return result

    # 1 bis bis. Chromium/Electron/Edge : molette par DevTools (recette B du banc commun, Codex, prouvée le 21/10), au
    # point donné ou au centre de l'élément visé, seulement si le port, la page et la liaison fenêtre ↔ page sont
    # prouvés. AVANT le défilement par ligne (banc de parité du 25/10 : la ligne amenée dans la vue n'est pas un cran,
    # 0/3 sur Edge et Electron là où la molette DevTools de Claude et Codex fait 3/3). Refus (rien envoyé) : on
    # continue ; envoyée : jamais une autre technique ensuite.
    if (delta_y or delta_x) and win32_controls.family(target_hwnd) == "Chromium":
        cdp_point: tuple[int, int] | None = None
        if x is not None and y is not None:
            if coords == "screen":
                cdp_point = (int(x), int(y))
            else:
                rect = get_window_rect(target_hwnd)
                cdp_point = (rect["left"] + int(x), rect["top"] + int(y))
        elif element_index is not None:
            crect = get_cached_element(element_index, target_hwnd).BoundingRectangle
            cdp_point = ((crect.left + crect.right) // 2, (crect.top + crect.bottom) // 2)
        if cdp_point is not None:
            # Empreinte prise APRÈS la preuve par titre (titre de la fenêtre revenu), juste avant l'envoi : le nonce ne
            # peut jamais passer pour l'effet de la molette (relecture de Codex, 21/10).
            snapshot: dict[str, Any] = {}
            try:
                sent = cdp_wheel.wheel(
                    win32_controls.root_of(target_hwnd) or target_hwnd, cdp_point[0], cdp_point[1], delta_y, delta_x,
                    check=emergency_stop.check,
                    before_send=lambda: snapshot.update(before=window_fingerprint(target_hwnd, with_tree=True)),
                )  # fmt: skip
            except cdp_wheel.NotApplicable as refusal:
                if getattr(refusal, "title_left", False):  # rien envoyé, mais la page peut garder le titre aléatoire
                    return {"success": False, "method": "devtools_wheel", "physical": False, "verified": None,
                            "message": str(refusal)}  # fmt: skip
                sent = None
            except cdp_wheel.Uncertain as error:
                return {"success": None, "method": "devtools_wheel", "technique": "molette DevTools", "physical": False,
                        "verified": None, "message": str(error)}  # fmt: skip
            if sent is not None:  # accusée par la page : partie une fois, effet relu sur l'image, jamais rejouée
                verified, how = _wait_window_effect(target_hwnd, snapshot.get("before"))
                result = {"success": _success(verified), "method": "devtools_wheel", "technique": sent["technique"],
                          "physical": False, "mechanism": sent["mechanism"], "delta_y": delta_y, "delta_x": delta_x,
                          "verified": verified, "surface": sent.get("surface")}  # fmt: skip
                if how:
                    result["verified_by"] = how
                return result

    # 1 ter. Sans molette (recette de NexusClaude du 23/10, relue par Codex) : Tk par sa barre de défilement native collée
    # au widget sous le point ; Chromium sans DevTools par la ligne cachée suivante de la zone sous le point. Refus (rien
    # envoyé) : on continue ; envoyé : jamais une autre technique ensuite.
    if delta_y and not delta_x and x is not None and y is not None and family in ("Tk", "Chromium"):
        if coords == "screen":
            line_point = (int(x), int(y))
        else:
            rect = get_window_rect(target_hwnd)
            line_point = (rect["left"] + int(x), rect["top"] + int(y))
        top = win32_controls.root_of(target_hwnd) or target_hwnd
        outcome = None
        method = ""
        if family == "Tk":
            bar = win32_controls.scroll_bar_beside(top, line_point[0], line_point[1], True)
            state = win32_controls.scroll_bar_state(bar) if bar else None
            if state is not None:
                low, high, page, pos = state
                end = max(low, high - max(int(page), 1) + 1)
                if not ((delta_y < 0 and pos >= end) or (delta_y > 0 and pos <= low)):
                    emergency_stop.check()
                    method = "tk_scroll_bar_lines"
                    try:
                        win32_controls.post_scroll_lines(
                            bar, True, delta_y < 0, abs(delta_y) * uia_scroll.LINES_PER_NOTCH
                        )
                        outcome = {"verified": None, "message": "lignes envoyées, position non relue en 1 s"}
                    except win32_controls.PartialSendError:
                        outcome = {"verified": None, "message": "envoi partiel : issue inconnue", "partial": True}
                    except win32_controls.MessageError:
                        outcome = None
                    if outcome is not None and not outcome.get("partial"):
                        deadline = time.monotonic() + uia_scroll.READ_BACK_S
                        while time.monotonic() < deadline:
                            time.sleep(0.05)
                            after = win32_controls.scroll_bar_state(bar)
                            if after is not None and after[3] != pos:
                                outcome = {"verified": True, "message": f"position {pos} → {after[3]}"}
                                break
        else:
            method = "uia_scroll_item"
            try:
                outcome = uia_scroll.item_at(top, line_point[0], line_point[1], delta_y, emergency_stop.check)
            except uia_scroll.NotApplicable:
                outcome = None
        if outcome is not None:
            result = {"success": _success(outcome["verified"]), "method": method,
                      "partial": bool(outcome.get("partial")),
                      "technique": "défilement sans molette", "physical": False, "delta_y": delta_y,
                      "verified": outcome["verified"], "message": outcome["message"]}  # fmt: skip
            return result

    # 2. Molette par message en Win32/WinForms (recette commune du banc NexusWindows : premier plan intact), au point
    # donné ou au centre de l'élément visé.
    if (delta_y or delta_x) and win32_controls.family(target_hwnd) in win32_controls.MESSAGE_MOUSE_FAMILIES:
        wheel_point: tuple[int, int] | None = None
        if x is not None and y is not None:
            if coords == "screen":
                wheel_point = (int(x), int(y))
            else:
                rect = get_window_rect(target_hwnd)
                wheel_point = (rect["left"] + int(x), rect["top"] + int(y))
        elif element_index is not None:
            crect = get_cached_element(element_index, target_hwnd).BoundingRectangle
            wheel_point = ((crect.left + crect.right) // 2, (crect.top + crect.bottom) // 2)
        if wheel_point is not None:
            before = window_fingerprint(target_hwnd, with_tree=True)
            try:
                win32_controls.post_wheel(target_hwnd, wheel_point[0], wheel_point[1], delta_y * 120, delta_x * 120)
                sent = True
            except win32_controls.PartialSendError:
                sent = True  # envoi partiel : issue inconnue, jamais la vraie molette par-dessus
            except win32_controls.MessageError:
                sent = False
            if sent:  # jamais renvoyé par la vraie molette ensuite : un effet lent serait doublé
                verified, how = _wait_window_effect(target_hwnd, before)
                result = {"success": _success(verified), "method": "win32_post_wheel", "technique": "molette par message",
                          "physical": False, "delta_y": delta_y, "verified": verified}  # fmt: skip
                if how:
                    result["verified_by"] = how
                return result

    # 3. Molette physique (repli autorisé seulement : fenêtre visée + foreground=True, jamais d'office)
    _physical_gate(
        target_hwnd,
        foreground,
        "défilement à la molette (viser une liste ou une zone défilante par son libellé pour l'arrière-plan)",
    )
    # Molette visée : point donné, sinon centre de l'élément visé ; jamais sous le curseur de Julien.
    point: tuple[int, int] | None = None
    if x is not None and y is not None:
        if coords == "screen":
            point = (int(x), int(y))
        else:
            win_rect = get_window_rect(target_hwnd)
            point = (win_rect["left"] + int(x), win_rect["top"] + int(y))
    elif element_index is not None:
        crect = get_cached_element(element_index, target_hwnd).BoundingRectangle
        point = ((crect.left + crect.right) // 2, (crect.top + crect.bottom) // 2)
    if point is None:
        raise ValueError(
            "Molette sans point visé : indiquer x, y (dans la fenêtre) ou la cible à faire défiler ; rien n'a été "
            "envoyé (jamais sous le curseur de Julien)."
        )

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

    # Preuve d'une molette physique : la POSITION relue du conteneur visé, jamais le titre de la fenêtre ou l'arbre
    # (banc commun du 22/10 : le titre changé par l'application passait pour un défilement réussi). Sans conteneur
    # lisible : issue non vérifiée, jamais affirmée.
    read = uia_scroll.position_reader(
        win32_controls.root_of(target_hwnd) or target_hwnd, point[0], point[1], delta_y != 0, app_pid(target_hwnd)
    )
    # Sens attendu : vers le bas (delta_y < 0) ou la droite (delta_x > 0) = pourcentage qui augmente.
    forward = delta_y < 0 if delta_y != 0 else delta_x > 0

    def wheel_position() -> float | None:
        """Pourcentage valide [0, 100] ; -1 (UIA NoScroll), non fini ou illisible : aucune preuve (relecture de Codex du
        22/10 14:31 : 25 → -1 passait pour un défilement)."""
        try:
            value = read() if read else None
        except Exception:  # noqa: BLE001 - illisible : pas de preuve
            return None
        return value if value is not None and math.isfinite(value) and 0.0 <= value <= 100.0 else None

    verified, how = None, ""
    with FocusGuard(target_hwnd, restore=restore_focus):
        _move_cursor(*point)
        time.sleep(0.02)
        # Référence lue SOUS la garde, après l'activation et le curseur, juste avant l'envoi ; effet relu sous la même
        # garde, avant la restitution (relecture de Codex du 22/10 14:31).
        position_before = wheel_position()
        if inputs:
            _checkpoint()
            _send_inputs(inputs)
        if position_before is not None:
            deadline = time.monotonic() + EFFECT_WAIT_S
            while time.monotonic() < deadline:
                after = wheel_position()
                if after is not None and after != position_before:
                    if (after > position_before) == forward:
                        verified, how = True, f"position relue ({position_before:g} % → {after:g} %)"
                    break
                time.sleep(EFFECT_POLL_S)
    result = {
        "success": _success(verified),
        "method": "mouse_wheel",
        "delta_y": delta_y,
        "delta_x": delta_x,
        "verified": verified,
        "focus_restored": restore_focus,
    }
    if how:
        result["verified_by"] = how
    return result


def drag(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    hwnd: int | str | None = None,
    steps: int = 12,
    delay_ms: int = 15,
    foreground: bool = False,
    coords: str = "auto",
    restore_focus: bool = True,
) -> dict[str, Any]:
    """Performs a smooth mouse drag between two coordinates.

    Vraie souris : passe par FocusGuard (jeton commun, pause de Julien, restauration du focus et du curseur). Le
    bouton est toujours relâché, même si l'arrêt d'urgence ou une reprise en main par Julien interrompt le geste.
    """
    emergency_stop.check()
    ensure_default_desktop()
    target_hwnd = resolve_window(hwnd)  # vraie souris : toujours une fenêtre visée, premier plan relu
    if coords == "screen":
        screen_from_x = from_x
        screen_from_y = from_y
        screen_to_x = to_x
        screen_to_y = to_y
    else:
        win_rect = get_window_rect(target_hwnd)
        screen_from_x = win_rect["left"] + from_x
        screen_from_y = win_rect["top"] + from_y
        screen_to_x = win_rect["left"] + to_x
        screen_to_y = win_rect["top"] + to_y

    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Glisser-déposer interdit sur {reason}.")
    _physical_gate(target_hwnd, foreground, "glisser-déposer (vraie souris : aucun équivalent d'arrière-plan)")

    before = window_fingerprint(target_hwnd, with_tree=True)
    with FocusGuard(target_hwnd, restore=restore_focus):
        _checkpoint()
        _move_cursor(screen_from_x, screen_from_y)
        time.sleep(0.03)

        # Mouse down
        down = INPUT(type=INPUT_MOUSE)
        down.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
        _send_inputs([down])
        try:
            time.sleep(0.02)

            # Intermediate steps
            for i in range(1, steps + 1):
                _checkpoint()
                cur_x = int(screen_from_x + (screen_to_x - screen_from_x) * (i / steps))
                cur_y = int(screen_from_y + (screen_to_y - screen_from_y) * (i / steps))
                _move_cursor(cur_x, cur_y)
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
        finally:
            # Mouse up : toujours, jamais de bouton laissé enfoncé
            up = INPUT(type=INPUT_MOUSE)
            up.union.mi.dwFlags = MOUSEEVENTF_LEFTUP
            _send_inputs([up])

    verified, how = _wait_window_effect(target_hwnd, before)
    result = {
        "success": _success(verified),
        "from": (from_x, from_y),
        "to": (to_x, to_y),
        "steps": steps,
        "verified": verified,
        "focus_restored": restore_focus,
    }
    if how:
        result["verified_by"] = how
    return result


# -----------------------------------------------------------------------------
# Contrôles : cocher, choisir une option, commande de menu (arrière-plan d'abord, état relu)
# -----------------------------------------------------------------------------
def _target_element(
    target_hwnd: int, element_index: int | None, target: Any, box_2d: Any = None
) -> tuple[int | None, Any, dict[str, Any]]:
    """Élément visé par index [N], libellé (target) ou box_2d (rapportée à l'élément sous le point, arbre UIA de la
    fenêtre, recouverte comprise)."""
    if element_index is None and box_2d is None:
        element_index, box_2d = _resolve_step_target({"target": target}, target_hwnd)
    if element_index is None and box_2d is not None:
        sx, sy = resolve_box_2d_coords(box_2d, target_hwnd)
        hit = _hit_test(target_hwnd, sx, sy)
        if hit is None:
            raise ValueError(f"Aucun élément UI Automation sous box_2d {list(box_2d)} : viser un libellé visible.")
        return None, hit[0], hit[1]
    if element_index is None:
        raise ValueError("Indiquez un 'element_index', une cible ('target' : #N ou libellé) ou un box_2d.")
    # Un index vient d'un look précis : jamais relu ici (il désignerait un autre élément) ; get_cached_element
    # refuse un index d'une autre fenêtre. Une cible par libellé, elle, a déjà relu la fenêtre au besoin.
    ctrl = get_cached_element(element_index, target_hwnd)
    return element_index, ctrl, _element_info.get(element_index, {})


def set_checked(
    hwnd: int | str | None = None,
    element_index: int | None = None,
    target: Any = None,
    checked: bool = True,
    box_2d: Any = None,
) -> dict[str, Any]:
    """Coche (ou décoche) une case en arrière-plan ; rien n'est envoyé si l'état est déjà le bon (`already`).

    Win32 : BM_SETCHECK + BN_CLICKED au parent. WinForms, WPF, UWP, Chromium : UIA Toggle. UNE bascule, puis relecture
    patiente (jusqu'à CHECK_SETTLE_S) : une nouvelle bascule seulement si l'effet de la précédente a été RELU (case à
    trois états) ; une autre technique seulement si l'état est relu inchangé (jamais deux bascules à l'aveugle)."""
    t0 = time.perf_counter()
    emergency_stop.check()
    target_hwnd = resolve_window(hwnd)
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Action interdite sur {reason}.")
    element_index, ctrl, info = _target_element(target_hwnd, element_index, target, box_2d)
    fam = _element_family(info, target_hwnd)
    wanted = 1 if checked else 0
    state = _read_state(ctrl, info).get("toggle")
    if state is not None and int(state) == wanted:
        result = {"success": True, "already": True, "verified": True, "method": "none", "family": fam,
                  "element_index": element_index, "checked": bool(wanted)}  # fmt: skip
        _log("set_checked", "already", target_hwnd, t0, result, {"element_index": element_index})
        return result
    own = int(info.get("hwnd") or 0)

    def settled_toggle(before: Any) -> Any:
        """État relu dès qu'il diffère de `before`, sinon le dernier lu à l'échéance (case lente : jusqu'à 1,6 s)."""
        deadline = time.monotonic() + CHECK_SETTLE_S
        while True:
            now = _read_state(ctrl, info).get("toggle")
            if now is not None and now != before:
                return now
            if time.monotonic() >= deadline:
                return now
            time.sleep(EFFECT_POLL_S)

    def uia_toggle_patient() -> str:
        before = _read_state(ctrl, info).get("toggle")
        for _ in range(3):  # case à trois états : au plus trois bascules, chacune après l'effet RELU de la précédente
            _UIA_TOGGLE(ctrl)
            now = settled_toggle(before)
            if now is None or now == before or int(now) == wanted:
                return "uia"  # effet illisible ou absent : jamais de seconde bascule ; état voulu : fini
            before = now
        return "uia"

    chain: list[tuple[str, Callable[[], Any]]] = []
    if fam == "Win32" and _native_kind(own) in ("checkbox", "radio"):
        chain.append(("BM_SETCHECK", lambda: win32_controls.set_check(own, bool(wanted))))
    chain.append(("UIA Toggle", uia_toggle_patient))

    def verify(_detail: Any) -> tuple[bool | None, str]:
        deadline = time.monotonic() + CHECK_SETTLE_S
        while True:
            now = _read_state(ctrl, info).get("toggle")
            if now is not None and int(now) == wanted:
                return True, "coche relue"
            if time.monotonic() >= deadline:
                return (None, "") if now is None else (False, "coche inchangée")
            time.sleep(EFFECT_POLL_S)

    out = _run_chain(chain, verify, user32.GetForegroundWindow())
    if not out["technique"]:
        raise RuntimeError(
            "Aucune technique d'arrière-plan n'a pu cocher l'élément : "
            + "; ".join(f"{t['technique']} : {t['error']}" for t in out["tried"])
        )
    result = {
        "success": _success(out["verified"]),
        "method": _method_slug(out["technique"]),
        "technique": out["technique"],
        "family": fam,
        "element_index": element_index,
        "checked": bool(wanted),
        "verified": out["verified"],
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
    for key in ("verified_by", "already", "focus_stolen_restored"):
        if out.get(key):
            result[key] = out[key]
    if out["tried"]:
        result["techniques_tried"] = out["tried"]
    _log("set_checked", result["method"], target_hwnd, t0, result, {"element_index": element_index})
    return result


def set_expanded(
    hwnd: int | str | None = None,
    element_index: int | None = None,
    target: Any = None,
    expanded: bool = True,
    box_2d: Any = None,
) -> dict[str, Any]:
    """Ouvre (ou ferme) une liste déroulante, un nœud ou un menu repliable, en arrière-plan, état relu ; rien n'est
    envoyé si l'état est déjà le bon (`already`).

    Liste déroulante Win32/WinForms : CB_SHOWDROPDOWN relu par CB_GETDROPPEDSTATE (ses options apparaissent ensuite
    dans look). Sinon UIA ExpandCollapse."""
    t0 = time.perf_counter()
    emergency_stop.check()
    target_hwnd = resolve_window(hwnd)
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Action interdite sur {reason}.")
    element_index, ctrl, info = _target_element(target_hwnd, element_index, target, box_2d)
    fam = _element_family(info, target_hwnd)
    own, host = int(info.get("hwnd") or 0), int(info.get("host_hwnd") or 0)
    combo = 0
    if fam in win32_controls.NATIVE_FAMILIES:
        combo = own if _native_kind(own) == "combo" else (host if not own and _native_kind(host) == "combo" else 0)

    def is_open() -> bool | None:
        if combo:
            return win32_controls.combo_dropped(combo)
        state = _read_state(ctrl, info).get("expand")
        return None if state is None else int(state) in (1, 2)  # 1 ouvert, 2 en partie

    if is_open() is expanded:
        result = {"success": True, "already": True, "verified": True, "method": "none", "family": fam,
                  "element_index": element_index, "expanded": expanded}  # fmt: skip
        _log("set_expanded", "already", target_hwnd, t0, result, {"element_index": element_index})
        return result

    def uia_set() -> str:
        pattern = ctrl.GetExpandCollapsePattern()
        if not pattern:
            raise LookupError("Motif ExpandCollapse absent.")
        pattern.Expand() if expanded else pattern.Collapse()
        return "uia"

    chain: list[tuple[str, Callable[[], Any]]] = []
    if combo:
        chain.append(("CB_SHOWDROPDOWN", lambda: win32_controls.combo_show_dropdown(combo, expanded)))
    else:
        chain.append(("UIA Expand/Collapse", uia_set))

    def verify(_detail: Any) -> tuple[bool | None, str]:
        deadline = time.monotonic() + EFFECT_WAIT_S
        while True:
            now = is_open()
            if now is expanded:
                return True, f"{'ouvert' if expanded else 'fermé'} (relu)"
            if time.monotonic() >= deadline:
                return (None, "") if now is None else (False, "état ouvert/fermé inchangé")
            time.sleep(EFFECT_POLL_S)

    out = _run_chain(chain, verify, user32.GetForegroundWindow())
    if not out["technique"]:
        raise RuntimeError(
            f"{'Ouverture' if expanded else 'Fermeture'} impossible en arrière-plan : "
            + "; ".join(f"{t['technique']} : {t['error']}" for t in out["tried"])
        )
    result = {
        "success": _success(out["verified"]),
        "method": _method_slug(out["technique"]),
        "technique": out["technique"],
        "family": fam,
        "element_index": element_index,
        "expanded": expanded,
        "verified": out["verified"],
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
    for key in ("verified_by", "already", "focus_stolen_restored"):
        if out.get(key):
            result[key] = out[key]
    if out["tried"]:
        result["techniques_tried"] = out["tried"]
    _log("set_expanded", result["method"], target_hwnd, t0, result, {"element_index": element_index})
    return result


def _uia_descendants(ctrl: Any) -> list[tuple[Any, dict[str, Any]]]:
    """Descendants d'un élément (lecture en cache, un aller-retour) : (élément brut, propriétés)."""
    if uia_fast is None:
        return []
    reader = uia_fast.reader()
    element = uia_fast.raw_element(ctrl)
    found = element.FindAllBuildCache(4, reader.uia.CreateTrueCondition(), reader.cache_one)  # TreeScope_Descendants
    out = []
    for i in range(found.Length if found else 0):
        item = found.GetElement(i)
        out.append((item, reader.props(item)))
    return out


ITEM_ROLES = {"ListItem", "TreeItem", "DataItem", "MenuItem"}


def _dedup_items(found: list[tuple[Any, dict[str, Any]]]) -> list[tuple[Any, dict[str, Any], str]]:
    """Options d'un niveau de recherche, dédoublonnées par identifiant d'exécution UIA (WPF montre un même élément
    deux fois : sous la liste et dans sa surgissante)."""
    unique: dict[Any, tuple[Any, dict[str, Any], str]] = {}
    for element, props in found:
        if _fast().control_type_name(props.get("control_type")) not in ITEM_ROLES:
            continue
        name = " ".join(str(props.get("name") or "").split())
        if not name:
            continue
        key = _fast().runtime_id(props) or (id(element),)
        unique.setdefault(key, (element, props, name))
    return list(unique.values())


def _pick_item(tier: list[tuple[Any, dict[str, Any], str]], option: str) -> tuple[Any, dict[str, Any]] | None:
    """Option voulue dans UN niveau : exacte, sinon partielle unique ; ambiguïté refusée (MessageError)."""
    if not tier:
        return None
    try:
        index = win32_controls.match_option([name for _, _, name in tier], option)
    except win32_controls.MessageError as error:
        if "absente" in str(error):
            return None
        raise
    element, props, _ = tier[index]
    return element, props


def _popup_items(windows: list[int]) -> list[tuple[Any, dict[str, Any], str]]:
    found: list[tuple[Any, dict[str, Any]]] = []
    for popup in windows:
        try:
            tree = _fast().reader().read_tree(popup, max_nodes=600, time_budget=0.8)
        except Exception:  # noqa: BLE001
            continue
        found += [(node.element, node.props) for node in tree.nodes]
    return _dedup_items(found)


def _uia_select_option(ctrl: Any, option: str, target_hwnd: int = 0) -> str:
    """Liste déroulante ou liste UIA (WPF, UWP, Chromium), recherche par niveaux (NexusClaude) : d'abord le
    sous-arbre de la liste (options repliées ou hors écran comprises) ; sinon liste dépliée, puis de nouveau son
    sous-arbre et les seules surgissantes APPARUES depuis le dépliage. Option hors écran amenée en vue (ScrollItem),
    choisie (SelectionItem, sinon Invoke), liste refermée."""
    chosen = _pick_item(_dedup_items(_uia_descendants(ctrl)), option)
    expand = None
    try:
        expand = ctrl.GetExpandCollapsePattern()
    except Exception:  # noqa: BLE001
        expand = None
    opened = False
    try:
        if chosen is None and expand and getattr(expand, "ExpandCollapseState", 0) != 1:
            pid = app_pid(target_hwnd) if target_hwnd else 0
            windows_before = set(_process_windows(pid)) if pid else set()
            expand.Expand()
            opened = True
            deadline = time.monotonic() + 1.5
            while chosen is None and time.monotonic() < deadline:
                emergency_stop.check()
                time.sleep(0.12)
                flush_chromium(target_hwnd)  # Chromium recouvert : options dépliées publiées
                chosen = _pick_item(_dedup_items(_uia_descendants(ctrl)), option)
                if chosen is None and pid:
                    popups = [h for h in _process_windows(pid) if h not in windows_before]
                    chosen = _pick_item(_popup_items(popups), option)
        typed_select = chosen is None and win32_controls.is_chromium_top(
            win32_controls.root_of(target_hwnd) or target_hwnd
        )  # <select> Chromium : options non publiées en arrière-plan → frappe du libellé, liste refermée d'abord
        if chosen is None and not typed_select:
            raise LookupError(f"Option « {option} » introuvable dans la liste.")
        if chosen is not None:
            element, props = chosen
            wrapped = _wrap_element(element, {"type_id": props.get("control_type")})
            if props.get("offscreen") and props.get("has_scroll_item"):
                try:
                    wrapped.GetScrollItemPattern().ScrollIntoView()
                except Exception:  # noqa: BLE001 - option choisie quand même ; la relecture tranche
                    pass
            selection = wrapped.GetSelectionItemPattern()
            if selection:
                selection.Select()
            else:
                _invoke_with_timeout(wrapped)
    finally:
        if opened and expand:
            try:
                if getattr(expand, "ExpandCollapseState", 0) == 1:
                    expand.Collapse()
            except Exception:  # noqa: BLE001
                pass
    if chosen is None:
        return _chromium_select_by_typing(ctrl, option, target_hwnd)
    return "uia"


def _combo_text(ctrl: Any) -> str:
    try:
        return " ".join(str(ctrl.GetValuePattern().Value or "").split())
    except Exception:  # noqa: BLE001
        return ""


def _chromium_select_by_typing(ctrl: Any, option: str, target_hwnd: int) -> str:
    """<select> Chromium (recette commune, NexusClaude) : ses options ne sont pas exposées et sa liste ne s'ouvre pas
    en arrière-plan. Focus puis frappe du libellé sous activation simulée : la recherche au clavier du <select>
    choisit l'option et émet `change` comme un humain. Relu ; envoyé sans relecture = inconnu, jamais renvoyé."""
    wanted = " ".join(option.split()).lower()
    done = _chromium_simulated_typing(target_hwnd, ctrl, option, lambda: _combo_text(ctrl).lower() == wanted)
    if done is None:
        return "pending"
    return "uia"


def select_option(
    option: str,
    hwnd: int | str | None = None,
    element_index: int | None = None,
    target: Any = None,
    box_2d: Any = None,
    confirm: bool = False,
    accord: str = "",
    approved: set[str] | None = None,
) -> dict[str, Any]:
    """Choisit une option d'une liste déroulante ou d'une liste, en arrière-plan, sélection relue. Une option est un
    élément de liste (choix réversible) : jamais de confirm exigé (NON_ACTION_ROLES ; `confirm` transmis au clic).

    Win32/WinForms : CB_SETCURSEL / LB_SETCURSEL + CBN_SELCHANGE / LBN_SELCHANGE au parent (UIA Select y est
    silencieux : jamais). WPF, UWP, Chromium : UIA (ouvrir, choisir l'option, refermer). `already` si déjà choisie."""
    t0 = time.perf_counter()
    emergency_stop.check()
    target_hwnd = resolve_window(hwnd)
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Action interdite sur {reason}.")
    element_index, ctrl, info = _target_element(target_hwnd, element_index, target, box_2d)
    fam = _element_family(info, target_hwnd)
    own = int(info.get("hwnd") or 0)
    kind = _native_kind(own)
    if info.get("type") == "ListItem":  # option visée directement : c'est un clic sur elle
        if element_index is None:
            return click(hwnd=target_hwnd, box_2d=box_2d, confirm=confirm, accord=accord, approved=approved)
        return click(hwnd=target_hwnd, element_index=element_index, confirm=confirm, accord=accord, approved=approved)

    chain: list[tuple[str, Callable[[], Any]]] = []
    if fam in win32_controls.NATIVE_FAMILIES and kind == "combo":
        chain.append(("CB_SETCURSEL", lambda: win32_controls.combo_select(own, option)))
    elif fam in win32_controls.NATIVE_FAMILIES and kind == "listbox":
        chain.append(("LB_SETCURSEL", lambda: win32_controls.listbox_select(own, option)))
    else:
        chain.append(("UIA Select", lambda: _uia_select_option(ctrl, option, target_hwnd)))

    def selected_label() -> str | None:
        if kind == "combo":
            return win32_controls.combo_selected(own)
        if kind == "listbox":
            return win32_controls.listbox_selected(own)
        value = _read_state(ctrl, info).get("value")
        if value:
            return str(value)
        try:  # liste UIA sans valeur : élément sélectionné parmi les descendants
            for _el, props in _uia_descendants(ctrl):
                if props.get("selected"):
                    return " ".join(str(props.get("name") or "").split())
        except Exception:  # noqa: BLE001
            return None
        return None

    def verify(_detail: Any) -> tuple[bool | None, str]:
        deadline = time.monotonic() + EFFECT_WAIT_S
        while True:
            label = selected_label()
            if label is not None:
                try:
                    win32_controls.match_option([label], option)
                    return True, f"option relue « {label} »"
                except win32_controls.MessageError:
                    pass
            if time.monotonic() >= deadline:
                return (None, "") if label is None else (False, f"option relue « {label} »")
            time.sleep(EFFECT_POLL_S)

    out = _run_chain(chain, verify, user32.GetForegroundWindow())
    if not out["technique"]:
        raise RuntimeError(
            f"Option « {option} » non choisie : " + "; ".join(f"{t['technique']} : {t['error']}" for t in out["tried"])
        )
    result = {
        "success": _success(out["verified"]),
        "method": _method_slug(out["technique"]),
        "technique": out["technique"],
        "family": fam,
        "element_index": element_index,
        "option": option,
        "verified": out["verified"],
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
    for key in ("verified_by", "already", "focus_stolen_restored"):
        if out.get(key):
            result[key] = out[key]
    if out["tried"]:
        result["techniques_tried"] = out["tried"]
    _log("select_option", result["method"], target_hwnd, t0, result, {"option": option})
    return result


def _find_menu_item(hwnds: list[int], label: str) -> Any:
    """Élément MenuItem nommé `label` dans les fenêtres données (fenêtre cible puis menus surgissants) : même règle
    que les cibles d'act (exact unique, sinon partiel unique en mots entiers ; ambiguïté refusée avec la liste)."""
    for top in hwnds:
        tree = _window_tree(top, max_nodes=MAX_UIA_NODES, time_budget=1.5)
        items = {i: n for i, n in enumerate(tree.nodes) if n.control_type == "MenuItem"}
        key, _note = choose_label(
            {i: n.name for i, n in items.items()},
            label,
            lambda i: f"« {items[i].name[:40]} »",
            role_of=lambda i: "MenuItem",
            what="élément de menu",
            acting=True,
        )
        if key is not None:
            node = items[key]
            return _wrap_element(node.element, {"type_id": node.props.get("control_type")})
    return None


def menu_command(
    path: str,
    hwnd: int | str | None = None,
    confirm: bool = False,
    accord: str = "",
    approved: set[str] | None = None,
) -> dict[str, Any]:
    """Commande de menu par son chemin (« Fichier > Enregistrer ») ; commande au libellé de CONFIRM_PATTERNS (Envoyer,
    Publier…) : confirm=true exigé (et accord si action sortante).

    Win32 (barre HMENU) : WM_COMMAND avec l'identifiant de l'élément, sans ouvrir le menu. Sinon UIA : chaque niveau
    ouvert (Expand) puis le dernier invoqué. Effet relu sur la fenêtre (titre, fenêtres, image) ; `expect` d'act pour
    une postcondition précise."""
    t0 = time.perf_counter()
    emergency_stop.check()
    target_hwnd = resolve_window(hwnd)
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Action interdite sur {reason}.")
    fam = win32_controls.family(target_hwnd)
    segments = [p.strip() for p in path.replace("/", ">").split(">") if p.strip()]
    if not segments:
        raise ValueError("Chemin de menu vide.")
    require_confirmation(
        segments[-1], confirm, "commande de menu", "MenuItem", target_hwnd, accord=accord, approved=approved
    )

    def uia_menu() -> str:
        if uia_fast is None:
            raise RuntimeError("UI Automation indisponible.")
        pid = _window_pid(target_hwnd)
        for i, label in enumerate(segments):
            _checkpoint()
            item = _find_menu_item([target_hwnd, *[h for h in _process_windows(pid) if h != target_hwnd]], label)
            if item is None:
                raise LookupError(f"Élément de menu « {label} » introuvable.")
            last = i == len(segments) - 1
            expand = item.GetExpandCollapsePattern() if not last else None
            if expand:
                expand.Expand()
                time.sleep(0.12)
            else:
                if _invoke_with_timeout(item) == "pending":
                    return "pending"
                if not last:
                    time.sleep(0.12)
        return "uia"

    chain: list[tuple[str, Callable[[], Any]]] = []
    if fam == "Win32" and win32_controls.menu_items(target_hwnd):
        chain.append(("WM_COMMAND menu", lambda: win32_controls.menu_command(target_hwnd, path)))
    chain.append(("UIA menu", uia_menu))
    before = window_fingerprint(target_hwnd)
    out = _run_chain(chain, lambda _d: _wait_window_effect(target_hwnd, before), user32.GetForegroundWindow())
    if not out["technique"]:
        raise RuntimeError(
            f"Menu « {path} » introuvable : " + "; ".join(f"{t['technique']} : {t['error']}" for t in out["tried"])
        )
    result = {
        "success": _success(out["verified"]),
        "method": _method_slug(out["technique"]),
        "technique": out["technique"],
        "family": fam,
        "path": path,
        "verified": out["verified"],
        "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
    for key in ("verified_by", "pending", "focus_stolen_restored"):
        if out.get(key):
            result[key] = out[key]
    if out["tried"]:
        result["techniques_tried"] = out["tried"]
    _log("menu", result["method"], target_hwnd, t0, result, {"path": path})
    return result


# -----------------------------------------------------------------------------
# Postconditions (expect) : état relu dans la fenêtre
# -----------------------------------------------------------------------------
def _find_nodes(tree: Any, wanted: str) -> tuple[list[Any], str]:
    """Nœud désigné par une postcondition : identifiant d'automatisation exact, sinon libellé (règle de choose_label :
    ambiguïté refusée). Rend ([nœud] ou [], « exact » ou « partiel »)."""
    named = [n for n in tree.nodes if n.name or n.props.get("automation_id")]
    low = " ".join(wanted.split()).casefold()
    by_id = [n for n in named if str(n.props.get("automation_id") or "").casefold() == low]
    if len(by_id) == 1:
        return by_id, "exact"
    nodes = {i: n for i, n in enumerate(named) if n.name}
    key, note = choose_label(
        {i: n.name for i, n in nodes.items()},
        wanted,
        lambda i: f"« {nodes[i].name[:40]} » {nodes[i].control_type}",
        what="élément",
    )
    if key is None:
        return [], ""
    return [nodes[key]], ("partiel" if note else "exact")


def check_expect(hwnd: int | str | None, expect: dict[str, Any]) -> tuple[bool | None, dict[str, Any]]:
    """Évalue une postcondition sur l'état ACTUEL de la fenêtre (lecture UIA fraîche, messages Win32 pour les
    contrôles natifs). Rend (vrai/faux/None si indécidable, ce qui a été observé).

    Clés : element (libellé, identifiant d'automatisation ou « #N »), value, contains, checked, selected, enabled,
    exists ; title / title_contains pour le titre de la fenêtre."""
    target_hwnd = resolve_window(hwnd)
    observed: dict[str, Any] = {}
    verdicts: list[bool | None] = []
    title = _window_text(target_hwnd)
    if "title" in expect:
        observed["title"] = title
        verdicts.append(_same_text(title, expect["title"]))
    if "title_contains" in expect:
        observed["title"] = title
        verdicts.append(str(expect["title_contains"]).lower() in title.lower())
    wanted = expect.get("element") or expect.get("target")
    if wanted is not None:
        info: dict[str, Any] = {}
        node_props: dict[str, Any] | None = None
        ctrl = None
        tree_status = "ok"
        wanted_s = str(wanted).strip()
        if wanted_s.startswith("#") and wanted_s[1:].isdigit() and _cached_window_hwnd == target_hwnd:
            idx = int(wanted_s[1:])
            if idx in _element_cache:
                ctrl, info = _element_cache[idx], _element_info.get(idx, {})
                observed["match"] = "exact"
        else:
            if uia_fast is None:
                return None, {"error": "UI Automation indisponible"}
            tree = _window_tree(target_hwnd, max_nodes=MAX_UIA_NODES, time_budget=2.0)
            tree_status = tree.status
            nodes, match = _find_nodes(tree, wanted_s) if tree.status != "failed" else ([], "")
            if nodes:
                node = nodes[0]
                ctrl = node.element
                node_props = node.props
                info = {"hwnd": int(node.props.get("hwnd") or 0), "type": node.control_type, "name": node.name}
                observed["match"] = match
                if match == "partiel":
                    observed["element_name"] = node.name
        exists = ctrl is not None
        if ctrl is not None and node_props is None:
            state = _read_state(ctrl, info)
            exists = state.get("exists", True) is not False
        elif ctrl is not None and node_props is not None:
            state = _read_state(None, info)  # messages Win32 (valeur, coche) ; propriétés déjà fraîches
            for key in ("value", "toggle", "selected", "expand", "name", "enabled"):
                if key in node_props and state.get(key) is None:
                    state[key] = node_props[key]
        else:
            state = {}
        observed["exists"] = exists
        if "exists" in expect:
            if exists or tree_status == "ok":
                verdicts.append(exists == bool(expect["exists"]))
            else:
                verdicts.append(None)  # arbre coupé ou illisible : absence non prouvée
        elif not exists:
            verdicts.append(False if tree_status == "ok" else None)
        if exists:
            value = state.get("value")
            if value is not None:
                observed["value"] = _norm_text(value)
            if "value" in expect:
                verdicts.append(None if value is None else _same_text(value, expect["value"]))
            if "contains" in expect:
                verdicts.append(
                    None if value is None else _norm_text(expect["contains"]).lower() in _norm_text(value).lower()
                )
            if "checked" in expect:
                toggle = state.get("toggle")
                observed["checked"] = None if toggle is None else int(toggle) == 1
                verdicts.append(None if toggle is None else (int(toggle) == 1) == bool(expect["checked"]))
            if "selected" in expect:
                selected = state.get("selected")
                observed["selected"] = selected
                verdicts.append(None if selected is None else bool(selected) == bool(expect["selected"]))
            if "enabled" in expect:
                enabled = state.get("enabled")
                observed["enabled"] = enabled
                verdicts.append(None if enabled is None else bool(enabled) == bool(expect["enabled"]))
    if not verdicts:
        raise ValueError(
            "Postcondition 'expect' vide : indiquez element + value/contains/checked/selected/exists, ou title."
        )
    if any(v is False for v in verdicts):
        return False, observed
    if any(v is None for v in verdicts):
        return None, observed
    return True, observed


def wait_expect(hwnd: int | str | None, expect: dict[str, Any], timeout: float | None = None):
    """Relit la postcondition jusqu'à ce qu'elle soit vraie ou que le délai expire (défaut 1,5 s)."""
    limit = float(expect.get("timeout", EXPECT_TIMEOUT_S) if timeout is None else timeout)
    deadline = time.monotonic() + min(max(limit, 0.0), 10.0)
    while True:
        met, observed = check_expect(hwnd, expect)
        if met is True or time.monotonic() >= deadline:
            return met, observed
        time.sleep(0.1)


# -----------------------------------------------------------------------------
# SOTA Batch Macro-Actions & Multimodal Vision Inspection (look & act)
# -----------------------------------------------------------------------------
def look(
    hwnd: int | str | None = None,
    query: str | None = None,
    max_elements: int = 120,
    max_depth: int = 30,
    annotate: bool = False,
    capture_screenshot: bool = True,
    output_path: str | None = None,
    zoom: list[int] | None = None,
) -> dict[str, Any]:
    """Inspects target window or screen, returning interactive elements and optional WebP screenshot.

    Equipped with Gemini box_2d [ymin, xmin, ymax, xmax] (0-1000) and Set-of-Marks [#1], [#2]...
    Supports targeting by HWND integer or title/process substring (e.g. 'claude', 'chrome', 'calc').
    """
    target_hwnd = resolve_window(hwnd)
    return get_window_state(
        hwnd=target_hwnd,
        max_elements=max_elements,
        capture_screenshot=capture_screenshot,
        output_path=output_path,
        max_depth=max_depth,
        annotate_screenshot=annotate,
        query=query,
        zoom=zoom,
    )


def _quote(text: Any) -> str:
    return "« " + " ".join(str(text).split()) + " »"


def format_look(state: dict[str, Any]) -> str:
    """Regard compact pour le modèle : une ligne par élément « [N] rôle « nom » = « valeur » états @x,y » (x, y : point
    dans la fenêtre, utilisable tel quel par act). Même information utile que le JSON (index, rôle, nom, valeur,
    coche, sélection, désactivé, liste ouverte, centre), 3 à 4 fois moins de jetons."""
    bounds = state.get("bounds") or {}
    uia = state.get("uia") or {}
    head = (
        f"fenêtre {state.get('hwnd')} {_quote(state.get('title') or '')} {state.get('process_name') or '?'} "
        f"({state.get('family') or '?'}) {bounds.get('width', '?')}x{bounds.get('height', '?')} · "
        f"{state.get('element_count', len(state.get('elements') or []))} éléments · UIA {uia.get('status', '?')}"
    )
    lines = [head, 'cible : target="libellé exact", "#N", ou x/y (@x,y ci-dessous) ; box_2d d\'après l\'image']
    size = state.get("image_dimensions")
    if size:  # échelle toujours dite : x/y sont des pixels de FENÊTRE, l'image peut être réduite (règle commune)
        sx = state.get("scale_x") or state.get("scale_factor")
        sy = state.get("scale_y") or sx
        left, top = state.get("image_origin") or (0, 0)
        zoom = state.get("zoom")
        where = f"zone zoomée box_2d {zoom}" if zoom else "fenêtre entière"
        lines.append(
            f"image {size[0]}x{size[1]} : {where} (x fenêtre = {left:g} + x image / {sx}, y fenêtre = {top:g} + "
            f"y image / {sy}) ; box_2d de la fenêtre entière, indépendant de l'image"
        )
    if not (state.get("elements") or []):
        # « l'image jointe » seulement si elle l'est vraiment (décision `attached` du serveur MCP ; texte d'abord).
        seen = "d'après l'image WebP jointe" if state.get("attached") else "capture_screenshot=true pour la voir"
        lines.append(
            "[Mode visuel / repli actif] Aucun élément UI Automation exposé par cette fenêtre. "
            f"Ciblez directement par box_2d [ymin, xmin, ymax, xmax] ({seen}) ou "
            'coordonnées relatives target="@x,y" (avec foreground=true).'
        )
    for el in state.get("elements") or []:
        parts = [f"[{el.get('index')}]", str(el.get("type") or "?")]
        if el.get("name"):
            parts.append(_quote(el["name"]))
        if el.get("value"):
            parts.append("= " + _quote(el["value"]))
        if "checked" in el:
            parts.append("☑" if el["checked"] else "☐")
        if el.get("selected"):
            parts.append("sélectionné")
        if el.get("enabled") is False:
            parts.append("désactivé")
        if el.get("open_list"):
            parts.append("liste ouverte")
        center = el.get("relative_center") or {}
        if center:
            parts.append(f"@{center.get('x')},{center.get('y')}")
        lines.append(" ".join(parts))
    if state.get("note"):
        lines.append(f"ℹ {state['note']}")
    if state.get("warning"):
        lines.append(f"⚠ {state['warning']}")
    return "\n".join(lines)


class AmbiguousTargetError(ValueError):
    """Libellé (ou fenêtre, menu, postcondition) qui désigne plusieurs éléments : refus, avec les candidats."""


def _label_key(text: Any) -> str:
    """Libellé comparable : casse et espaces ignorés, « & » d'accélérateur, raccourci de menu après une tabulation
    (« Enregistrer\tCtrl+S ») et « : », « * », « … » ou « ... » finaux retirés."""
    key = " ".join(str(text or "").split("\t", 1)[0].replace("&", "").split()).casefold()
    return re.sub(r"(\s*(\.\.\.|…|:|\*))+$", "", key).strip()


# Mots qui inversent le sens d'un libellé : « Ne pas supprimer » n'est jamais « Supprimer », « Don't send » jamais
# « Send ». Une correspondance partielle qui en ajoute un au libellé voulu n'est jamais retenue.
INVERTING_RE = re.compile(r"\b(ne|pas|non|sans|annuler|jamais|don ?t|do not|not|no|cancel|skip|never)\b")  # n'…pas
# Seuls les CHAMPS acceptent un libellé partiel unique (« Nom » → « Nom de famille ») ; un bouton, un menu, un lien
# ou tout autre élément d'action se vise par son nom exact ou son [N].
PARTIAL_OK_ROLES = ("Edit", "ComboBox", "Document")


def _inverting_words(text: Any) -> set[str]:
    return {m.group(0) for m in INVERTING_RE.finditer(_plain(text))}


def label_matches(names: dict[Any, str], wanted: Any) -> tuple[list[Any], list[Any]]:
    """(exacts, partiels) : partiel = le libellé voulu en MOTS entiers dans le nom (« Nom » ne trouve pas
    « Prénom : ») et SANS mot qui en inverse le sens (« Supprimer » ne trouve pas « Ne pas supprimer »)."""
    w = _label_key(wanted)
    if not w:
        return [], []
    exact = [key for key, name in names.items() if _label_key(name) == w]
    pattern = re.compile(r"(?<!\w)" + re.escape(w) + r"(?!\w)")
    kept = _inverting_words(wanted)
    partial = [
        key
        for key, name in names.items()
        if key not in exact and pattern.search(_label_key(name)) and not (_inverting_words(name) - kept)
    ]
    return exact, partial


def choose_label(
    names: dict[Any, str],
    wanted: Any,
    describe: Callable[[Any], str],
    role_of: Callable[[Any], str] | None = None,
    roles: tuple[str, ...] = (),
    what: str = "élément",
    acting: bool = False,
    combo_of: Callable[[Any], Any] | None = None,
) -> tuple[Any, str]:
    """Choix SANS hasard : exact unique d'abord ; plusieurs exacts → refus (jamais un partiel à la place) ; aucun exact
    et un seul partiel → accepté et signalé ; plusieurs partiels → refus. Le rôle attendu par l'action (`roles`)
    départage seulement s'il laisse un candidat unique. Un partiel n'ajoute jamais une négation (label_matches).
    `acting` (cible d'une action) : le partiel unique n'est accepté que pour un champ (PARTIAL_OK_ROLES) ; pour un
    bouton, un menu, un lien… refus qui propose le candidat. Rend (clé ou None, note)."""
    exact, partial = label_matches(names, wanted)
    for tier, kind in ((exact, "exact"), (partial, "partiel")):
        if not tier:
            continue
        if len(tier) > 1 and roles and role_of is not None:
            narrowed = [key for key in tier if role_of(key) in roles]
            if len(narrowed) == 1:
                tier = narrowed
            elif "Edit" in roles and combo_of is not None and len(narrowed) == 2:
                # Liste déroulante modifiable : la ComboBox et SON champ Edit (enfant direct relu dans l'arbre) portent
                # le même nom (« Nom du fichier : » des boîtes Ouvrir/Enregistrer, passe 2 du 22/10) ; le texte va au
                # champ. Deux champs distincts restent ambigus (relecture de Codex).
                edit = next((key for key in narrowed if role_of(key) == "Edit"), None)
                combo = next((key for key in narrowed if role_of(key) == "ComboBox"), None)
                if edit is not None and combo is not None and combo_of(edit) == combo:
                    tier = [edit]
        if len(tier) == 1:
            key = tier[0]
            if kind == "partiel" and acting and (role_of is None or role_of(key) not in PARTIAL_OK_ROLES):
                raise AmbiguousTargetError(
                    f"« {wanted} » n'est le nom exact d'aucun {what} ; seul candidat partiel : {describe(key)}. Rien n'a "
                    "été fait : un bouton, un menu ou un lien se vise par son nom exact ou son [N] (viser [N] ou le "
                    "nom exact)."
                )
            note = "" if kind == "exact" else f"libellé partiel : « {names[key]} » choisi pour « {wanted} »"
            return key, note
        listed = " ; ".join(describe(key) for key in tier[:10])
        raise AmbiguousTargetError(
            f"« {wanted} » désigne {len(tier)} {what}s ({kind}s) : {listed}. Rien n'a été fait : viser « #N » ou un "
            "libellé exact unique."
        )
    return None, ""


ACTION_ROLES: dict[str, tuple[str, ...]] = {
    "type": ("Edit", "Document", "ComboBox"),
    "type_text": ("Edit", "Document", "ComboBox"),
    "paste": ("Edit", "Document", "ComboBox"),
    "set": ("Edit", "Document", "ComboBox"),
    "set_value": ("Edit", "Document", "ComboBox"),
    "clear": ("Edit", "Document", "ComboBox"),
    "check": ("CheckBox", "RadioButton", "ListItem", "TreeItem", "DataItem", "MenuItem"),
    "uncheck": ("CheckBox", "RadioButton", "ListItem", "TreeItem", "DataItem", "MenuItem"),
    "select": ("ComboBox", "List"),
    "select_option": ("ComboBox", "List"),
    "expand": ("ComboBox", "TreeItem", "MenuItem", "SplitButton"),
    "collapse": ("ComboBox", "TreeItem", "MenuItem", "SplitButton"),
    "click": ("Button", "SplitButton", "Hyperlink", "MenuItem", "TabItem", "ListItem", "CheckBox", "RadioButton"),
}


def _cache_line(idx: int) -> str:
    info = _element_info.get(idx, {})
    return f"[{idx}] « {str(info.get('name') or '')[:40]} » {info.get('type') or '?'}"


def _find_by_label(label: str, action: str = "") -> tuple[int | None, str]:
    """Index du cache désigné par le libellé (règle de choose_label) et la note éventuelle (libellé partiel)."""
    names = {idx: str(_element_info.get(idx, {}).get("name") or "") for idx in _element_cache}
    if not any(names.values()):  # cache sans propriétés (repli pas à pas) : noms lus en direct
        names = {idx: str(getattr(c, "Name", "") or "") for idx, c in _element_cache.items()}
    return choose_label(
        names,
        label,
        _cache_line,
        role_of=lambda idx: str(_element_info.get(idx, {}).get("type") or ""),
        roles=ACTION_ROLES.get(action, ()),
        acting=True,
        combo_of=_combo_of_edit,
    )


def _combo_of_edit(idx: int) -> int | None:
    """Index du cache de la ComboBox dont l'Edit `idx` est l'enfant direct (même lecture de l'arbre), sinon None."""
    parent = _element_info.get(idx, {}).get("combo_parent")
    if parent is None:
        return None
    return next((i for i, info in _element_info.items() if info.get("tree_index") == parent), None)


def _resolve_step_target(
    s: dict[str, Any], target_hwnd: int
) -> tuple[int | None, list[int] | tuple[int, int, int, int] | None]:
    """Cible d'une étape d'act : index Set-of-Marks (« #N », « [N] »), box_2d, ou libellé (règle de choose_label).
    Une note de libellé partiel est rangée dans s["_target_note"]."""
    box_2d = s.get("box_2d")
    element_index = s.get("element_index") or s.get("index")
    target = s.get("target")

    if target is not None and element_index is None and box_2d is None:
        if isinstance(target, bool):
            raise ValueError(f"Cible invalide : {target!r}.")
        if isinstance(target, int):
            element_index = target
        elif isinstance(target, (list, tuple)) and len(target) == 4:
            box_2d = list(target)
        elif isinstance(target, str):
            t_str = target.strip()
            marked = re.fullmatch(r"(?:#|\[)\s*(\d+)\s*\]?", t_str)
            box_match = re.fullmatch(r"(?:box_2d:)?\s*\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]", t_str)
            coords_match = re.fullmatch(r"(?:@|coords:|x=)?\s*(\d+)\s*(?:,|\s*,\s*|x|\s*y=)\s*(\d+)", t_str)
            if marked:
                element_index = int(marked.group(1))
            elif box_match:
                box_2d = [int(box_match.group(i)) for i in range(1, 5)]
            elif coords_match:
                s["x"] = int(coords_match.group(1))
                s["y"] = int(coords_match.group(2))
                s["_target_note"] = f"coordonnées relatives ({s['x']}, {s['y']})"
            elif t_str.isdigit():
                element_index = int(t_str)
            else:
                action = str(s.get("action") or "").lower().replace("-", "_").strip()
                fresh = _cached_window_hwnd != target_hwnd or not _element_info
                if fresh:
                    get_window_state(hwnd=target_hwnd, max_elements=200)
                found, note = _find_by_label(t_str, action)
                if found is None and not fresh:
                    # Absent du dernier look (liste ouverte, boîte apparue depuis) : fenêtre relue une fois.
                    get_window_state(hwnd=target_hwnd, max_elements=200)
                    found, note = _find_by_label(t_str, action)
                if found is None:
                    if s.get("x") is not None and s.get("y") is not None:
                        s["_target_note"] = (
                            f"libellé '{target}' absent de l'arbre UIA, repli visuel sur coordonnées ({s['x']}, {s['y']})"
                        )
                    elif s.get("box_2d") is not None:
                        s["_target_note"] = f"libellé '{target}' absent de l'arbre UIA, repli visuel sur box_2d"
                    else:
                        raise ValueError(f"Élément cible '{target}' introuvable dans la fenêtre.")
                else:
                    element_index = found
                    if note:
                        s["_target_note"] = note
    return element_index, box_2d


WAIT_MAX_S = 30.0  # attente la plus longue d'une étape wait (annoncée si la demande est plus longue)


def _text_present(hwnd: int, text: str) -> bool | None:
    """Texte présent dans la fenêtre (titre, noms ou valeurs de l'arbre UIA), casse et accents ignorés ; None si
    l'arbre est illisible."""
    wanted = _plain(text)
    if wanted and wanted in _plain(_window_text(hwnd)):
        return True
    if uia_fast is None:
        return None
    try:
        tree = _window_tree(hwnd, max_nodes=MAX_UIA_NODES, time_budget=1.0)
    except Exception:  # noqa: BLE001
        return None
    if tree.status == "failed":
        return None
    for node in tree.nodes:
        if wanted in _plain(node.name) or wanted in _plain(node.props.get("value")):
            return True
    return False if tree.status == "ok" else None


def _wait_step(s: dict[str, Any], target_hwnd: int) -> dict[str, Any]:
    """Étape wait : durée demandée (seconds, ou delay_ms), bornée à WAIT_MAX_S et annoncée EXACTEMENT ; avec `text`,
    attente de son apparition (ou de sa disparition avec gone=true) : ✓ relue, ✗ si le délai expire."""
    text = s.get("text") or s.get("until")
    gone = s.get("gone") is True
    given = s.get("seconds") if s.get("seconds") is not None else s.get("timeout")
    if given is not None:
        requested = float(given)
    elif s.get("delay_ms") is not None:
        requested = float(s["delay_ms"]) / 1000.0
    else:
        requested = 5.0 if text else 0.1
    bounded = min(max(0.0, requested), WAIT_MAX_S)
    t0 = time.monotonic()
    deadline = t0 + bounded
    out: dict[str, Any] = {"requested_seconds": requested}
    if requested > WAIT_MAX_S:
        out["note"] = f"durée demandée {requested:g} s ramenée à {WAIT_MAX_S:g} s"
    if not text:
        while time.monotonic() < deadline:
            emergency_stop.check()  # une attente reste interruptible par l'arrêt d'urgence
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        out.update(success=True, verified=True, waited_seconds=round(time.monotonic() - t0, 2))
        return out
    seen: bool | None = None
    while True:
        emergency_stop.check()
        present = _text_present(target_hwnd, str(text))
        if present is not None:
            seen = present
            if present is not gone:
                out.update(success=True, verified=True, waited_seconds=round(time.monotonic() - t0, 2),
                           verified_by=f"texte « {text} » {'disparu' if gone else 'apparu'} (relu)")  # fmt: skip
                return out
        if time.monotonic() >= deadline:
            break
        time.sleep(0.15)
    waited = round(time.monotonic() - t0, 2)
    if seen is None:
        out.update(success=None, verified=None, waited_seconds=waited, message="fenêtre illisible pendant l'attente")
    else:
        out.update(success=False, verified=False, waited_seconds=waited,
                   verified_by=f"texte « {text} » {'toujours là' if gone else 'non apparu'} après {waited:g} s")  # fmt: skip
    return out


def _run_act_step(
    action: str,
    s: dict[str, Any],
    target_hwnd: int,
    foreground: bool,
    step_index: int,
) -> dict[str, Any]:
    """Exécute une étape d'act et renvoie son résultat (lève en cas d'échec). `confirm` de l'étape : seulement après
    un « oui » explicite de Julien pour une action de CONFIRM_PATTERNS (payer, envoyer, publier…)."""
    confirm = s.get("confirm") is True
    policy = _current_policy()
    step_accord = str(s.get("accord") or (policy.accord if policy is not None else "") or "").strip()
    approved = policy.approved if policy is not None else None
    if action == "menu":
        return menu_command(
            path=str(s.get("path") or s.get("target") or ""),
            hwnd=target_hwnd,
            confirm=confirm,
            accord=step_accord,
            approved=approved,
        )
    if action in ("wait", "sleep"):
        return _wait_step(s, target_hwnd)
    element_index, box_2d = _resolve_step_target(s, target_hwnd)
    x = s.get("x")
    y = s.get("y")
    coords = s.get("coords", "auto")
    restore = not foreground

    if action in ("click", "left_click", "double_click", "right_click"):
        return click(
            hwnd=target_hwnd,
            element_index=element_index,
            x=x,
            y=y,
            box_2d=box_2d,
            button="right" if action == "right_click" else "left",
            click_count=2 if action == "double_click" else 1,
            foreground=foreground,
            restore_focus=restore,
            coords=coords,
            confirm=confirm,
            accord=step_accord,
            approved=approved,
        )
    if action in ("type", "paste", "type_text"):
        return type_text(
            text=s.get("text") or s.get("value") or "",
            hwnd=target_hwnd,
            element_index=element_index,
            x=x,
            y=y,
            box_2d=box_2d,
            clear_first=bool(s.get("clear_first", False)),
            submit=bool(s.get("submit", False)),
            method=str(s.get("method", "auto")),
            foreground=foreground,
            restore_focus=restore,
            confirm=confirm,
            accord=step_accord,
            approved=approved,
        )
    if action in ("set", "set_value"):
        return type_text(
            text=s.get("text") or s.get("value") or "",
            hwnd=target_hwnd,
            element_index=element_index,
            x=x,
            y=y,
            box_2d=box_2d,
            clear_first=True,
            submit=False,
            method=str(s.get("method", "auto")),
            foreground=foreground,
            restore_focus=restore,
            confirm=confirm,
            accord=step_accord,
            approved=approved,
        )
    if action == "clear":
        if element_index is not None:
            return type_text(
                text="",
                hwnd=target_hwnd,
                element_index=element_index,
                clear_first=True,
                submit=False,
                method="auto",
                foreground=foreground,
                restore_focus=restore,
                confirm=confirm,
                accord=step_accord,
                approved=approved,
            )
        press_key(
            "ctrl+a",
            hwnd=target_hwnd,
            foreground=foreground,
            restore_focus=restore,
            verify=False,
            confirm=confirm,
            accord=step_accord,
            approved=approved,
        )
        return press_key(
            "backspace",
            hwnd=target_hwnd,
            foreground=foreground,
            restore_focus=restore,
            confirm=confirm,
            accord=step_accord,
            approved=approved,
        )
    if action in ("check", "uncheck"):
        return set_checked(hwnd=target_hwnd, element_index=element_index, checked=action == "check", box_2d=box_2d)
    if action in ("expand", "collapse"):
        return set_expanded(hwnd=target_hwnd, element_index=element_index, expanded=action == "expand", box_2d=box_2d)
    if action in ("select", "select_option"):
        option = s.get("option") or s.get("value") or s.get("text")
        if option is None:
            raise ValueError(f"Étape {step_index} : 'option' est requise pour select.")
        return select_option(
            str(option),
            hwnd=target_hwnd,
            element_index=element_index,
            box_2d=box_2d,
            confirm=confirm,
            accord=step_accord,
            approved=approved,
        )
    if action in ("key", "press_key", "hotkey"):
        if element_index is not None:  # touche visée sur un élément nommé « Envoyer »… : même règle que le clic
            info = _element_info.get(element_index, {})
            require_confirmation(
                info.get("name") or "",
                confirm,
                "touche",
                str(info.get("type") or ""),
                target_hwnd,
                accord=step_accord,
                approved=approved,
            )
        return press_key(
            keys=s.get("key") or s.get("keys") or "",
            hwnd=target_hwnd,
            foreground=foreground,
            restore_focus=restore,
            confirm=confirm,
            accord=step_accord,
            approved=approved,
        )
    if action == "scroll":
        return scroll(
            delta_y=s.get("delta_y", 0),
            delta_x=s.get("delta_x", 0),
            hwnd=target_hwnd,
            x=x,
            y=y,
            element_index=element_index,
            foreground=foreground,
            coords=coords,
            restore_focus=restore,
        )
    if action == "drag":
        return drag(
            from_x=s.get("from_x", 0),
            from_y=s.get("from_y", 0),
            to_x=s.get("to_x", 0),
            to_y=s.get("to_y", 0),
            hwnd=target_hwnd,
            steps=s.get("steps", 12),
            delay_ms=s.get("delay_ms", 15),
            foreground=foreground,
            coords=coords,
            restore_focus=restore,
        )
    if action in ("hover", "move", "mouse_move"):
        target_x = x
        target_y = y
        if box_2d is not None:
            sx, sy = resolve_box_2d_coords(box_2d, target_hwnd)
            wrect = get_window_rect(target_hwnd)
            target_x = sx - wrect["left"]
            target_y = sy - wrect["top"]
        elif element_index is not None:
            ctrl = get_cached_element(element_index, target_hwnd)
            crect = ctrl.BoundingRectangle
            wrect = get_window_rect(target_hwnd)
            target_x = ((crect.left + crect.right) // 2) - wrect["left"]
            target_y = ((crect.top + crect.bottom) // 2) - wrect["top"]
        return mouse_move(
            x=target_x or 0,
            y=target_y or 0,
            hwnd=target_hwnd,
            smooth=bool(s.get("smooth", True)),
            foreground=foreground,
            coords=coords,
            restore_focus=restore,
        )
    if action == "focus":
        _physical_gate(target_hwnd, foreground, "mise au premier plan (prend le premier plan à Julien)")
        res = focus_window(hwnd=target_hwnd)
        res["verified"] = user32.GetForegroundWindow() == target_hwnd
        res["success"] = bool(res["success"]) and res["verified"]
        return res
    raise ValueError(f"Action '{action}' non reconnue dans l'étape {step_index}.")


EXACT_EXPECT_KEYS = {"value", "checked", "selected", "title"}


def _exact_postcondition(expect: dict[str, Any]) -> bool:
    """Postcondition qui prouve à elle seule qu'une étape est déjà faite (état exact, jamais une présence)."""
    keys = set(expect) - {"element", "target", "timeout"}
    return bool(keys) and keys <= EXACT_EXPECT_KEYS


_LABEL_KEYS = {"element", "target", "match"}  # libellés visés (permis au journal), jamais un texte saisi ou attendu


def _masked_texts(value: Any) -> Any:
    """Postcondition ou état observé pour le journal sur disque : chaque texte (valeur attendue, valeur lue, titre)
    remplacé par sa longueur ; libellés visés, booléens et nombres gardés. La réponse à l'agent garde les valeurs."""
    if isinstance(value, dict):
        return {k: (v if k in _LABEL_KEYS else _masked_texts(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_masked_texts(v) for v in value]
    if isinstance(value, str):
        return f"<{len(value)} car.>"
    return value


def _private_texts(step: dict[str, Any]) -> list[str]:
    """Textes saisis ou attendus d'une étape : `text` et les textes de `expect` hors libellés visés."""
    out = [step.get("text")]
    expect = step.get("expect")
    if isinstance(expect, dict):
        out += [v for k, v in expect.items() if k not in _LABEL_KEYS]
    return [v for v in out if isinstance(v, str) and v]


def _redacted(step: dict[str, Any], message: str) -> str:
    """Message d'erreur pour le journal sur disque : textes saisis ou attendus de l'étape remplacés par leur longueur
    (un refus d'accord résume le texte saisi)."""
    for value in sorted(_private_texts(step), key=len, reverse=True):
        message = message.replace(value, f"<{len(value)} car.>")
    return message


def act(
    steps: list[dict[str, Any]],
    hwnd: int | str | None = None,
    then: str = "state",
    foreground: bool = False,
    time_budget: float = 30.0,
    accord: str | None = None,
) -> dict[str, Any]:
    """Exécute un lot d'actions en un seul appel, en arrière-plan d'abord.

    - Ciblage : `target` (libellé visible, "#N", index, box_2d), `element_index`, `box_2d` Gemini (0-1000) ou (x, y).
      Un point visé est rapporté à l'élément qu'il désigne : techniques d'arrière-plan comme pour un libellé.
    - Relecture automatique : chaque étape porte `verified` (vrai/faux/None) et une marque `mark` (✓ relu, = déjà
      fait, ~ effet non vu, ✗ échec). Postcondition optionnelle `expect`, évaluée APRÈS l'étape (relue fausse → ✗) ;
      étape sautée (`already`, =) seulement si une postcondition EXACTE (élément trouvé par libellé exact, value,
      checked, selected ou title) est déjà vraie avant — jamais sur « exists », « contains » ou un libellé partiel.
    - Garde-fous : surface Windows impossible à piloter (session, verrouillage, UAC) refusée d'emblée ; payer,
      acheter, commander, virer, envoyer, publier, supprimer définitivement, désinstaller, formater, réinitialiser,
      résilier refusés sans `confirm: true` sur l'étape, aussi par Entrée/Espace/submit qui les déclencheraient
      (CONFIRM_PATTERNS, NEXUS_AGY_CONFIRM=off pour tout désactiver) ; libellé ambigu refusé avec les candidats.
    - foreground=False (défaut) : aucune vraie souris ni vrai clavier ; une étape impossible en arrière-plan est
      refusée (NeedsForegroundError, rien envoyé). foreground=True : vraie souris/clavier en REPLI seulement ; la garde
      du lot (jeton commun tenu sans trou, fenêtre devant, premier plan et curseur rendus à la fin) n'est prise qu'au
      premier geste physique réellement nécessaire.
    - Compte rendu sans perte : une étape en échec ou sans effet établi arrête le lot avant l'étape suivante et
      figure dans `steps` ; `success` est faux en échec, None si l'effet reste inconnu. Aucun rejeu automatique.
      Une postcondition relue vraie établit l'effet et permet de poursuivre. `next` dit quoi faire ensuite.
    """
    t0 = time.perf_counter()
    emergency_stop.check()
    ensure_default_desktop()
    target_hwnd = resolve_window(hwnd)
    is_protected, reason = is_protected_system_window(target_hwnd)
    if is_protected:
        raise PermissionError(f"Action interdite sur {reason}. Rien n'a été fait.")

    blind_paste_err = garde_fous.check_blind_paste(steps)
    if blind_paste_err:
        raise ValueError(blind_paste_err)

    results: list[dict[str, Any]] = []
    failure: str | None = None
    failure_logged: str | None = None  # même message pour le journal sur disque : textes saisis/attendus masqués
    uncertain: list[int] = []
    interrupted = False

    default_accord = str(accord or "").strip()
    policy = _PhysicalPolicy(
        allow=bool(foreground), target_hwnd=target_hwnd, lot=bool(foreground and target_hwnd), accord=default_accord
    )
    previous_policy = _current_policy()
    _policy_local.current = policy
    try:
        for i, s in enumerate(steps):
            if (time.perf_counter() - t0) > time_budget:
                failure = failure_logged = f"Budget de temps de {time_budget} s dépassé avant l'étape {i}"
                results.append({"step": i, "status": "timeout", "mark": agent_guard.MARK_FAIL, "message": failure})
                break

            s = dict(s) if isinstance(s, dict) else {}
            action = str(s.get("action", "")).lower().replace("-", "_").strip()
            expect = s.get("expect")
            try:
                emergency_stop.check()  # point de contrôle entre les étapes
                if not action:
                    raise ValueError(f"Étape {i} invalide : 'action' est requise.")
                if expect is not None and not isinstance(expect, dict):
                    raise ValueError(f"Étape {i} : 'expect' doit être un objet.")
                if expect and _exact_postcondition(expect):
                    met, observed = check_expect(target_hwnd, expect)
                    if met is True and (not (expect.get("element") or expect.get("target"))
                                        or observed.get("match") == "exact"):  # fmt: skip
                        results.append({"step": i, "action": action, "status": "ok", "already": True,
                                        "verified": True, "mark": agent_guard.MARK_ALREADY,
                                        "observed": observed})  # fmt: skip
                        continue
                step_res = _run_act_step(action, s, target_hwnd, foreground, i)
                if expect and isinstance(step_res, dict):
                    met, observed = wait_expect(target_hwnd, expect)
                    step_res["expect"] = {"met": met, "observed": observed}
                    # Envoi partiel : issue inconnue terminale, qu'aucune postcondition n'efface (relecture de Codex).
                    step_res["verified"] = None if step_res.get("partial") else met
                    step_res["success"] = _success(step_res["verified"])
                    if met is not True:
                        step_res.pop("already", None)  # l'état du contrôle ne prouve pas la postcondition finale
            except Exception as error:  # noqa: BLE001 - le compte rendu des étapes déjà faites ne doit pas se perdre
                failure = f"Étape {i} ({action or '?'}) : {error}"
                failure_logged = _redacted(s, failure)
                interrupted = isinstance(error, UserInterruptError)
                results.append(
                    {
                        "step": i,
                        "action": action,
                        "status": "error",
                        "mark": agent_guard.MARK_FAIL,
                        "error": str(error),
                        "error_type": type(error).__name__,
                        **({"what": error.what} if isinstance(error, NeedsForegroundError) else {}),
                        **({"partial_input": True} if getattr(error, "partial_input", False) else {}),
                    }
                )
                break

            success = step_res.get("success") if isinstance(step_res, dict) else None
            verified = step_res.get("verified") if isinstance(step_res, dict) else None
            already = bool(isinstance(step_res, dict) and step_res.get("already"))
            if success is False:
                status = "failed"
            elif success is not True or verified is not True:
                status = "unverified"
                uncertain.append(i)
            else:
                status = "ok"
            entry = {
                "step": i,
                "action": action,
                "status": status,
                "verified": verified,
                "mark": agent_guard.mark(verified, success, already),
                "result": step_res,
            }
            if already:
                entry["already"] = True
            if s.get("_target_note"):
                entry["target_note"] = s["_target_note"]
            results.append(entry)
            if status == "failed":
                failure = f"Étape {i} ({action}) : échec relu" + (
                    f" (attendu {expect}, observé {step_res.get('expect', {}).get('observed')})" if expect else ""
                )
                failure_logged = f"Étape {i} ({action}) : échec relu" + (
                    f" (attendu {_masked_texts(expect)}, observé "
                    f"{_masked_texts(step_res.get('expect', {}).get('observed'))})"
                    if expect
                    else ""
                )
                break
            if status == "unverified":
                break  # l'effet précédent doit être établi avant d'envoyer une autre action
    finally:
        _policy_local.current = previous_policy
        if policy.lot_guard is not None:
            policy.lot_guard.__exit__(UserInterruptError if interrupted else None, None, None)

    elapsed = (time.perf_counter() - t0) * 1000
    computer_logger.log_action(
        "act",
        "batch",
        target_hwnd,
        elapsed,
        "FAILURE" if failure else ("UNVERIFIED" if uncertain else "SUCCESS"),
        {"steps_count": len(steps), "executed": len(results), "error": failure_logged},
    )

    res: dict[str, Any] = {
        "success": False if failure else (None if uncertain else True),
        "hwnd": target_hwnd,
        "executed_steps": len(results),
        "total_steps": len(steps),
        "steps": results,
        "physical_steps": policy.physical_steps,
        "timing_ms": round(elapsed, 2),
    }
    if failure:
        res["error"] = failure
    if interrupted:
        res["interrupted_by_user"] = True
    note = window_browser_note(target_hwnd)
    if note:
        res["note"] = note
    if uncertain and not failure:
        res["unverified_steps"] = uncertain
        res["warning"] = (
            "Lot arrêté sur un effet non établi : la suite n'a pas été envoyée. "
            "Regarder l'image jointe ou look avant toute reprise ; ajouter une postcondition 'expect' si utile."
        )
    res["next"] = agent_guard.next_for_act(res)

    # Post-execution inspection (lecture : permise même pendant un arrêt d'urgence)
    try:
        if then == "state":
            res["state"] = get_window_state(hwnd=target_hwnd, max_elements=100, capture_screenshot=False)
        elif then == "look":
            res["state"] = look(hwnd=target_hwnd, max_elements=100, capture_screenshot=True)
    except Exception as error:  # noqa: BLE001
        res["state_error"] = str(error)
    return res
