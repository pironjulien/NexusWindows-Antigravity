"""Contrôles Win32 natifs pilotés par messages directs : en arrière-plan, sans souris, sans clavier, sans focus.

Mesures de référence (NexusClaude/nexus-windows bench/RESULTS.md, 11 octobre 2026) reprises ici :
- Bouton Win32 : WM_COMMAND/BN_CLICKED au parent ✓ silencieux ; BM_CLICK active la fenêtre (il simule un clic) ;
  UIA Invoke ⚠ (le proxy UIA des boutons Win32 appelle lui-même SetForegroundWindow) : jamais sur un bouton Win32.
- Case : BM_SETCHECK + BN_CLICKED ✓ (Win32) ; en WinForms, BN_CLICKED est sans effet → UIA Toggle.
- Champ : EM_SETSEL + EM_REPLACESEL ✓ (le contrôle émet lui-même EN_UPDATE/EN_CHANGE, annulation possible).
- Liste déroulante / liste : CB_SETCURSEL / LB_SETCURSEL + CBN_SELCHANGE / LBN_SELCHANGE ✓ ; UIA Select sur une liste
  Win32 ou WinForms change la sélection SANS prévenir l'application (silencieux) : jamais.
- Liste déroulante OUVERTE (banc du 16/10) : sa liste est une fenêtre ComboLBox de premier niveau à part (hors de
  l'arbre de la fenêtre), reliée par GetComboBoxInfo. CB_SHOWDROPDOWN l'ouvre et la ferme sans activation ni vol de
  premier plan (relu par CB_GETDROPPEDSTATE). Sa fermeture par CB_SHOWDROPDOWN(FALSE) est une ANNULATION
  (CBN_SELENDCANCEL) : WinForms y remet la sélection d'avant l'ouverture (mesuré : choix perdu, « Formule= » vide).
  Ordre juste : fermer d'abord, puis CB_SETCURSEL relu, puis CBN_SELENDOK et CBN_SELCHANGE ENVOYÉS (synchrones, dans
  l'ordre) au parent.
- Menu Win32 (HMENU) : WM_COMMAND avec l'identifiant de l'élément ✓.

Chaque fonction lève MessageError quand la technique ne s'applique pas (essayer la suivante) et relit l'état du
contrôle quand c'est possible.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t


def _fn(name: str, restype, *argtypes):
    func = getattr(_user32, name)
    func.restype = restype
    func.argtypes = list(argtypes)
    return func


_SendMessageTimeoutW = _fn(
    "SendMessageTimeoutW",
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ULONG_PTR),
)
_PostMessageW = _fn("PostMessageW", wintypes.BOOL, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_GetClassNameW = _fn("GetClassNameW", ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_GetParent = _fn("GetParent", wintypes.HWND, wintypes.HWND)
_GetAncestor = _fn("GetAncestor", wintypes.HWND, wintypes.HWND, wintypes.UINT)
_GetDlgCtrlID = _fn("GetDlgCtrlID", ctypes.c_int, wintypes.HWND)
_GetWindowLongW = _fn("GetWindowLongW", ctypes.c_long, wintypes.HWND, ctypes.c_int)
_IsWindowEnabled = _fn("IsWindowEnabled", wintypes.BOOL, wintypes.HWND)
_IsWindow = _fn("IsWindow", wintypes.BOOL, wintypes.HWND)
_GetNextDlgGroupItem = _fn("GetNextDlgGroupItem", wintypes.HWND, wintypes.HWND, wintypes.HWND, wintypes.BOOL)
_GetMenu = _fn("GetMenu", wintypes.HMENU, wintypes.HWND)
_GetMenuItemCount = _fn("GetMenuItemCount", ctypes.c_int, wintypes.HMENU)
_GetMenuItemID = _fn("GetMenuItemID", wintypes.UINT, wintypes.HMENU, ctypes.c_int)
_GetSubMenu = _fn("GetSubMenu", wintypes.HMENU, wintypes.HMENU, ctypes.c_int)
_GetMenuStringW = _fn(
    "GetMenuStringW", ctypes.c_int, wintypes.HMENU, wintypes.UINT, wintypes.LPWSTR, ctypes.c_int, wintypes.UINT
)
_GetMenuState = _fn("GetMenuState", wintypes.UINT, wintypes.HMENU, wintypes.UINT, wintypes.UINT)
_MapVirtualKeyW = _fn("MapVirtualKeyW", wintypes.UINT, wintypes.UINT, wintypes.UINT)
_GetWindowThreadProcessId = _fn("GetWindowThreadProcessId", wintypes.DWORD, wintypes.HWND, ctypes.c_void_p)
_IsChild = _fn("IsChild", wintypes.BOOL, wintypes.HWND, wintypes.HWND)
_IsWindowVisible = _fn("IsWindowVisible", wintypes.BOOL, wintypes.HWND)
_EnumChildProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_EnumChildWindows = _fn("EnumChildWindows", wintypes.BOOL, wintypes.HWND, _EnumChildProc, wintypes.LPARAM)


class COMBOBOXINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcItem", wintypes.RECT),
        ("rcButton", wintypes.RECT),
        ("stateButton", wintypes.DWORD),
        ("hwndCombo", wintypes.HWND),
        ("hwndItem", wintypes.HWND),
        ("hwndList", wintypes.HWND),
    ]


_GetComboBoxInfo = _fn("GetComboBoxInfo", wintypes.BOOL, wintypes.HWND, ctypes.POINTER(COMBOBOXINFO))


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


_GetGUIThreadInfo = _fn("GetGUIThreadInfo", wintypes.BOOL, wintypes.DWORD, ctypes.POINTER(GUITHREADINFO))

SMTO_NORMAL, SMTO_ABORTIFHUNG = 0x0, 0x2
GWL_STYLE = -16
GA_ROOT = 2
WM_COMMAND, WM_SETTEXT, WM_GETTEXT, WM_GETTEXTLENGTH = 0x0111, 0x000C, 0x000D, 0x000E
BM_GETCHECK, BM_SETCHECK = 0x00F0, 0x00F1
BN_CLICKED = 0
EM_GETSEL, EM_SETSEL, EM_REPLACESEL = 0x00B0, 0x00B1, 0x00C2
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
ES_READONLY = 0x0800
ES_PASSWORD = 0x0020
BS_TYPEMASK = 0xF
BS_PUSHBUTTON, BS_DEFPUSHBUTTON, BS_CHECKBOX, BS_AUTOCHECKBOX = 0x0, 0x1, 0x2, 0x3
BS_RADIOBUTTON, BS_3STATE, BS_AUTO3STATE, BS_AUTORADIOBUTTON = 0x4, 0x5, 0x6, 0x9
BS_OWNERDRAW = 0xB
PUSHBUTTON_KINDS = (BS_PUSHBUTTON, BS_DEFPUSHBUTTON, BS_OWNERDRAW)
CHECKBOX_KINDS = (BS_CHECKBOX, BS_AUTOCHECKBOX, BS_3STATE, BS_AUTO3STATE)
RADIO_KINDS = (BS_RADIOBUTTON, BS_AUTORADIOBUTTON)
CB_GETCOUNT, CB_GETCURSEL, CB_GETLBTEXT, CB_GETLBTEXTLEN, CB_SETCURSEL = 0x146, 0x147, 0x148, 0x149, 0x14E
CB_SHOWDROPDOWN, CB_GETDROPPEDSTATE = 0x14F, 0x157
LB_SETCURSEL, LB_GETCURSEL, LB_GETTEXT, LB_GETTEXTLEN, LB_GETCOUNT = 0x186, 0x188, 0x189, 0x18A, 0x18B
LBS_MULTIPLESEL, LBS_EXTENDEDSEL = 0x0008, 0x0800
CBN_SELCHANGE, LBN_SELCHANGE, CBN_SELENDOK = 1, 1, 9
MF_BYPOSITION, MF_GRAYED, MF_DISABLED = 0x400, 0x1, 0x2
ERROR_ACCESS_DENIED = 5

BUTTON_CLASSES = ("button",)
EDIT_CLASSES = ("edit", "richedit", "richedit20w", "richedit50w", "richeditd2dpt")
COMBO_CLASSES = ("combobox",)
LISTBOX_CLASSES = ("listbox",)
COMBO_LIST_CLASSES = ("combolbox",)  # liste ouverte d'une liste déroulante : fenêtre de premier niveau à part

# Famille d'interface d'une fenêtre de premier niveau, par préfixe de classe (NexusClaude snapshot.py).
FAMILY_BY_CLASS = (
    ("Chrome_WidgetWin_", "Chromium"),
    ("ApplicationFrameWindow", "UWP"),
    ("Windows.UI.Core.CoreWindow", "UWP"),
    ("WinUIDesktopWin32WindowClass", "WinUI"),
    ("HwndWrapper", "WPF"),
    ("WindowsForms10", "WinForms"),
    ("MozillaWindowClass", "Firefox"),
    ("TkTopLevel", "Tk"),
    ("Qt5", "Qt"),
    ("Qt6", "Qt"),
    ("SunAwt", "Java"),
    ("Notepad", "WinUI"),
)
UIA_ONLY_FAMILIES = {"WPF", "XAML", "UWP", "WinUI", "DirectUI", "Chromium", "Firefox"}
NATIVE_FAMILIES = {"Win32", "WinForms"}


class MessageError(RuntimeError):
    """La technique par messages ne s'applique pas à cette cible (essayer la suivante)."""


# --- Outils de base -----------------------------------------------------------------------------------------
def send(hwnd: int, msg: int, wparam: int = 0, lparam: int = 0, timeout_ms: int = 1000) -> int | None:
    """SendMessage borné dans le temps : None si la fenêtre ne répond pas (ou a disparu)."""
    result = ULONG_PTR(0)
    ok = _SendMessageTimeoutW(
        hwnd, msg, wparam, lparam, SMTO_ABORTIFHUNG | SMTO_NORMAL, timeout_ms, ctypes.byref(result)
    )
    if not ok:
        return None
    return int(result.value)


def _signed(value: int | None) -> int | None:
    """LRESULT relu non signé (CB_ERR / LB_ERR = -1) → entier signé."""
    if value is None:
        return None
    return value - (1 << (ctypes.sizeof(ULONG_PTR) * 8)) if value >= 1 << (ctypes.sizeof(ULONG_PTR) * 8 - 1) else value


def post(hwnd: int, msg: int, wparam: int, lparam: int) -> None:
    """PostMessage vérifié : un refus (fenêtre disparue, application élevée bloquée par UIPI) n'est jamais un succès."""
    if not _PostMessageW(hwnd, msg, wparam, lparam):
        error = ctypes.get_last_error()
        if error == ERROR_ACCESS_DENIED:
            raise MessageError("Windows bloque les messages vers cette application (élevée, UIPI).")
        raise MessageError(f"PostMessage refusé (erreur {error}).")


def class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _GetClassNameW(hwnd, buf, 256)
    return buf.value


def base_class(hwnd: int) -> str:
    """Classe Win32 sous-jacente, en minuscules (WinForms : « WindowsForms10.BUTTON.app.0.x » → « button »)."""
    cls = class_name(hwnd).lower()
    if cls.startswith("windowsforms"):
        parts = cls.split(".")
        return parts[1] if len(parts) > 1 else cls
    return cls


def is_class(hwnd: int, names: tuple[str, ...]) -> bool:
    return bool(hwnd) and base_class(hwnd) in names


def style(hwnd: int) -> int:
    return _GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF


def root_of(hwnd: int) -> int:
    return int(_GetAncestor(hwnd, GA_ROOT) or 0)


def family(hwnd: int) -> str:
    """Famille d'interface de la fenêtre (de son premier niveau) : Win32, WinForms, WPF, UWP, WinUI, Chromium…"""
    if not hwnd:
        return "Inconnue"
    top = root_of(hwnd) or hwnd
    cls = class_name(top)
    return next((name for prefix, name in FAMILY_BY_CLASS if cls.startswith(prefix)), "Win32")


def get_text(hwnd: int, timeout_ms: int = 1000) -> str | None:
    """Texte d'un contrôle via WM_GETTEXT (marshallé entre processus par Windows)."""
    length = send(hwnd, WM_GETTEXTLENGTH, 0, 0, timeout_ms)
    if length is None:
        return None
    buf = ctypes.create_unicode_buffer(length + 2)
    if send(hwnd, WM_GETTEXT, length + 1, ctypes.addressof(buf), timeout_ms) is None:
        return None
    return buf.value


def _notify_parent(control: int, code: int) -> None:
    """Notification WM_COMMAND (code, identifiant) au parent, comme le contrôle l'enverrait après un vrai clic."""
    parent = int(_GetParent(control) or 0)
    if not parent:
        raise MessageError("Contrôle sans parent.")
    ident = _GetDlgCtrlID(control) & 0xFFFF
    post(parent, WM_COMMAND, (code << 16) | ident, control)


def _notify_parent_sync(control: int, code: int) -> None:
    """Notification WM_COMMAND ENVOYÉE (synchrone, bornée) au parent : traitée avant la suivante, dans l'ordre voulu
    (un message posté passerait après les notifications que le contrôle envoie lui-même). Application qui ne répond
    pas dans le délai : postée, comme _notify_parent."""
    parent = int(_GetParent(control) or 0)
    if not parent:
        raise MessageError("Contrôle sans parent.")
    ident = _GetDlgCtrlID(control) & 0xFFFF
    if send(parent, WM_COMMAND, (code << 16) | ident, control, timeout_ms=2000) is None:
        post(parent, WM_COMMAND, (code << 16) | ident, control)


def _radio_group(control: int) -> list[int]:
    parent = int(_GetParent(control) or 0)
    out: list[int] = []
    current = control
    for _ in range(64):
        current = int(_GetNextDlgGroupItem(parent, current, False) or 0)
        if not current or current == control:
            break
        if is_class(current, BUTTON_CLASSES) and style(current) & BS_TYPEMASK == BS_AUTORADIOBUTTON:
            out.append(current)
    return out


# --- Boutons et cases ------------------------------------------------------------------------------------------
def button_kind(control: int) -> int:
    return style(control) & BS_TYPEMASK


def get_check(control: int) -> int | None:
    """État d'une case ou d'un bouton radio (0, 1, 2 indéterminé), None si illisible."""
    state = send(control, BM_GETCHECK)
    return None if state is None else state & 0x3


def button_click(control: int) -> str:
    """Bouton Win32 : WM_COMMAND/BN_CLICKED au parent, comme un vrai clic (case automatique : coche basculée)."""
    if not is_class(control, BUTTON_CLASSES):
        raise MessageError("Pas un bouton Win32.")
    if not _IsWindowEnabled(control):
        raise MessageError("Bouton désactivé.")
    kind = button_kind(control)
    if kind in (BS_AUTOCHECKBOX, BS_AUTO3STATE):
        state = get_check(control)
        if state is None:
            raise MessageError("Bouton figé.")
        send(control, BM_SETCHECK, (state + 1) % (3 if kind == BS_AUTO3STATE else 2))
    elif kind == BS_AUTORADIOBUTTON:
        for other in _radio_group(control):
            send(other, BM_SETCHECK, 0)
        send(control, BM_SETCHECK, 1)
    _notify_parent(control, BN_CLICKED)
    return "bn_clicked"


def set_check(control: int, checked: bool) -> str:
    """Case Win32 : BM_SETCHECK puis BN_CLICKED au parent ; état relu. Rien n'est envoyé si l'état est déjà le bon."""
    if not is_class(control, BUTTON_CLASSES) or button_kind(control) not in CHECKBOX_KINDS + RADIO_KINDS:
        raise MessageError("Pas une case à cocher Win32.")
    if not _IsWindowEnabled(control):
        raise MessageError("Case désactivée.")
    wanted = 1 if checked else 0
    if get_check(control) == wanted:
        return "already"
    if button_kind(control) == BS_AUTORADIOBUTTON and wanted:
        for other in _radio_group(control):
            send(other, BM_SETCHECK, 0)
    send(control, BM_SETCHECK, wanted)
    if get_check(control) != wanted:
        raise MessageError("La case n'a pas pris l'état demandé (relu).")
    _notify_parent(control, BN_CLICKED)
    return "bm_setcheck"


# --- Champs ---------------------------------------------------------------------------------------------------
def edit_set_text(control: int, text: str, append: bool = False) -> str:
    """Champ Edit/RichEdit : EM_SETSEL + EM_REPLACESEL (le contrôle émet EN_UPDATE/EN_CHANGE comme une saisie)."""
    if not is_class(control, EDIT_CLASSES):
        raise MessageError("Pas un champ Edit Win32.")
    if style(control) & ES_READONLY:
        raise MessageError("Champ en lecture seule.")
    if not _IsWindowEnabled(control):
        raise MessageError("Champ désactivé.")
    if append:
        send(control, EM_SETSEL, 0x7FFFFFFF, 0x7FFFFFFF)
    else:
        send(control, EM_SETSEL, 0, -1)
    buf = ctypes.create_unicode_buffer(text.replace("\r\n", "\n").replace("\n", "\r\n"))
    if send(control, EM_REPLACESEL, 1, ctypes.addressof(buf), timeout_ms=2000) is None:
        raise MessageError("Le champ ne répond pas.")
    return "em_replacesel"


def is_password_edit(control: int) -> bool:
    """Champ Edit/RichEdit Win32 au style ES_PASSWORD (caractères masqués)."""
    return bool(control) and is_class(control, EDIT_CLASSES) and bool(style(control) & ES_PASSWORD)


# --- Listes ---------------------------------------------------------------------------------------------------
def _item_texts(control: int, count_msg: int, len_msg: int, text_msg: int) -> list[str]:
    count = _signed(send(control, count_msg)) or 0
    items: list[str] = []
    for i in range(min(max(count, 0), 2000)):
        length = _signed(send(control, len_msg, i))
        if length is None or length < 0:
            items.append("")
            continue
        buf = ctypes.create_unicode_buffer(length + 2)
        send(control, text_msg, i, ctypes.addressof(buf))
        items.append(buf.value)
    return items


def match_option(items: list[str], wanted: str) -> int:
    """Index de l'option voulue : correspondance exacte (casse et espaces ignorés), sinon partielle unique ; refus
    d'une ambiguïté plutôt qu'un choix au hasard."""
    low = " ".join(wanted.split()).lower()
    exact = [i for i, item in enumerate(items) if " ".join(item.split()).lower() == low]
    if len(exact) == 1:
        return exact[0]
    if exact:
        raise MessageError(f"« {wanted} » apparaît {len(exact)} fois dans la liste : impossible de savoir laquelle.")
    partial = [i for i, item in enumerate(items) if low and low in item.lower()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        raise MessageError(f"« {wanted} » est ambigu : {', '.join(items[i] for i in partial[:8])}.")
    raise MessageError(f"Option « {wanted} » absente ({', '.join(items[:20])}).")


def combo_items(control: int) -> list[str]:
    return _item_texts(control, CB_GETCOUNT, CB_GETLBTEXTLEN, CB_GETLBTEXT)


def listbox_items(control: int) -> list[str]:
    return _item_texts(control, LB_GETCOUNT, LB_GETTEXTLEN, LB_GETTEXT)


def combo_selected(control: int) -> str | None:
    index = _signed(send(control, CB_GETCURSEL))
    if index is None or index < 0:
        return None
    items = combo_items(control)
    return items[index] if index < len(items) else None


def listbox_selected(control: int) -> str | None:
    index = _signed(send(control, LB_GETCURSEL))
    if index is None or index < 0:
        return None
    items = listbox_items(control)
    return items[index] if index < len(items) else None


def combo_dropped(control: int) -> bool | None:
    """Liste déroulante ouverte ? (CB_GETDROPPEDSTATE ; None si illisible)."""
    state = send(control, CB_GETDROPPEDSTATE)
    return None if state is None else bool(state)


def combo_list_of(control: int) -> int:
    """Liste (ComboLBox) d'une liste déroulante Win32/WinForms, d'après GetComboBoxInfo (0 si illisible)."""
    info = COMBOBOXINFO(cbSize=ctypes.sizeof(COMBOBOXINFO))
    if not control or not _GetComboBoxInfo(control, ctypes.byref(info)):
        return 0
    return int(info.hwndList or 0)


def child_windows(top: int) -> list[int]:
    """Fenêtres enfants (tous niveaux) d'une fenêtre, 5000 au plus."""
    out: list[int] = []

    def cb(hwnd: int, _: int) -> bool:
        out.append(int(hwnd))
        return len(out) < 5000

    _EnumChildWindows(top, _EnumChildProc(cb), 0)
    return out


def combo_owning(drop: int, top: int) -> int:
    """Liste déroulante de `top` qui possède la ComboLBox `drop` (rien d'autre ne les relie), 0 sinon."""
    for child in child_windows(top):
        if is_class(child, COMBO_CLASSES) and combo_list_of(child) == drop:
            return child
    return 0


def open_combo_lists(top: int) -> list[tuple[int, int]]:
    """Listes déroulantes Win32/WinForms OUVERTES de la fenêtre : (liste déroulante, sa ComboLBox visible)."""
    out: list[tuple[int, int]] = []
    for child in child_windows(top):
        if is_class(child, COMBO_CLASSES) and combo_dropped(child):
            drop = combo_list_of(child)
            if drop and _IsWindowVisible(drop):
                out.append((child, drop))
    return out


def combo_show_dropdown(control: int, show: bool, timeout_s: float = 0.6) -> str:
    """Ouvre ou ferme la liste d'une liste déroulante : CB_SHOWDROPDOWN, état relu par CB_GETDROPPEDSTATE (sans
    activation, sans souris). Fermer ainsi ANNULE un choix fait dans la liste ouverte : combo_select ferme d'abord."""
    if not is_class(control, COMBO_CLASSES):
        raise MessageError("Pas une liste déroulante Win32.")
    if not _IsWindowEnabled(control):
        raise MessageError("Liste déroulante désactivée.")
    if not combo_list_of(control):
        raise MessageError("Liste déroulante sans liste à ouvrir (style simple).")
    if combo_dropped(control) is show:
        return "already"
    if send(control, CB_SHOWDROPDOWN, int(show)) is None:
        raise MessageError("La liste déroulante ne répond pas.")
    deadline = time.monotonic() + timeout_s
    while combo_dropped(control) is not show:
        if time.monotonic() >= deadline:
            raise MessageError(f"La liste ne s'est pas {'ouverte' if show else 'fermée'} (relu).")
        time.sleep(0.02)
    return "cb_showdropdown"


def combo_select(control: int, option: str) -> str:
    """Liste déroulante, ouverte ou fermée : l'application reçoit la valeur comme après un vrai choix.

    Liste ouverte : refermée D'ABORD (CB_SHOWDROPDOWN(FALSE) est une annulation, sur laquelle WinForms remet
    l'ancienne sélection par-dessus le choix). Puis CB_SETCURSEL relu, et CBN_SELENDOK puis CBN_SELCHANGE envoyés au parent dans cet
    ordre (celui d'un choix réel), chacun traité avant le suivant. Sélection relue après les notifications."""
    if not is_class(control, COMBO_CLASSES):
        raise MessageError("Pas une liste déroulante Win32.")
    items = combo_items(control)
    index = match_option(items, option)
    if combo_dropped(control):
        send(control, CB_SHOWDROPDOWN, 0)
        if combo_dropped(control):
            raise MessageError("La liste ouverte n'a pas pu être refermée (relu).")
    if _signed(send(control, CB_GETCURSEL)) == index:
        return "already"
    send(control, CB_SETCURSEL, index)
    if _signed(send(control, CB_GETCURSEL)) != index:
        raise MessageError("La liste déroulante n'a pas pris la sélection.")
    _notify_parent_sync(control, CBN_SELENDOK)
    _notify_parent_sync(control, CBN_SELCHANGE)
    if _signed(send(control, CB_GETCURSEL)) != index:
        raise MessageError("L'application a remis une autre sélection après la notification (relu).")
    return "cb_setcursel"


def listbox_select(control: int, option: str) -> str:
    """Liste simple : LB_SETCURSEL relu, puis LBN_SELCHANGE au parent."""
    if not is_class(control, LISTBOX_CLASSES):
        raise MessageError("Pas une liste Win32.")
    if style(control) & (LBS_MULTIPLESEL | LBS_EXTENDEDSEL):
        raise MessageError("Liste à sélection multiple : LB_SETCURSEL ne s'y applique pas.")
    items = listbox_items(control)
    index = match_option(items, option)
    if _signed(send(control, LB_GETCURSEL)) == index:
        return "already"
    send(control, LB_SETCURSEL, index)
    if _signed(send(control, LB_GETCURSEL)) != index:
        raise MessageError("La liste n'a pas pris la sélection.")
    _notify_parent(control, LBN_SELCHANGE)
    return "lb_setcursel"


# --- Menus Win32 (HMENU) --------------------------------------------------------------------------------------
def _menu_label(menu, pos: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _GetMenuStringW(menu, pos, buf, 256, MF_BYPOSITION)
    return buf.value.replace("&", "").split("\t")[0].strip()


def menu_items(top: int) -> list[tuple[str, int]]:
    """Chemins « Fichier > Enregistrer » → identifiant de commande, pour une barre de menus Win32 classique."""
    out: list[tuple[str, int]] = []

    def walk(menu, prefix: str, depth: int) -> None:
        for pos in range(max(0, _GetMenuItemCount(menu))):
            label = _menu_label(menu, pos)
            path = f"{prefix} > {label}" if prefix else label
            sub = _GetSubMenu(menu, pos)
            if sub and depth < 6:
                walk(sub, path, depth + 1)
            else:
                ident = _GetMenuItemID(menu, pos)
                state = _GetMenuState(menu, pos, MF_BYPOSITION)
                if ident not in (0, 0xFFFFFFFF) and label and not state & (MF_GRAYED | MF_DISABLED):
                    out.append((path, ident))

    menu = _GetMenu(top)
    if menu:
        walk(menu, "", 0)
    return out


def menu_command(top: int, path: str) -> str:
    """Commande de menu par son chemin (« Fichier > Enregistrer » ou dernier libellé seul) : WM_COMMAND au cadre."""
    items = menu_items(top)
    if not items:
        raise MessageError("Pas de barre de menus Win32.")
    wanted = [p.strip().lower() for p in path.replace("/", ">").split(">") if p.strip()]
    matches = []
    for label, ident in items:
        parts = [p.strip().lower() for p in label.split(">")]
        if parts[-len(wanted) :] == wanted:
            matches.append((label, ident))
    if len(matches) > 1:
        raise MessageError(f"Menu « {path} » ambigu : {', '.join(m[0] for m in matches[:6])}.")
    if not matches:
        raise MessageError(f"Commande de menu « {path} » introuvable.")
    post(top, WM_COMMAND, matches[0][1] & 0xFFFF, 0)
    return "wm_command_menu"


# --- Clavier par messages (fenêtre en arrière-plan, sans activation) -----------------------------------------
# Mesuré par NexusClaude (bench/RESULTS.md) : touches simples postées ✓ en Win32, WinForms et WPF ; ignorées en
# UWP/WinUI/XAML et par Chromium d'une fenêtre inactive ; raccourcis Ctrl/Alt ignorés en WPF.
EXTENDED_KEYS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}


def keyboard_target(top: int) -> int:
    """Fenêtre qui reçoit le clavier dans la cible : focus du thread de la cible s'il est l'une de ses fenêtres
    (jamais une fenêtre d'un autre premier niveau), sinon la fenêtre principale."""
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    thread = _GetWindowThreadProcessId(top, None)
    if thread and _GetGUIThreadInfo(thread, ctypes.byref(info)):
        focus = int(info.hwndFocus or 0)
        if focus and (focus == top or _IsChild(top, focus)):
            return focus
    return top


DM_GETDEFID, DC_HASDEFID = 0x0400, 0x534B
DIALOG_CLASS = "#32770"
WS_VISIBLE = 0x10000000


def _live_push_button(hwnd: int) -> bool:
    """Bouton poussoir affiché (style WS_VISIBLE du bouton lui-même : la fenêtre cible peut être recouverte ou
    réduite) et actif."""
    return (is_class(hwnd, BUTTON_CLASSES) and button_kind(hwnd) in PUSHBUTTON_KINDS
            and bool(style(hwnd) & WS_VISIBLE) and bool(_IsWindowEnabled(hwnd)))  # fmt: skip


def default_button(top: int) -> int:
    """Bouton qu'Entrée déclenche dans la fenêtre : DM_GETDEFID d'une boîte de dialogue (envoyé seulement à la classe
    #32770 : WM_USER n'a pas de sens ailleurs), sinon bouton visible et actif au style BS_DEFPUSHBUTTON (WinForms
    AcceptButton compris). 0 s'il n'y en a pas."""
    children = child_windows(top)
    if class_name(top) == DIALOG_CLASS:
        res = send(top, DM_GETDEFID)
        if res and (res >> 16) & 0xFFFF == DC_HASDEFID:
            ident = res & 0xFFFF
            for child in children:
                if _GetDlgCtrlID(child) == ident and _live_push_button(child):
                    return child
    for child in children:
        if _live_push_button(child) and button_kind(child) == BS_DEFPUSHBUTTON:
            return child
    return 0


def focused_push_button(top: int) -> int:
    """Bouton poussoir qui a le focus clavier dans la fenêtre (Entrée ou Espace l'activent), 0 sinon."""
    focus = keyboard_target(top)
    return focus if focus != top and _live_push_button(focus) else 0


def _key_lparam(vk: int, up: bool) -> int:
    scan = _MapVirtualKeyW(vk, 0) & 0xFF
    lparam = 1 | (scan << 16)
    if vk in EXTENDED_KEYS:
        lparam |= 1 << 24
    if up:
        lparam |= (1 << 30) | (1 << 31)
    return lparam


def post_key(target: int, vk: int) -> str:
    """Touche simple : WM_KEYDOWN puis WM_KEYUP postés (la boucle de l'application fabrique elle-même WM_CHAR ;
    l'ajouter doublerait Entrée, Tab ou la lettre)."""
    if not is_window(target):
        raise MessageError("Fenêtre de clavier introuvable.")
    post(target, WM_KEYDOWN, vk, _key_lparam(vk, False))
    post(target, WM_KEYUP, vk, _key_lparam(vk, True))
    return "wm_keydown"


def edit_select_all(control: int) -> str:
    """Ctrl+A d'un champ Edit : EM_SETSEL(0, -1), sélection relue (EM_GETSEL)."""
    if not is_class(control, EDIT_CLASSES):
        raise MessageError("Pas un champ Edit Win32.")
    send(control, EM_SETSEL, 0, -1)
    length = send(control, WM_GETTEXTLENGTH) or 0
    sel = send(control, EM_GETSEL)
    if sel is None or ((sel >> 16) & 0xFFFF) < min(length, 0xFFFF):
        raise MessageError("Sélection non relue.")
    return "em_setsel"


def is_window(hwnd: int) -> bool:
    return bool(hwnd) and bool(_IsWindow(hwnd))
