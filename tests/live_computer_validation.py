#!/usr/bin/env python3
"""Validation réelle du pilotage du bureau (test.ps1 -Full), sur des fenêtres de test créées ici et fermées à la fin.

Fenêtres de test, affichées SANS activation et placées derrière les fenêtres de Julien :
- Win32 natif (Python ctypes, processus à part) : bouton, case, champ, liste déroulante, liste, menu « Fichier » ;
- WinForms (Windows PowerShell, Add-Type C#, ShowWithoutActivation) : bouton, case, champ, liste déroulante, liste ;
- formulaires WinForms et WPF (tests/desktop_fixtures.py) pilotés par le vrai serveur MCP comme Gemini le 16/10 :
  lot naïf (box_2d, Ctrl+A, saisie sans cible) fait en arrière-plan et relu, même lot renvoyé sans regarder refusé,
  débloqué par un regard ; raccourci Ctrl refusé en clair sur WPF.
Chaque contrôle met à jour une étiquette quand l'APPLICATION reçoit la notification (BN_CLICKED, EN_CHANGE,
CBN_SELCHANGE…) : l'effet est relu dans l'application elle-même, pas seulement dans l'état du contrôle.

Vérifié : chaque action en arrière-plan (technique attendue, `verified`, étiquette relue), postconditions `expect`
(dont `already` et l'échec honnête), aucun vol de premier plan (échantillonné toutes les 5 ms), curseur et
presse-papiers intacts, lecture UIA en un aller-retour (durée mesurée, comparée à l'ancien parcours), Raw Input actif.
Les vérifications qui exigent la vraie souris/le vrai clavier ne s'exécutent que si Julien est inactif depuis 120 s
(Raw Input) ; sinon « sautées (Julien actif) », jamais comptées comme réussies.

Code de sortie : 0 si aucune vérification n'échoue (les sautées sont listées), 1 sinon, 2 si l'environnement manque.
`--win32-fixture` : mode interne (fenêtre Win32 de test seule, HWND écrit sur la sortie standard).
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import json
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parent.parent
PHYSICAL_IDLE_S = 120.0

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = (
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
user32.CreateWindowExW.restype = wintypes.HWND
user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = LRESULT
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPCWSTR)
user32.GetDlgItem.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetDlgItem.restype = wintypes.HWND
user32.SetWindowPos.argtypes = (
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.AppendMenuW.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR)
user32.CreateMenu.restype = wintypes.HMENU
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.SetMenu.argtypes = (wintypes.HWND, wintypes.HMENU)
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE  # handle 64 bits : jamais tronqué en int

WM_DESTROY, WM_CLOSE, WM_COMMAND = 0x0002, 0x0010, 0x0111
WS_OVERLAPPEDWINDOW, WS_CHILD, WS_VISIBLE, WS_BORDER, WS_VSCROLL, WS_TABSTOP = (
    0x00CF0000,
    0x40000000,
    0x10000000,
    0x00800000,
    0x00200000,
    0x00010000,
)
BS_PUSHBUTTON, BS_AUTOCHECKBOX = 0x0, 0x3
ES_AUTOHSCROLL = 0x0080
CBS_DROPDOWNLIST = 0x0003
LBS_NOTIFY = 0x0001
BM_GETCHECK = 0x00F0
CB_ADDSTRING, CB_GETCURSEL, CB_GETLBTEXT = 0x0143, 0x0147, 0x0148
LB_ADDSTRING, LB_GETCURSEL, LB_GETTEXT = 0x0180, 0x0188, 0x0189
BN_CLICKED, EN_CHANGE, CBN_SELCHANGE, LBN_SELCHANGE = 0, 0x0300, 1, 1
MF_STRING, MF_POPUP = 0x0, 0x10
HWND_BOTTOM = wintypes.HWND(1)
SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0010, 0x0040

ID_BUTTON, ID_CHECK, ID_EDIT, ID_COMBO, ID_LIST = 101, 102, 103, 104, 105
ID_L_CLICKS, ID_L_CASE, ID_L_CHAMP, ID_L_CHOIX, ID_L_LISTE, ID_L_MENU = 201, 202, 203, 204, 205, 206
ID_MENU_MARK = 401
WIN32_TITLE = "NexusAGY validation Win32"
WINFORMS_TITLE = "NexusAGY validation WinForms"


# =============================================================================
# Fenêtre de test Win32 (processus à part)
# =============================================================================
def _text_of(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def run_win32_fixture() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass
    hinst = kernel32.GetModuleHandleW(None)
    state = {"clicks": 0}
    main: dict[str, int] = {}

    def label(ident: int, text: str) -> None:
        user32.SetWindowTextW(user32.GetDlgItem(main["hwnd"], ident), text)

    def item_text(ctrl: int, getsel: int, gettext: int) -> str:
        index = user32.SendMessageW(ctrl, getsel, 0, 0)
        if index < 0:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        user32.SendMessageW(ctrl, gettext, index, ctypes.addressof(buf))
        return buf.value

    def proc(hwnd, msg, wparam, lparam):
        if msg == WM_COMMAND:
            ident, code = wparam & 0xFFFF, (wparam >> 16) & 0xFFFF
            if ident == ID_BUTTON and code == BN_CLICKED:
                state["clicks"] += 1
                label(ID_L_CLICKS, f"Clics : {state['clicks']}")
            elif ident == ID_CHECK and code == BN_CLICKED:
                checked = user32.SendMessageW(user32.GetDlgItem(hwnd, ID_CHECK), BM_GETCHECK, 0, 0) == 1
                label(ID_L_CASE, f"Case : {'oui' if checked else 'non'}")
            elif ident == ID_EDIT and code == EN_CHANGE:
                label(ID_L_CHAMP, f"Champ : {_text_of(user32.GetDlgItem(hwnd, ID_EDIT))}")
            elif ident == ID_COMBO and code == CBN_SELCHANGE:
                text = item_text(user32.GetDlgItem(hwnd, ID_COMBO), CB_GETCURSEL, CB_GETLBTEXT)
                label(ID_L_CHOIX, f"Choix : {text}")
            elif ident == ID_LIST and code == LBN_SELCHANGE:
                text = item_text(user32.GetDlgItem(hwnd, ID_LIST), LB_GETCURSEL, LB_GETTEXT)
                label(ID_L_LISTE, f"Liste : {text}")
            elif ident == ID_MENU_MARK and code == 0:
                label(ID_L_MENU, "Menu : Marquer")
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wndproc = WNDPROC(proc)

    class WNDCLASSW(ctypes.Structure):
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

    user32.LoadCursorW.restype = wintypes.HANDLE
    wc = WNDCLASSW(
        lpfnWndProc=wndproc,
        hInstance=hinst,
        lpszClassName="NexusAGYLiveWin32",
        hbrBackground=wintypes.HBRUSH(16),  # COLOR_BTNFACE + 1
        hCursor=user32.LoadCursorW(None, ctypes.c_void_p(32512)),
    )
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(
        0, wc.lpszClassName, WIN32_TITLE, WS_OVERLAPPEDWINDOW, 0, 0, 10, 10, None, None, hinst, None
    )
    main["hwnd"] = hwnd

    def child(cls: str, text: str, style: int, x: int, y: int, w: int, h: int, ident: int) -> int:
        return user32.CreateWindowExW(
            0, cls, text, WS_CHILD | WS_VISIBLE | style, x, y, w, h, hwnd, wintypes.HMENU(ident), hinst, None
        )

    child("BUTTON", "Valider", BS_PUSHBUTTON | WS_TABSTOP, 20, 20, 140, 32, ID_BUTTON)
    child("BUTTON", "Option active", BS_AUTOCHECKBOX | WS_TABSTOP, 20, 64, 180, 28, ID_CHECK)
    child("EDIT", "", WS_BORDER | ES_AUTOHSCROLL | WS_TABSTOP, 20, 104, 260, 28, ID_EDIT)
    combo = child("COMBOBOX", "", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP, 20, 144, 200, 160, ID_COMBO)
    listbox = child("LISTBOX", "", LBS_NOTIFY | WS_BORDER | WS_VSCROLL | WS_TABSTOP, 20, 184, 200, 90, ID_LIST)
    for name in ("Alpha", "Bravo", "Charlie"):
        user32.SendMessageW(combo, CB_ADDSTRING, 0, ctypes.addressof(ctypes.create_unicode_buffer(name)))
    for name in ("Un", "Deux", "Trois"):
        user32.SendMessageW(listbox, LB_ADDSTRING, 0, ctypes.addressof(ctypes.create_unicode_buffer(name)))
    for i, (ident, text) in enumerate(
        (
            (ID_L_CLICKS, "Clics : 0"),
            (ID_L_CASE, "Case : non"),
            (ID_L_CHAMP, "Champ : "),
            (ID_L_CHOIX, "Choix : "),
            (ID_L_LISTE, "Liste : "),
            (ID_L_MENU, "Menu : "),
        )
    ):
        child("STATIC", text, 0, 300, 20 + 36 * i, 260, 28, ident)

    menubar = user32.CreateMenu()
    filemenu = user32.CreatePopupMenu()
    user32.AppendMenuW(filemenu, MF_STRING, ID_MENU_MARK, "&Marquer")
    user32.AppendMenuW(menubar, MF_POPUP, filemenu, "&Fichier")
    user32.SetMenu(hwnd, menubar)

    # Affichée sans activation, au fond de l'empilement : derrière les fenêtres de Julien.
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 60, 60, 620, 380, SWP_NOACTIVATE | SWP_SHOWWINDOW)
    sys.stdout.write(f"{int(hwnd)}\n")
    sys.stdout.flush()
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


# =============================================================================
# Fenêtre de test WinForms (Windows PowerShell + Add-Type)
# =============================================================================
WINFORMS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -ReferencedAssemblies System.Windows.Forms, System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public class AgyForm : Form {
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    protected override bool ShowWithoutActivation { get { return true; } }
    int clicks = 0;
    Label Lbl(string text, int y) { var l = new Label(); l.Text = text; l.Location = new Point(300, y); l.AutoSize = false; l.Size = new Size(260, 26); Controls.Add(l); return l; }
    public AgyForm() {
        Text = "__TITLE__"; StartPosition = FormStartPosition.Manual; Location = new Point(100, 100); Size = new Size(620, 380);
        var lClicks = Lbl("Clics : 0", 20); var lCase = Lbl("Case : non", 56); var lChamp = Lbl("Champ : ", 92);
        var lChoix = Lbl("Choix : ", 128); var lListe = Lbl("Liste : ", 164);
        var b = new Button(); b.Text = "Valider"; b.Location = new Point(20, 20); b.Size = new Size(140, 30);
        b.Click += (s, e) => { clicks++; lClicks.Text = "Clics : " + clicks; }; Controls.Add(b);
        var c = new CheckBox(); c.Text = "Option active"; c.Location = new Point(20, 60); c.Size = new Size(180, 26);
        c.CheckedChanged += (s, e) => { lCase.Text = "Case : " + (c.Checked ? "oui" : "non"); }; Controls.Add(c);
        var t = new TextBox(); t.Location = new Point(20, 100); t.Size = new Size(260, 26); t.Name = "champ"; t.AccessibleName = "Champ texte";
        t.TextChanged += (s, e) => { lChamp.Text = "Champ : " + t.Text; }; Controls.Add(t);
        var cb = new ComboBox(); cb.DropDownStyle = ComboBoxStyle.DropDownList; cb.Location = new Point(20, 140); cb.Size = new Size(200, 26);
        cb.Items.AddRange(new object[] { "Alpha", "Bravo", "Charlie" }); cb.AccessibleName = "Choix";
        cb.SelectedIndexChanged += (s, e) => { lChoix.Text = "Choix : " + cb.SelectedItem; }; Controls.Add(cb);
        var lb = new ListBox(); lb.Location = new Point(20, 180); lb.Size = new Size(200, 80);
        lb.Items.AddRange(new object[] { "Un", "Deux", "Trois" }); lb.AccessibleName = "Liste";
        lb.SelectedIndexChanged += (s, e) => { lListe.Text = "Liste : " + lb.SelectedItem; }; Controls.Add(lb);
    }
}
'@
$form = New-Object AgyForm
$form.add_FormClosed({ [System.Windows.Forms.Application]::ExitThread() })
$form.Show()
[void][AgyForm]::SetWindowPos($form.Handle, [IntPtr]1, 0, 0, 0, 0, 0x0013)  # HWND_BOTTOM, SWP_NOSIZE|SWP_NOMOVE|SWP_NOACTIVATE
[Console]::Out.WriteLine($form.Handle.ToInt64())
[Console]::Out.Flush()
[System.Windows.Forms.Application]::Run()
""".replace("__TITLE__", WINFORMS_TITLE)


# =============================================================================
# Validation
# =============================================================================
class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, status: str, detail: str = "", **data) -> None:
        row = {"check": name, "status": status, "detail": detail, **data}
        self.rows.append(row)
        mark = {"ok": "OK  ", "fail": "ÉCHEC", "skipped": "SAUTÉ"}[status]
        print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""), flush=True)

    def check(self, name: str, condition: bool, detail: str = "", **data) -> bool:
        self.add(name, "ok" if condition else "fail", detail, **data)
        return condition

    def run(self, name: str, func) -> None:
        try:
            func()
        except Exception as error:  # noqa: BLE001 - une vérification qui lève est un échec rapporté
            self.add(name, "fail", f"{type(error).__name__}: {error}")

    @property
    def failures(self) -> list[dict]:
        return [r for r in self.rows if r["status"] == "fail"]


def _label(top: int, text_prefix: str, cc) -> str:
    """Texte d'une étiquette de la fenêtre de test (lu par WM_GETTEXT sur ses fenêtres enfants)."""
    found: list[str] = []

    def cb(hwnd, _):
        text = cc.win32_controls.get_text(hwnd) or ""
        if text.startswith(text_prefix):
            found.append(text)
        return True

    user32.EnumChildWindows(top, cc.WNDENUMPROC(cb), 0)
    return found[0] if found else ""


def _wait_label(top: int, expected: str, cc, timeout: float = 2.0) -> str:
    prefix = expected.split(":")[0]
    deadline = time.monotonic() + timeout
    while True:
        text = _label(top, prefix, cc)
        if text.strip() == expected.strip() or time.monotonic() >= deadline:
            return text
        time.sleep(0.05)


def _element_index(state: dict, type_name: str, name: str | None = None) -> int:
    for el in state["elements"]:
        if el["type"] == type_name and (name is None or el["name"] == name):
            return el["index"]
    raise LookupError(f"{type_name} {name or ''} absent de la lecture UIA ({len(state['elements'])} éléments)")


def validate_family(cc, report: Report, fixture: Any, family: str, expected: dict[str, str]) -> None:
    hwnd = fixture.hwnd
    tag = family

    # Lecture UIA en un aller-retour (et ancien parcours pour comparaison)
    def read() -> None:
        t0 = time.perf_counter()
        state = cc.get_window_state(hwnd=hwnd, max_elements=100)
        elapsed = (time.perf_counter() - t0) * 1000
        types = {el["type"] for el in state["elements"]}
        rect = cc.get_window_rect(hwnd)
        t1 = time.perf_counter()
        cc._legacy_walk(hwnd, rect, 100, 30, 5.0, None)
        legacy_ms = (time.perf_counter() - t1) * 1000
        need = {"Button", "CheckBox", "Edit", "ComboBox", "List"}
        report.check(
            f"{tag} : lecture UIA en cache",
            state["uia"]["status"] == "ok" and need <= types and state["family"] == family,
            f"{state['uia'].get('nodes')} nœuds, {len(state['elements'])} éléments en {elapsed:.0f} ms "
            f"(UIA {state['uia'].get('duration_ms')} ms ; ancien parcours {legacy_ms:.0f} ms) ; famille {state['family']}",
            duration_ms=round(elapsed, 1),
            legacy_ms=round(legacy_ms, 1),
        )

    report.run(f"{tag} : lecture UIA en cache", read)

    def click_button() -> None:
        res = cc.act(
            steps=[{"action": "click", "target": "Valider", "expect": {"element": "Clics : 1", "exists": True}}],
            hwnd=hwnd,
            then="none",
        )
        step = res["steps"][0]
        method = step.get("result", {}).get("method")
        label = _wait_label(hwnd, "Clics : 1", cc)
        report.check(
            f"{tag} : clic du bouton en arrière-plan",
            res["success"] is True
            and step["verified"] is True
            and method == expected["button"]
            and label == "Clics : 1",
            f"technique {method}, verified={step['verified']}, étiquette « {label} »",
        )

    report.run(f"{tag} : clic du bouton en arrière-plan", click_button)

    def check_box() -> None:
        res = cc.set_checked(hwnd=hwnd, target="Option active", checked=True)
        label = _wait_label(hwnd, "Case : oui", cc)
        report.check(
            f"{tag} : case cochée en arrière-plan",
            res["success"] is True and res["method"] == expected["check"] and label == "Case : oui",
            f"technique {res['method']}, verified={res['verified']}, étiquette « {label} »",
        )
        again = cc.act(
            steps=[
                {"action": "check", "target": "Option active", "expect": {"element": "Option active", "checked": True}}
            ],
            hwnd=hwnd,
            then="none",
        )
        report.check(
            f"{tag} : postcondition déjà vraie → étape sautée",
            again["success"] is True and again["steps"][0].get("already") is True,
            f"already={again['steps'][0].get('already')}",
        )

    report.run(f"{tag} : case cochée en arrière-plan", check_box)

    def type_field() -> None:
        state = cc.get_window_state(hwnd=hwnd, max_elements=100)
        index = _element_index(state, "Edit")
        text = "Bonjour Julien éàç"
        res = cc.type_text(text, hwnd=hwnd, element_index=index, clear_first=True)
        label = _wait_label(hwnd, f"Champ : {text}", cc)
        report.check(
            f"{tag} : champ rempli en arrière-plan",
            res["success"] is True and res["method"] == expected["edit"] and label == f"Champ : {text}",
            f"technique {res['method']}, valeur relue « {res.get('current_value')} », étiquette « {label} »",
        )

    report.run(f"{tag} : champ rempli en arrière-plan", type_field)

    def select_combo() -> None:
        state = cc.get_window_state(hwnd=hwnd, max_elements=100)
        index = _element_index(state, "ComboBox")
        res = cc.select_option("Bravo", hwnd=hwnd, element_index=index)
        label = _wait_label(hwnd, "Choix : Bravo", cc)
        report.check(
            f"{tag} : liste déroulante en arrière-plan",
            res["success"] is True and res["method"] == "win32_cb_setcursel" and label == "Choix : Bravo",
            f"technique {res['method']}, {res.get('verified_by')}, étiquette « {label} »",
        )

    report.run(f"{tag} : liste déroulante en arrière-plan", select_combo)

    def select_list() -> None:
        state = cc.get_window_state(hwnd=hwnd, max_elements=100)
        index = _element_index(state, "List")
        res = cc.select_option("Deux", hwnd=hwnd, element_index=index)
        label = _wait_label(hwnd, "Liste : Deux", cc)
        report.check(
            f"{tag} : liste en arrière-plan",
            res["success"] is True and res["method"] == "win32_lb_setcursel" and label == "Liste : Deux",
            f"technique {res['method']}, {res.get('verified_by')}, étiquette « {label} »",
        )

    report.run(f"{tag} : liste en arrière-plan", select_list)

    if family == "Win32":

        def menu() -> None:
            res = cc.act(
                steps=[
                    {
                        "action": "menu",
                        "path": "Fichier > Marquer",
                        "expect": {"element": "Menu : Marquer", "exists": True},
                    }
                ],
                hwnd=hwnd,
                then="none",
            )
            step = res["steps"][0]
            label = _wait_label(hwnd, "Menu : Marquer", cc)
            report.check(
                "Win32 : commande de menu en arrière-plan",
                res["success"] is True
                and step["result"]["method"] == "win32_menu_command"
                and label == "Menu : Marquer",
                f"technique {step['result']['method']}, verified={step['verified']}, étiquette « {label} »",
            )

        report.run("Win32 : commande de menu en arrière-plan", menu)

        def honest_failure() -> None:
            res = cc.act(
                steps=[
                    {
                        "action": "click",
                        "target": "Valider",
                        "expect": {"element": "Clics : 99", "exists": True, "timeout": 0.3},
                    }
                ],
                hwnd=hwnd,
                then="none",
            )
            report.check(
                "Win32 : postcondition fausse → étape en échec (aucun faux succès)",
                res["success"] is False and res["steps"][0]["status"] == "failed",
                f"success={res['success']}, statut {res['steps'][0]['status']}",
            )

        report.run("Win32 : postcondition fausse → étape en échec (aucun faux succès)", honest_failure)

        def coords_click() -> None:
            state = cc.get_window_state(hwnd=hwnd, max_elements=100)
            button = next(el for el in state["elements"] if el["type"] == "Button" and el["name"] == "Valider")
            before = _label(hwnd, "Clics", cc)
            n = int(before.split(":")[1]) + 1
            center = button["relative_center"]
            res = cc.click(hwnd=hwnd, x=center["x"], y=center["y"], coords="window", foreground=False)
            label = _wait_label(hwnd, f"Clics : {n}", cc)
            report.check(
                "Win32 : clic par coordonnées rapporté au bouton, fait en arrière-plan",
                res["verified"] is True and res["method"] == "win32_bn_clicked" and label == f"Clics : {n}"
                and not res.get("physical"),
                f"technique {res['method']}, visé {res.get('hit_test')}, étiquette « {label} »",
            )  # fmt: skip

        report.run("Win32 : clic par coordonnées rapporté au bouton, fait en arrière-plan", coords_click)


def _tool_payload(raw) -> dict:
    """Réponse d'un outil MCP : texte JSON seul, ou liste [texte, image]."""
    if isinstance(raw, (list, tuple)):
        raw = next(item for item in raw if isinstance(item, str))
    return json.loads(raw)


def validate_gemini_form(cc, mcp, report: Report, fixture, family: str) -> None:
    """Formulaire WinForms/WPF piloté comme Gemini l'a fait le 16/10 (clic box_2d dans le champ, Ctrl+A, saisie sans
    cible), par le vrai serveur MCP : tout en arrière-plan, relu ✓, puis le même lot renvoyé sans regarder est
    refusé, et un regard le débloque."""
    import bench_gemini_task as bench
    import desktop_fixtures as df

    tag = f"{family} formulaire"
    hwnd = fixture.hwnd
    state = _tool_payload(mcp.computer_look(hwnd=hwnd, capture_screenshot=False, max_elements=60, format="json"))[
        "data"
    ]
    lot = bench._naive_lot(state)

    def naive_lot() -> None:
        res = _tool_payload(mcp.computer_act(steps=lot, hwnd=hwnd))
        data = res.get("data") or {}
        marks = [step.get("mark") for step in data.get("steps", [])]
        result = df.wait_result(cc, hwnd, "Envois=1")
        report.check(
            f"{tag} : lot naïf (box_2d, Ctrl+A, saisie sans cible) fait en arrière-plan et relu",
            data.get("success") is True
            and marks == ["✓"] * len(lot)
            and data.get("physical_steps") == 0
            and result == bench.EXPECTED,
            f"marques {''.join(m or '?' for m in marks)}, gestes physiques {data.get('physical_steps')}, "
            f"next « {res.get('next')} », application « {result} »",
        )

    report.run(f"{tag} : lot naïf (box_2d, Ctrl+A, saisie sans cible) fait en arrière-plan et relu", naive_lot)

    def repeat_guard() -> None:
        again = _tool_payload(mcp.computer_act(steps=lot, hwnd=hwnd))
        result = df.wait_result(cc, hwnd, "Envois=", timeout=0.5)
        report.check(
            f"{tag} : même lot renvoyé sans regarder → refusé, rien envoyé",
            again.get("status") == "refused" and result.endswith("Envois=1"),
            f"statut {again.get('status')}, next « {again.get('next')} », application « {result} »",
        )
        mcp.computer_look(hwnd=hwnd, capture_screenshot=False, max_elements=20)
        valider = [{"action": "click", "target": "Valider"}]
        first = _tool_payload(mcp.computer_act(steps=valider, hwnd=hwnd))
        mcp.computer_look(hwnd=hwnd, capture_screenshot=False, max_elements=20)
        after_look = _tool_payload(mcp.computer_act(steps=valider, hwnd=hwnd))
        result = df.wait_result(cc, hwnd, "Envois=3")
        report.check(
            f"{tag} : après un regard, le lot repart",
            first.get("status") == "success" and after_look.get("status") == "success" and result.endswith("Envois=3"),
            f"statuts {first.get('status')} puis {after_look.get('status')}, application « {result} »",
        )

    report.run(f"{tag} : même lot renvoyé sans regarder → refusé, rien envoyé", repeat_guard)

    if family == "WPF":

        def shortcut_refused() -> None:
            res = _tool_payload(mcp.computer_act(steps=[{"action": "key", "key": "ctrl+s"}], hwnd=hwnd))
            step = ((res.get("data") or {}).get("steps") or [{}])[0]
            report.check(
                "WPF : raccourci Ctrl impossible en arrière-plan → refus explicite (aucune vraie touche)",
                step.get("error_type") == "NeedsForegroundError" and "foreground" in (res.get("next") or ""),
                f"{step.get('error_type')} ; next « {res.get('next')} »",
            )

        report.run("WPF : raccourci Ctrl impossible en arrière-plan → refus explicite (aucune vraie touche)",
                   shortcut_refused)  # fmt: skip


def validate_physical(cc, report: Report, fixture: Any, julien_fg: int) -> None:
    """Vraie souris et vrai clavier (FocusGuard) sur la fenêtre de test : seulement si Julien est inactif depuis 120 s."""
    hwnd = fixture.hwnd
    state = cc.get_window_state(hwnd=hwnd, max_elements=100)
    edit = _element_index(state, "Edit")
    button = next(el for el in state["elements"] if el["type"] == "Button" and el["name"] == "Valider")
    before_clicks = _label(hwnd, "Clics", cc)

    res = cc.type_text(
        "Frappe réelle", hwnd=hwnd, element_index=edit, clear_first=True, method="typing", foreground=True
    )
    label = _wait_label(hwnd, "Champ : Frappe réelle", cc)
    fg_after = user32.GetForegroundWindow()
    report.check(
        "Physique : frappe SendInput relue, premier plan rendu",
        res["verified"] is True and label == "Champ : Frappe réelle" and (not julien_fg or fg_after == julien_fg),
        f"verified={res['verified']}, étiquette « {label} », premier plan rendu={fg_after == julien_fg}",
    )

    pt = cc.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    center = button["relative_center"]
    # Chemin physique de repli (point sans élément UIA) forcé sur le bouton : la vraie souris, sous garde.
    rect = cc.get_window_rect(hwnd)
    sx, sy = rect["left"] + center["x"], rect["top"] + center["y"]
    res = cc._physical_point_click(hwnd, sx, sy, "relative_coordinates", {}, "left", 1, True, True,
                                   time.perf_counter())  # fmt: skip
    n = int(before_clicks.split(":")[1]) + 1 if ":" in before_clicks else 1
    label = _wait_label(hwnd, f"Clics : {n}", cc)
    after = cc.POINT()
    user32.GetCursorPos(ctypes.byref(after))
    report.check(
        "Physique : clic réel (repli sans élément UIA), curseur rendu",
        label == f"Clics : {n}" and (after.x, after.y) == (pt.x, pt.y) and res["verified"] is True,
        f"étiquette « {label} », verified={res['verified']}, curseur rendu={(after.x, after.y) == (pt.x, pt.y)}",
    )


def main_validation() -> int:
    sys.path.insert(0, str(REPO_ROOT / "client"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import computer_client as cc
    import computer_logger
    import desktop_fixtures as df
    import mcp_server as mcp
    import physical_input

    # Journal de la validation à part : le vrai ~/.nexusagy/computer.log ne reçoit que l'usage réel de Gemini.
    log_dir = Path(tempfile.mkdtemp(prefix="nexusagy-live-"))
    computer_logger.LOG_DIR = log_dir
    computer_logger.LOG_FILE = log_dir / "computer.log"

    report = Report()
    raw_ok = physical_input.start(timeout_s=2.0)
    if cc.uia_fast is not None:
        cc.uia_fast.reader()  # client UIA créé une fois, comme dans le serveur : mesures en régime établi
    report.check(
        "Raw Input actif (entrées physiques distinguées des injectées)", raw_ok, json.dumps(physical_input.summary())
    )

    # Règle commune des bancs : aucune fenêtre de test si Julien est actif ; s'il revient, tout est fermé aussitôt et
    # la validation s'arrête sans être comptée (code 3).
    guard = df.PresenceGuard(physical_input)
    try:
        guard.require_absent()
    except df.JulienActive as active:
        print(f"Validation réelle non lancée : {active}")
        return 3
    guard.start()
    julien_fg = int(user32.GetForegroundWindow() or 0)
    cursor = cc.POINT()
    user32.GetCursorPos(ctypes.byref(cursor))
    clip_seq = int(user32.GetClipboardSequenceNumber())
    token = physical_input.mark()
    watch = df.ForegroundWatch()
    fixtures: list[Any] = []  # desktop_fixtures.Fixture, inscrites au garde de présence
    try:
        win32 = df.Fixture("Win32", [sys.executable, "-B", str(Path(__file__).resolve()), "--win32-fixture"])
        fixtures.append(win32)
        watch.forbidden.add(win32.pid)
        encoded = base64.b64encode(WINFORMS_SCRIPT.encode("utf-16-le")).decode("ascii")
        try:
            winforms = df.Fixture(
                "WinForms",
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass",
                 "-EncodedCommand", encoded],
            )  # fmt: skip
            fixtures.append(winforms)
            watch.forbidden.add(winforms.pid)
        except RuntimeError as error:
            winforms = None
            report.add("WinForms : fenêtre de test", "fail", str(error))
        watch.start()
        time.sleep(0.3)
        fg_now = int(user32.GetForegroundWindow() or 0)
        fixture_pids = {f.pid for f in fixtures}
        stolen = bool(watch.hits) or (fg_now != julien_fg and df.window_pid(fg_now) in fixture_pids)
        report.check(
            "Fenêtres de test affichées sans activation",
            not stolen,
            "premier plan inchangé"
            if fg_now == julien_fg
            else "premier plan changé par Julien lui-même (jamais une fenêtre de test)",
        )

        validate_family(
            cc,
            report,
            win32,
            "Win32",
            {"button": "win32_bn_clicked", "check": "win32_bm_setcheck", "edit": "win32_em_replacesel"},
        )
        if winforms is not None:
            validate_family(
                cc,
                report,
                winforms,
                "WinForms",
                # bouton poussoir WinForms : BN_CLICKED posté d'abord (UIA Invoke bloquerait sur une boîte modale)
                {"button": "win32_bn_clicked", "check": "uia_toggle", "edit": "uia_set_value"},
            )

        for make, family in ((df.winforms_form, "WinForms"), (df.wpf_form, "WPF")):
            try:
                form = make()
            except RuntimeError as error:
                report.add(f"{family} formulaire : fenêtre de test", "fail", str(error))
                continue
            fixtures.append(form)
            watch.forbidden.add(form.pid)
            report.run(f"{family} formulaire", lambda form=form, family=family: validate_gemini_form(
                cc, mcp, report, form, family))  # fmt: skip

        report.check(
            "Aucun vol de premier plan pendant les actions d'arrière-plan",
            not watch.hits,
            f"{len(watch.hits)} échantillons où une fenêtre de test (ou ce processus) avait le premier plan",
        )
        julien_touched = physical_input.user_touched_since(token)
        now = cc.POINT()
        user32.GetCursorPos(ctypes.byref(now))
        if (now.x, now.y) == (cursor.x, cursor.y):
            report.add("Curseur inchangé", "ok", f"({now.x}, {now.y})")
        elif julien_touched:
            report.add("Curseur inchangé", "skipped", "non concluant : Julien a bougé la souris pendant la validation")
        else:
            report.add("Curseur inchangé", "fail", f"({cursor.x}, {cursor.y}) → ({now.x}, {now.y})")
        seq = int(user32.GetClipboardSequenceNumber())
        if seq == clip_seq:
            report.add("Presse-papiers intact", "ok", "numéro de séquence inchangé")
        elif julien_touched:
            report.add("Presse-papiers intact", "skipped", "non concluant : Julien actif (il a pu copier)")
        else:
            report.add("Presse-papiers intact", "fail", f"séquence {clip_seq} → {seq}")

        idle = physical_input.user_idle_s()
        if idle >= PHYSICAL_IDLE_S and raw_ok:
            watch.paused.set()  # ici la fenêtre de test prend le premier plan, brièvement et volontairement
            report.run("Physique", lambda: validate_physical(cc, report, win32, julien_fg))
        else:
            for name in (
                "Physique : frappe SendInput relue, premier plan rendu",
                "Physique : clic réel (repli sans élément UIA), curseur rendu",
            ):
                report.add(
                    name, "skipped", f"sautée (Julien actif : inactif depuis {idle:.0f} s < {PHYSICAL_IDLE_S:.0f} s)"
                )
    except Exception:
        if not guard.returned:
            raise
    finally:
        guard.stop()
        watch.stop()
        for fixture in fixtures:
            fixture.close()
        closed = all(not user32.IsWindow(f.hwnd) for f in fixtures)
        report.check("Fenêtres de test fermées", closed)
    if guard.returned:
        print(
            "Validation réelle interrompue : Julien est revenu, fenêtres de test fermées aussitôt, rien n'est compté."
        )
        return 3

    ok = sum(1 for r in report.rows if r["status"] == "ok")
    skipped = sum(1 for r in report.rows if r["status"] == "skipped")
    print(
        json.dumps(
            {"ok": ok, "failed": len(report.failures), "skipped": skipped, "raw_input": raw_ok}, ensure_ascii=False
        )
    )
    return 1 if report.failures else 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--win32-fixture", action="store_true", help="mode interne : fenêtre Win32 de test seule")
    args = parser.parse_args()
    if args.win32_fixture:
        return run_win32_fixture()
    return main_validation()


if __name__ == "__main__":
    sys.exit(main())
