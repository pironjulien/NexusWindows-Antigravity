"""Contrôles Win32 natifs pilotés par messages directs : en arrière-plan, sans souris, sans clavier, sans focus.

Mesures de référence (NexusWindows/claude bench/RESULTS.md, 11 octobre 2026) reprises ici :
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


# --- Souris et raccourcis par messages (recette commune, banc NexusWindows du 21/10/2026) ------------------------
# Mesuré par le banc commun (NexusWindows/commun/benchmarks/windows) et NexusClaude (bench/RESULTS.md) : clic et molette postés à
# l'enfant le plus profond sous le point ✓ en Win32 et WinForms (effet émis par l'application, premier plan intact) ;
# WPF ignore la souris postée ; raccourcis Ctrl/Alt postés ✓ en Win32 et WinForms si l'état clavier du fil cible est
# simulé le temps du traitement (AttachThreadInput au seul fil de la cible, jamais à celui de Julien).
class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


_ChildWindowFromPointEx = _fn("ChildWindowFromPointEx", wintypes.HWND, wintypes.HWND, _POINT, wintypes.UINT)
_WindowFromPoint = _fn("WindowFromPoint", wintypes.HWND, _POINT)
_ScreenToClient = _fn("ScreenToClient", wintypes.BOOL, wintypes.HWND, ctypes.POINTER(_POINT))
_AttachThreadInput = _fn("AttachThreadInput", wintypes.BOOL, wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
_GetKeyboardState = _fn("GetKeyboardState", wintypes.BOOL, ctypes.c_void_p)
_SetKeyboardState = _fn("SetKeyboardState", wintypes.BOOL, ctypes.c_void_p)
_GetForegroundWindow = _fn("GetForegroundWindow", wintypes.HWND)
_GetCurrentThreadId = ctypes.WinDLL("kernel32").GetCurrentThreadId
CWP_SKIPINVISIBLE, CWP_SKIPDISABLED, CWP_SKIPTRANSPARENT = 0x0001, 0x0002, 0x0004
WM_MOUSEMOVE, WM_MOUSEWHEEL = 0x0200, 0x020A
MOUSE_MESSAGES = {  # bouton : (appui, relâché, état MK_*, double clic)
    "left": (0x0201, 0x0202, 0x0001, 0x0203),
    "right": (0x0204, 0x0205, 0x0002, 0x0206),
    "middle": (0x0207, 0x0208, 0x0010, 0x0209),
}
MESSAGE_MOUSE_FAMILIES = {"Win32", "WinForms"}
# Clic par coordonnées posté : aussi Chromium/Electron recouvert (mesuré par NexusClaude, banc commun du 21/10 : effet
# émis, premier plan intact) ; pas la molette, que Chromium ignore par message.
MESSAGE_CLICK_FAMILIES = MESSAGE_MOUSE_FAMILIES | {"Chromium"}
MESSAGE_SHORTCUT_FAMILIES = {"Win32", "WinForms"}


def _to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    p = _POINT(x, y)
    _ScreenToClient(hwnd, ctypes.byref(p))
    return p.x, p.y


_GetWindowDpiAwarenessContext = _fn("GetWindowDpiAwarenessContext", ctypes.c_void_p, wintypes.HWND)
_GetAwarenessFromDpiAwarenessContext = _fn("GetAwarenessFromDpiAwarenessContext", ctypes.c_int, ctypes.c_void_p)
_GetDpiFromDpiAwarenessContext = _fn("GetDpiFromDpiAwarenessContext", wintypes.UINT, ctypes.c_void_p)
_MonitorFromWindow = _fn("MonitorFromWindow", wintypes.HMONITOR, wintypes.HWND, wintypes.DWORD)
_GetDpiForMonitor = ctypes.WinDLL("shcore").GetDpiForMonitor
_GetDpiForMonitor.restype = ctypes.c_long
_GetDpiForMonitor.argtypes = [
    wintypes.HMONITOR,
    ctypes.c_int,
    ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(wintypes.UINT),
]


def _message_point(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Point client d'un message souris posté, dans le repère où la fenêtre le lit : pixels logiques pour une fenêtre
    non adaptée au DPI (ou au DPI système), car Windows ne convertit jamais un message posté (banc commun du 22/10 : à
    125 %, le double clic sur la 3e ligne d'une ListBox WinForms tombait une ligne plus bas)."""
    cx, cy = _to_client(hwnd, x, y)
    context = _GetWindowDpiAwarenessContext(hwnd)
    awareness = _GetAwarenessFromDpiAwarenessContext(context) if context else -1
    if awareness not in (0, 1):  # par moniteur, ou contexte illisible (-1) : pixels réels
        return cx, cy
    # Fenêtre virtualisée : GetDpiForWindow rend 96 (ou le DPI système) ; le DPI réel est celui de son moniteur.
    drawn = (_GetDpiFromDpiAwarenessContext(context) or 96) if awareness == 1 else 96
    monitor = _MonitorFromWindow(hwnd, 2)
    dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
    if not monitor or _GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) != 0 or not dpi_x.value:
        return cx, cy
    scale = dpi_x.value / drawn
    return (cx, cy) if abs(scale - 1.0) < 0.01 else (round(cx / scale), round(cy / scale))


def _lparam_xy(x: int, y: int) -> int:
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def deepest_child_at(top: int, x: int, y: int) -> int:
    """Fenêtre enfant la plus profonde sous le point écran (x, y), visible et active (sinon `top`)."""
    current = top
    for _ in range(32):
        cx, cy = _to_client(current, x, y)
        flags = CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT
        child = int(_ChildWindowFromPointEx(current, _POINT(cx, cy), flags) or 0)
        if not child or child == current:
            break
        current = child
    return current


class PartialSendError(MessageError):
    """Une partie de l'entrée a été postée avant l'échec : issue INCONNUE. Jamais de repli (physique ou autre
    technique) par-dessus, il referait l'action (relecture de Codex, 21/10)."""


class _Sender:
    """Postes successifs d'une même action : un échec après le premier poste devient PartialSendError."""

    def __init__(self) -> None:
        self.sent = 0

    def post(self, hwnd: int, msg: int, wparam: int, lparam: int) -> None:
        try:
            post(hwnd, msg, wparam, lparam)
        except MessageError as error:
            if self.sent:
                raise PartialSendError(f"envoi partiel ({self.sent} messages postés) : {error}") from error
            raise
        self.sent += 1


def post_click(top: int, x: int, y: int, button: str = "left", count: int = 1) -> int:
    """Clic par messages à l'enfant le plus profond sous (x, y) écran, sans souris réelle. Rend le HWND visé.
    Double clic : séquence complète DOWN, UP, DBLCLK, UP."""
    target = deepest_child_at(top, x, y)
    # WinForms ne lève DoubleClick que si la fenêtre au point (hit-test) est le contrôle lui-même : point recouvert, double clic posté sans effet (banc commun du 22/10, les trois outils) ; rien n'est envoyé, la technique suivante (vraie souris, premier plan bref) s'en charge si elle est permise.
    if (
        count >= 2
        and class_name(target).lower().startswith("windowsforms")
        and int(_WindowFromPoint(_POINT(x, y)) or 0) != target
    ):
        raise MessageError("double clic WinForms à un point recouvert : sans effet par messages, rien n'a été envoyé")
    down, up, mk, dbl = MOUSE_MESSAGES[button]
    lp = _lparam_xy(*_message_point(target, x, y))
    sender = _Sender()
    sender.post(target, WM_MOUSEMOVE, 0, lp)
    for i in range(count):
        sender.post(target, dbl if i == 1 else down, mk, lp)
        sender.post(target, up, 0, lp)
    return target


WM_MOUSEHWHEEL = 0x020E


def post_wheel(top: int, x: int, y: int, delta: int, delta_x: int = 0) -> int:
    """Molette par message : WM_MOUSEWHEEL (et WM_MOUSEHWHEEL pour delta_x) en coordonnées ÉCRAN."""
    target = deepest_child_at(top, x, y)
    sender = _Sender()
    if delta:
        sender.post(target, WM_MOUSEWHEEL, (delta & 0xFFFF) << 16, _lparam_xy(x, y))
    if delta_x:
        sender.post(target, WM_MOUSEHWHEEL, (delta_x & 0xFFFF) << 16, _lparam_xy(x, y))
    return target


VK_MENU = 0x12
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_OpenProcess = _kernel32.OpenProcess
_OpenProcess.restype = wintypes.HANDLE
_OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_CloseHandle = _kernel32.CloseHandle
_WaitForInputIdle = ctypes.WinDLL("user32", use_last_error=True).WaitForInputIdle
_WaitForInputIdle.restype = wintypes.DWORD
_WaitForInputIdle.argtypes = (wintypes.HANDLE, wintypes.DWORD)
SYNCHRONIZE, PROCESS_QUERY_LIMITED_INFORMATION = 0x00100000, 0x1000


def _wait_input_idle(hwnd: int, timeout_ms: int) -> None:
    """Attend que le processus de la fenêtre ait traité ses entrées en file (WaitForInputIdle), au plus timeout_ms."""
    pid = wintypes.DWORD()
    _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = _OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return
    try:
        _WaitForInputIdle(handle, timeout_ms)
    finally:
        _CloseHandle(handle)


def post_shortcut(target: int, vk: int, modifiers: list[int], hold_s: float = 0.15) -> str:
    """Raccourci Ctrl/Maj par messages : état clavier du fil de la cible simulé le temps du traitement, touches
    postées, état restauré seulement quand la cible a traité ses entrées (WaitForInputIdle, au moins hold_s), pour
    que Ctrl+S ne devienne jamais S. Alt refusé (les raccourcis système attendent WM_SYSKEYDOWN : rien n'est envoyé).
    Refusé si la cible partage le fil du premier plan (celui de Julien)."""
    if VK_MENU in modifiers:
        raise MessageError(
            "Raccourci avec Alt : pas de technique d'arrière-plan sûre (WM_SYSKEYDOWN), rien n'a été envoyé."
        )
    thread = _GetWindowThreadProcessId(target, None)
    fg = int(_GetForegroundWindow() or 0)
    if not thread or (fg and _GetWindowThreadProcessId(fg, None) == thread):
        raise MessageError("Fil de la cible = fil du premier plan : état clavier simulé refusé.")
    own = _GetCurrentThreadId()
    if not _AttachThreadInput(own, thread, True):
        raise MessageError("AttachThreadInput refusé.")
    # État lu une fois attaché (file d'entrée partagée) : c'est celui de la cible, restauré à l'identique ensuite.
    saved = (ctypes.c_ubyte * 256)()
    sender = _Sender()
    try:
        _GetKeyboardState(ctypes.byref(saved))
        state = (ctypes.c_ubyte * 256)(*saved)
        for m in modifiers:
            state[m] = 0x80
        _SetKeyboardState(ctypes.byref(state))
        for m in modifiers:
            sender.post(target, WM_KEYDOWN, m, _key_lparam(m, False))
        sender.post(target, WM_KEYDOWN, vk, _key_lparam(vk, False))
        sender.post(target, WM_KEYUP, vk, _key_lparam(vk, True))
        for m in reversed(modifiers):
            sender.post(target, WM_KEYUP, m, _key_lparam(m, True))
        started = time.monotonic()
        _wait_input_idle(target, 2000)  # touches traitées pendant que l'état est posé
        remaining = hold_s - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)
    finally:
        _SetKeyboardState(ctypes.byref(saved))
        _AttachThreadInput(own, thread, False)
    return "wm_keydown_modifiers"


# --- Activation simulée de Chromium (recette commune, mesurée par NexusClaude le 15/10, banc commun du 21/10) ------
# Chromium jette le clavier d'une fenêtre inactive, mais tient son état d'activation des MESSAGES qu'il reçoit
# (WM_NCACTIVATE, WM_ACTIVATE), pas de Windows : ces messages envoyés à sa seule fenêtre, sans activation réelle,
# suffisent pour que WM_CHAR et WM_KEYDOWN produisent des événements de confiance (input, keydown) dans <input>,
# <select> et contenteditable ; Ctrl simulé par l'état clavier du fil. Premier plan de Julien intact. Désactivation
# POSTÉE en sortie : traitée après les caractères encore en file.
WM_ACTIVATE, WM_NCACTIVATE, WM_CHAR = 0x0006, 0x0086, 0x0102
CHROMIUM_TOP_CLASS = "Chrome_WidgetWin_"
SIM_MODIFIERS_HOLD_S = 0.5  # Chromium occulté lit l'état clavier tard (mesuré)


def is_chromium_top(hwnd: int) -> bool:
    return bool(hwnd) and class_name(hwnd).startswith(CHROMIUM_TOP_CLASS) and root_of(hwnd) in (0, hwnd)


class simulated_activation:
    """Bloc où la fenêtre Chromium `top` se croit active sans l'être. Refus (MessageError) si elle est réellement
    au premier plan (la frappe ordinaire s'applique) ou si ce n'est pas une fenêtre Chromium de premier niveau."""

    def __init__(self, top: int) -> None:
        self.top = top

    def __enter__(self) -> simulated_activation:
        if not is_chromium_top(self.top):
            raise MessageError("Pas une fenêtre Chromium de premier niveau : activation simulée inapplicable.")
        if root_of(int(_GetForegroundWindow() or 0)) == self.top:
            raise MessageError("Fenêtre au premier plan : activation simulée inutile.")
        if send(self.top, WM_NCACTIVATE, 1, 0) is None or send(self.top, WM_ACTIVATE, 1, 0) is None:
            raise MessageError("La fenêtre ne répond pas aux messages d'activation.")
        return self

    def __exit__(self, *exc: object) -> None:
        if root_of(int(_GetForegroundWindow() or 0)) != self.top:
            try:
                post(self.top, WM_ACTIVATE, 0, 0)
                post(self.top, WM_NCACTIVATE, 0, 0)
            except MessageError:
                pass
        time.sleep(0.03)


def post_chars(target: int, text: str) -> int:
    """Texte par WM_CHAR (unités UTF-16), sans saut de ligne (il passerait outre la confirmation d'Entrée : refusé,
    rien n'est envoyé). Un échec après le premier caractère : PartialSendError. Rend le nombre de caractères."""
    if "\n" in text or "\r" in text:
        raise MessageError("Saut de ligne : la frappe sans activation ne l'envoie pas (confirmation d'Entrée).")
    sender = _Sender()
    for ch in text:
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):
            sender.post(target, WM_CHAR, int.from_bytes(data[i : i + 2], "little"), 1)
    return len(text)


# --- Tk en arrière-plan (recette de NexusClaude du 23/10, relue par Codex en six tours, feu vert c97a651) ----------
# Tk lit l'état des boutons et de Ctrl par GetKeyState au traitement (TkWinGetModifierState) : un clic posté sans
# bouton « enfoncé » est ignoré. Pression ENVOYÉE avec le bouton simulé pour le seul fil de Tk, par un fil auxiliaire
# qui possède pression ET relâchement (le délai de SendMessageTimeout n'est pas garanti sous AttachThreadInput) ; une
# seule pression simulée à la fois par application ; relâchement sans réponse : application fermée aux pressions
# simulées tant que sa fenêtre existe. Clavier : Tk ne route les touches qu'à sa fenêtre focalisée, qu'il tient de
# WM_SETFOCUS (FocusIn) : WM_SETFOCUS envoyé (jamais WM_ACTIVATE), touches postées, WM_KILLFOCUS posté.
import threading  # noqa: E402

_GetAsyncKeyState = _fn("GetAsyncKeyState", ctypes.c_short, ctypes.c_int)
BUTTON_VK = {"left": 0x01, "right": 0x02, "middle": 0x04}
HELD_SEND_S = 1.0
_PENDING_PRESS: set[int] = set()  # fils GUI dont une pression simulée n'est pas soldée
_PENDING_LOCK = threading.Lock()
WM_SETFOCUS, WM_KILLFOCUS = 0x0007, 0x0008


def _thread_of(hwnd: int) -> int:
    return int(_GetWindowThreadProcessId(hwnd, None) or 0)


def _in_front(thread: int) -> bool:
    fg = int(_GetForegroundWindow() or 0)
    return bool(fg) and _thread_of(fg) == thread


class _simulated_keys:
    """Touches `vks` « enfoncées » pour le seul fil de `target` (file attachée, jamais celle du premier plan). En
    sortie, seules ces touches reprennent leur valeur d'avant (leur état physique si l'utilisateur a pris la fenêtre) ;
    lecture impossible : l'état d'avant entier."""

    def __init__(self, target: int, vks: list[int]) -> None:
        self.target, self.vks = target, vks
        self.thread = _thread_of(target)
        self.own = _GetCurrentThreadId()
        self.saved = (ctypes.c_ubyte * 256)()
        self.attached = False

    def __enter__(self) -> _simulated_keys:
        if not self.thread or _in_front(self.thread):
            raise MessageError("Fil de la cible = fil du premier plan : état simulé refusé.")
        if not _AttachThreadInput(self.own, self.thread, True):
            raise MessageError("AttachThreadInput refusé.")
        self.attached = True
        _GetKeyboardState(ctypes.byref(self.saved))
        state = (ctypes.c_ubyte * 256)(*self.saved)
        for vk in self.vks:
            state[vk] = 0x80
        _SetKeyboardState(ctypes.byref(state))
        return self

    def __exit__(self, *exc: object) -> None:
        if not self.attached:
            return
        try:
            now = (ctypes.c_ubyte * 256)()
            if not _GetKeyboardState(ctypes.byref(now)):
                ctypes.memmove(now, self.saved, 256)
            taken = _in_front(self.thread)
            for vk in self.vks:
                if taken:
                    now[vk] = (0x80 if _GetAsyncKeyState(vk) & 0x8000 else 0) | (self.saved[vk] & 1)
                else:
                    now[vk] = self.saved[vk]
            _SetKeyboardState(ctypes.byref(now))
        finally:
            _AttachThreadInput(self.own, self.thread, False)
            self.attached = False


def _held_press(target: int, vk: int, down: int, up: int, mk: int, lparam: int, check=None) -> None:
    thread = _thread_of(target)
    with _PENDING_LOCK:
        if thread in _PENDING_PRESS:
            raise MessageError("Pression simulée précédente non soldée dans cette application : rien n'a été envoyé.")
        _PENDING_PRESS.add(thread)
    abandoned, done = threading.Event(), threading.Event()
    outcome: list[str] = []
    raised: list[BaseException] = []
    state = {"sent": False}

    def run() -> None:
        pressed = False
        try:
            if abandoned.is_set():
                return
            with _simulated_keys(target, [vk]):
                if abandoned.is_set():
                    return
                if check is not None:
                    check()  # arrêt d'urgence relu juste avant la pression (relecture de Codex du 24/10)
                pressed = True
                state["sent"] = True
                if send(target, down, mk, lparam) is None:
                    outcome.append("pression sans réponse en 1 s")
        except MessageError as error:
            outcome.append(str(error))
        except BaseException as error:  # noqa: BLE001 - rendu tel quel au fil de travail (arrêt d'urgence compris)
            raised.append(error)
        finally:
            try:
                if pressed:  # relâchement de nettoyage, état déjà restauré : toujours envoyé
                    if send(target, up, 0, lparam) is None:
                        outcome.append("relâchement sans réponse en 1 s")
                        done.set()
                        while is_window(target):  # jamais prouvé soldé : fil fermé aux pressions simulées
                            time.sleep(1.0)
            finally:
                with _PENDING_LOCK:
                    _PENDING_PRESS.discard(thread)
                done.set()

    threading.Thread(target=run, name="agy-held-press", daemon=True).start()
    deadline = time.monotonic() + HELD_SEND_S
    try:
        while not done.wait(0.02):
            if check is not None:
                check()  # arrêt d'urgence : abandon, l'auxiliaire qui n'a rien envoyé n'envoie plus rien
            if time.monotonic() >= deadline:
                raise PartialSendError("pression sans réponse en 1 s : issue inconnue")
    except BaseException as error:
        abandoned.set()
        if state["sent"]:
            error.partial_input = True  # type: ignore[attr-defined]  # pression déjà partie : issue inconnue
        raise
    if raised:
        if state["sent"]:
            raised[0].partial_input = True  # type: ignore[attr-defined]  # pression déjà partie : issue inconnue
        raise raised[0]
    if outcome:
        if state["sent"]:
            raise PartialSendError(outcome[0])
        raise MessageError(outcome[0])


def tk_click(top: int, x: int, y: int, button: str = "left", count: int = 1, check=None) -> int:
    """Clic Tk à (x, y) écran, en arrière-plan : survol envoyé, puis pour chaque pression le bouton simulé pour le seul
    fil de Tk. check() : arrêt d'urgence, avant chaque pression. Après le survol, toute erreur est PartialSendError
    (issue inconnue, jamais de vraie souris par-dessus)."""
    target = deepest_child_at(top, x, y)
    if _in_front(_thread_of(target)):
        raise MessageError("Fenêtre Tk au premier plan : rien de simulé.")
    if _thread_of(target) in _PENDING_PRESS:
        raise MessageError("Pression simulée précédente non soldée dans cette application : rien n'a été envoyé.")
    down, up, mk, dbl = MOUSE_MESSAGES[button]
    lp = _lparam_xy(*_message_point(target, x, y))
    if not is_window(target) or send(target, WM_MOUSEMOVE, 0, lp) is None:
        raise MessageError("survol sans réponse : rien d'autre n'a été envoyé")
    try:
        for i in range(count):
            try:
                if check is not None:
                    check()
                _held_press(target, BUTTON_VK[button], dbl if i == 1 else down, up, mk, lp, check)
            except BaseException as error:
                if i:  # une pression précédente est partie : issue inconnue, identité de l'erreur conservée
                    error.partial_input = True  # type: ignore[attr-defined]
                raise
    except PartialSendError:
        raise
    except MessageError as error:
        raise PartialSendError(f"clic Tk interrompu après le survol : {error}") from error
    return target


def tk_keys(top: int, vk: int, modifiers: list[int], check=None) -> str:
    """Touche ou raccourci Ctrl/Maj vers une fenêtre Tk sans l'activer (focus simulé). Fenêtre au premier plan, ou
    prise pendant la préparation : rien de simulé. Modificateurs simulés pour le seul fil de Tk, seules ces touches
    restaurées en sortie (_simulated_keys). Envois comptés de bout en bout, WM_KILLFOCUS compris : après le premier
    accepté, toute erreur est PartialSendError (issue inconnue, jamais le vrai clavier par-dessus). Alt refusé."""
    if VK_MENU in modifiers:
        raise MessageError("Raccourci avec Alt : pas de technique d'arrière-plan sûre, rien n'a été envoyé.")
    thread = _thread_of(top)
    if _in_front(thread):
        raise MessageError("Fenêtre Tk au premier plan : rien de simulé.")
    if send(top, WM_SETFOCUS, 0, 0) is None:
        post(top, WM_KILLFOCUS, 0, 0)
        raise MessageError("Tk ne répond pas à WM_SETFOCUS : aucune touche envoyée")
    sender = _Sender()
    try:
        if check is not None:
            check()
        if _in_front(thread):
            raise MessageError("Fenêtre Tk prise par l'utilisateur pendant la préparation : aucune touche envoyée")
        with _simulated_keys(top, modifiers):
            for m in modifiers:
                sender.post(top, WM_KEYDOWN, m, _key_lparam(m, False))
            sender.post(top, WM_KEYDOWN, vk, _key_lparam(vk, False))
            sender.post(top, WM_KEYUP, vk, _key_lparam(vk, True))
            for m in reversed(modifiers):
                sender.post(top, WM_KEYUP, m, _key_lparam(m, True))
            if modifiers:  # état tenu le temps du traitement (pas un accusé : l'effet reste relu)
                started = time.monotonic()
                _wait_input_idle(top, 2000)
                remaining = SIM_MODIFIERS_HOLD_S - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)
    except MessageError as error:
        if sender.sent and not isinstance(error, PartialSendError):
            raise PartialSendError(f"touches Tk interrompues après envoi : {error}") from error
        raise
    finally:
        if not _in_front(thread):
            try:
                post(top, WM_KILLFOCUS, 0, 0)
            except MessageError as error:
                if sender.sent:
                    raise PartialSendError(f"touches envoyées, focus simulé non défait : {error}") from error
    return "tk_focus_keys"


# --- Barre de défilement native (tk.Scrollbar), recette de NexusClaude du 23/10 ------------------------------------
WM_HSCROLL, WM_VSCROLL = 0x0114, 0x0115
SB_LINEUP, SB_LINEDOWN, SB_ENDSCROLL = 0, 1, 8
SB_CTL, SIF_RANGE, SIF_PAGE, SIF_POS = 2, 0x1, 0x2, 0x4
SBS_VERT = 0x1


class _SCROLLINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("fMask", ctypes.c_uint), ("nMin", ctypes.c_int), ("nMax", ctypes.c_int),
                ("nPage", ctypes.c_uint), ("nPos", ctypes.c_int), ("nTrackPos", ctypes.c_int)]  # fmt: skip


_GetScrollInfo = _fn("GetScrollInfo", wintypes.BOOL, wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
_GetWindowRectRaw = _fn("GetWindowRect", wintypes.BOOL, wintypes.HWND, ctypes.c_void_p)


def _rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    _GetWindowRectRaw(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def scroll_bar_state(bar: int) -> tuple[int, int, int, int] | None:
    info = _SCROLLINFO(ctypes.sizeof(_SCROLLINFO), SIF_RANGE | SIF_PAGE | SIF_POS)
    if not _GetScrollInfo(bar, SB_CTL, ctypes.byref(info)):
        return None
    return info.nMin, info.nMax, info.nPage, info.nPos


def scroll_bar_beside(top: int, x: int, y: int, vertical: bool) -> int:
    """Barre native visible du bon sens, sœur du widget sous le point, COLLÉE à lui sur toute sa hauteur (largeur),
    et collée à aucun autre widget frère ; exactement une, sinon 0 (rien deviné)."""
    under = deepest_child_at(top, x, y)
    if not under or class_name(under).lower() == "scrollbar":
        return 0
    parent = int(_GetParent(under) or 0)
    siblings = [h for h in child_windows(top) if int(_GetParent(h) or 0) == parent and _IsWindowVisible(h)]

    def touches(bar: tuple[int, int, int, int], box: tuple[int, int, int, int], whole: bool) -> bool:
        if vertical:
            side = abs(bar[0] - box[2]) <= 4 or abs(box[0] - bar[2]) <= 4
            span = (bar[1] <= box[1] + 4 and bar[3] >= box[3] - 4) if whole else (bar[1] < box[3] and box[1] < bar[3])
        else:
            side = abs(bar[1] - box[3]) <= 4 or abs(box[1] - bar[3]) <= 4
            span = (bar[0] <= box[0] + 4 and bar[2] >= box[2] - 4) if whole else (bar[0] < box[2] and box[0] < bar[2])
        return side and span

    found = []
    for bar in siblings:
        if class_name(bar).lower() != "scrollbar" or bool(style(bar) & SBS_VERT) != vertical:
            continue
        r = _rect(bar)
        if not touches(r, _rect(under), True):
            continue
        others = [h for h in siblings if h not in (bar, under) and class_name(h).lower() != "scrollbar"]
        if any(touches(r, _rect(h), False) for h in others):
            continue
        found.append(bar)
    return found[0] if len(found) == 1 else 0


def post_scroll_lines(bar: int, vertical: bool, forward: bool, lines: int) -> None:
    parent = int(_GetParent(bar) or 0)
    msg = WM_VSCROLL if vertical else WM_HSCROLL
    sender = _Sender()
    for _ in range(lines):
        sender.post(parent, msg, SB_LINEDOWN if forward else SB_LINEUP, bar)
    sender.post(parent, msg, SB_ENDSCROLL, bar)


# --- Molette Tk d'une fenêtre entièrement recouverte (recette de NexusWindows Claude 3.7.0, 27/10, relue cinq fois par
# Codex) : Tk renvoie la molette à la fenêtre visible AU POINT du message (tkWinX.c) ; recouverte, elle est perdue. La
# fenêtre, entièrement cachée, est déplacée au-delà du bureau virtuel le temps de la molette, puis remise et relue.
_GetWindow = _fn("GetWindow", wintypes.HWND, wintypes.HWND, wintypes.UINT)
_IsIconic = _fn("IsIconic", wintypes.BOOL, wintypes.HWND)
_IsZoomed = _fn("IsZoomed", wintypes.BOOL, wintypes.HWND)
_SetWindowPos = _fn(
    "SetWindowPos", wintypes.BOOL, wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.UINT,
)  # fmt: skip
_GetSystemMetrics = _fn("GetSystemMetrics", ctypes.c_int, ctypes.c_int)
_GetDpiForWindow = _fn("GetDpiForWindow", wintypes.UINT, wintypes.HWND)
_GetWindowRgnBox = _fn("GetWindowRgnBox", ctypes.c_int, wintypes.HWND, ctypes.c_void_p)
_DwmGetWindowAttribute = ctypes.WinDLL("dwmapi").DwmGetWindowAttribute
_DwmGetWindowAttribute.restype = ctypes.c_long
_DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
GW_HWNDPREV, GWL_EXSTYLE, DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 3, -20, 9, 14
SM_XVIRTUALSCREEN, SM_CXVIRTUALSCREEN = 76, 78
SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
# Styles qui ne prouvent pas l'opacité : translucide (LAYERED), traversée (TRANSPARENT), composition sans bitmap
# (NOREDIRECTIONBITMAP : client possiblement entièrement transparent).
NOT_OPAQUE = 0x00000020 | 0x00080000 | 0x00200000
OFFSCREEN_SETTLE_S, OFFSCREEN_HOLD_S = 0.15, 0.3
Box = tuple[int, int, int, int]


class WindowNotRestored(RuntimeError):
    """La fenêtre déplacée n'a pas pu revenir à sa place : échec de l'action, jamais une issue simplement incertaine
    (ni MessageError, donc aucune autre technique ensuite)."""


def _frame(hwnd: int) -> Box:
    """Cadre visible (DWM, sans l'ombre) ; à défaut, le rectangle de la fenêtre."""
    r = wintypes.RECT()
    if _DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) == 0:
        return r.left, r.top, r.right, r.bottom
    return _rect(hwnd)


def _cloaked(hwnd: int) -> bool:
    value = wintypes.DWORD()
    size = ctypes.sizeof(value)
    return _DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), size) == 0 and bool(value.value)


def _monitor_dpi(hwnd: int) -> int:
    """DPI effectif du moniteur de la fenêtre ; illisible : 0."""
    monitor = _MonitorFromWindow(hwnd, 2)
    dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
    if not monitor or _GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) != 0:
        return 0
    return int(dpi_x.value)


def _corner(hwnd: int) -> int:
    """Rayon majoré des coins arrondis DWM : 8 px à 100 %, linéaire avec l'échelle du MONITEUR (GetDpiForWindow rend
    96 pour une application non adaptée au DPI), + 2 px ; échelle illisible : 0 (la fenêtre ne couvre rien)."""
    dpi = _monitor_dpi(hwnd)
    return -(-8 * max(dpi, int(_GetDpiForWindow(hwnd))) // 96) + 2 if dpi else 0


def _minus(box: Box, cut: Box) -> list[Box]:
    """box privé de cut : jusqu'à quatre rectangles."""
    left, top, right, bottom = box
    cl, ct, cr, cb = cut
    if cl >= right or cr <= left or ct >= bottom or cb <= top:
        return [box]
    out = []
    if ct > top:
        out.append((left, top, right, ct))
    if cb < bottom:
        out.append((left, cb, right, bottom))
    mid_top, mid_bottom = max(top, ct), min(bottom, cb)
    if cl > left:
        out.append((left, mid_top, cl, mid_bottom))
    if cr < right:
        out.append((cr, mid_top, right, mid_bottom))
    return out


def fully_covered(top: int) -> bool:
    """Aucun pixel de la fenêtre n'est visible : son cadre privé du cadre de chaque fenêtre au-dessus d'elle (ordre z
    réel). Seules comptent les fenêtres visibles, non réduites, non masquées par DWM, sans style NOT_OPAQUE ni région
    SetWindowRgn, coins arrondis DWM exclus à l'échelle de leur moniteur ; un seul pixel visible suffit à refuser."""
    left = [_frame(top)]
    above = int(_GetWindow(top, GW_HWNDPREV) or 0)
    while above and left:
        if (
            _IsWindowVisible(above)
            and not _IsIconic(above)
            and not _cloaked(above)
            and not _GetWindowLongW(above, GWL_EXSTYLE) & NOT_OPAQUE
            and not _GetWindowRgnBox(above, ctypes.byref(wintypes.RECT()))
            and (k := _corner(above))
        ):
            cl, ct, cr, cb = _frame(above)
            for cover in ((cl + k, ct, cr - k, cb), (cl, ct + k, cr, cb - k)):
                left = [piece for box in left for piece in _minus(box, cover)]
        above = int(_GetWindow(above, GW_HWNDPREV) or 0)
    return not left


def tk_wheel_offscreen(top: int, x: int, y: int, delta: int, horizontal: bool = False, check=None) -> int:
    """Molette Tk d'une fenêtre ENTIÈREMENT recouverte : déplacée au-delà du bureau virtuel (sans activation ni
    changement d'ordre), molette postée au MÊME contrôle (relevé avant le déplacement), retour relu au rectangle entier
    avec un second essai. Refus, rien envoyé (MessageError) : fenêtre agrandie, réduite ou en partie visible, autre
    contrôle au point une fois dehors, fenêtre ramenée devant par l'utilisateur. Fenêtre non remise : WindowNotRestored.
    Le délai tenu dehors n'est pas un accusé de traitement ; event.x/y de Tk viennent du curseur (GetMessagePos)."""
    if _IsZoomed(top) or _IsIconic(top):
        raise MessageError("Fenêtre agrandie ou réduite : jamais déplacée, rien n'a été envoyé.")
    if not fully_covered(top):
        raise MessageError("Fenêtre en partie visible : jamais déplacée hors écran, rien n'a été envoyé.")
    place = _rect(top)
    expected = deepest_child_at(top, x, y)
    if not expected or not is_window(expected):
        raise MessageError("Aucun contrôle sous le point : rien n'a été envoyé.")
    right = _GetSystemMetrics(SM_XVIRTUALSCREEN) + _GetSystemMetrics(SM_CXVIRTUALSCREEN)
    dx = right + 50 - place[0]
    flags = SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
    thread = _thread_of(top)
    if check:
        check()  # arrêt d'urgence : la fenêtre n'a pas bougé
    posted = False
    failure: BaseException | None = None
    try:
        if not _SetWindowPos(top, None, place[0] + dx, place[1], 0, 0, flags):
            raise MessageError("Fenêtre impossible à déplacer : rien n'a été envoyé.")
        time.sleep(OFFSCREEN_SETTLE_S)
        if deepest_child_at(top, x + dx, y) != expected or int(_WindowFromPoint(_POINT(x + dx, y)) or 0) != expected:
            raise MessageError("Dehors, le point ne tombe pas sur le même contrôle : rien n'a été envoyé.")
        if check:
            check()
        if _in_front(thread):  # seul un Alt+Tab peut l'atteindre dehors
            raise MessageError("Fenêtre ramenée au premier plan entre-temps : rien n'a été envoyé.")
        msg = WM_MOUSEHWHEEL if horizontal else WM_MOUSEWHEEL
        post(expected, msg, (delta & 0xFFFF) << 16, _lparam_xy(x + dx, y))
        posted = True
        time.sleep(OFFSCREEN_HOLD_S)
    except BaseException as error:  # noqa: BLE001  (rendue après le retour de la fenêtre)
        failure = error
    back = bool(_SetWindowPos(top, None, place[0], place[1], 0, 0, flags)) and _rect(top) == place
    if not back:
        time.sleep(0.05)
        width, height = place[2] - place[0], place[3] - place[1]
        back = bool(_SetWindowPos(top, None, place[0], place[1], width, height, SWP_NOZORDER | SWP_NOACTIVATE))
        back = back and _rect(top) == place
    if not back:
        sent = "molette envoyée, effet inconnu" if posted else "rien n'a été envoyé"
        raise WindowNotRestored(
            f"Fenêtre impossible à remettre exactement en ({place[0]}, {place[1]}) : {sent}. La regarder avant tout."
        ) from failure
    if failure is not None:
        raise failure
    return expected


def overlapped(top: int) -> bool:
    """Une autre fenêtre visible au-dessus de `top` (ordre z réel) chevauche son cadre, quelle que soit son opacité :
    une copie de l'écran à cet endroit montrerait au moins en partie autre chose que `top`."""
    left, top_y, right, bottom = _frame(top)
    above = int(_GetWindow(top, GW_HWNDPREV) or 0)
    while above:
        if _IsWindowVisible(above) and not _IsIconic(above) and not _cloaked(above):
            al, at, ar, ab = _frame(above)
            if al < right and ar > left and at < bottom and ab > top_y:
                return True
        above = int(_GetWindow(above, GW_HWNDPREV) or 0)
    return False
