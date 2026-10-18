"""Bureau 2026-10-15 (14 → 17/20) : Raw Input et interruption, messages Win32 directs selon la famille d'interface,
lecture UIA en un aller-retour, relecture et postconditions `expect`, validation réelle branchée dans test.ps1 -Full.

Hors ligne : les fenêtres Win32 de ces tests sont créées dans ce processus, jamais affichées, et détruites à la fin.
"""

import ctypes
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "client"))

import computer_client  # noqa: E402
import emergency_stop  # noqa: E402
import mcp_server  # noqa: E402
import physical_input  # noqa: E402
import uia_fast  # noqa: E402
import win32_controls  # noqa: E402


# =============================================================================
# 1. Raw Input : entrées physiques distinguées des injectées ; interruption
# =============================================================================
def _fake_raw(dw_type: int, device: int, button_flags: int = 0, dx: int = 0, dy: int = 0):
    def fake(handle, command, buffer, size, header_size):
        header = physical_input._RAWINPUTHEADER.from_buffer(buffer)
        header.dwType = dw_type
        header.dwSize = 48
        header.hDevice = device
        if dw_type == physical_input.RIM_TYPEMOUSE:
            mouse = physical_input._RAWMOUSE.from_buffer(buffer, physical_input._HEADER)
            mouse.usButtonFlags = button_flags
            mouse.lLastX = dx
            mouse.lLastY = dy
        return 48

    return fake


@pytest.fixture
def raw_state(monkeypatch):
    state = physical_input._S
    monkeypatch.setattr(state, "last_input", 0.0)
    monkeypatch.setattr(state, "last_move", 0.0)
    monkeypatch.setattr(state, "counts", {"keyboard": 0, "mouse_buttons": 0, "mouse_moves": 0, "injected": 0})
    return state


def test_rawmouse_layout_matches_windows():
    # usFlags (2) + alignement (2), puis l'union ulButtons : usButtonFlags à l'octet 4 (comme RAWMOUSE de Windows)
    assert physical_input._RAWMOUSE.usButtonFlags.offset == 4
    assert physical_input._RAWMOUSE.lLastX.offset == 12
    assert ctypes.sizeof(physical_input._RAWMOUSE) == 24


def test_injected_input_is_never_counted_as_julien(raw_state):
    with patch.object(physical_input._user32, "GetRawInputData", _fake_raw(physical_input.RIM_TYPEKEYBOARD, 0)):
        physical_input._on_input(1)
    assert raw_state.last_input == 0.0
    assert raw_state.counts["injected"] == 1


def test_physical_keyboard_buttons_and_moves_are_seen(raw_state):
    with patch.object(physical_input._user32, "GetRawInputData", _fake_raw(physical_input.RIM_TYPEKEYBOARD, 0x1234)):
        physical_input._on_input(1)
    assert raw_state.last_input > 0
    first = raw_state.last_input
    with patch.object(
        physical_input._user32, "GetRawInputData", _fake_raw(physical_input.RIM_TYPEMOUSE, 0x99, dx=3, dy=-1)
    ):
        physical_input._on_input(1)
    assert raw_state.last_move > 0 and raw_state.last_input == first  # un déplacement n'est pas une frappe
    with patch.object(
        physical_input._user32, "GetRawInputData", _fake_raw(physical_input.RIM_TYPEMOUSE, 0x99, button_flags=1)
    ):
        physical_input._on_input(1)
    assert raw_state.counts == {"keyboard": 1, "mouse_buttons": 1, "mouse_moves": 1, "injected": 0}


def test_touched_since_uses_raw_input_when_available(raw_state, monkeypatch):
    monkeypatch.setattr(raw_state, "ok", True)
    token = (time.monotonic(), 0)
    assert physical_input.user_touched_since(token) is False
    raw_state.last_move = time.monotonic() + 0.001
    assert physical_input.user_touched_since(token) is True
    assert physical_input.user_touched_since(token, include_moves=False) is False


def test_fallback_ignores_own_injections(monkeypatch):
    state = physical_input._S
    monkeypatch.setattr(state, "ok", False)
    monkeypatch.setattr(state, "injections", physical_input.deque(maxlen=8))
    monkeypatch.setattr(state, "last_foreign_tick", 1000)
    ticks = {"now": 5000, "last": 1000}
    monkeypatch.setattr(physical_input, "_tick", lambda: ticks["now"])
    monkeypatch.setattr(physical_input, "_lastinput_tick", lambda: ticks["last"])
    # Injection de NexusAGY entre 4000 et 4010 : GetLastInputInfo la voit, le repli l'écarte.
    state.injections.append((4000, 4010 + physical_input.INJECTION_GRACE_MS))
    ticks["last"] = 4005
    assert physical_input.fallback_idle_s() == pytest.approx(4.0)  # depuis 1000, pas depuis l'injection
    # Une vraie frappe hors de toute injection compte.
    ticks["last"] = 4900
    assert physical_input.fallback_idle_s() == pytest.approx(0.1)
    token = (time.monotonic(), 4950)
    ticks["last"] = 4980
    assert physical_input.user_touched_since(token) is True


def test_wait_for_user_idle_reads_physical_idle():
    with patch.object(physical_input, "user_idle_s", side_effect=[0.2, 0.4, 2.0]):
        assert computer_client.wait_for_user_idle(threshold_s=1.5, max_wait_s=2.0) is True
    with patch.object(physical_input, "user_idle_s", return_value=0.0):
        assert computer_client.wait_for_user_idle(threshold_s=1.5, max_wait_s=0.15) is False


@pytest.fixture
def quiet_guard(monkeypatch):
    """FocusGuard réel, mais sans jeton, sans attente, sans changer le vrai premier plan ni le vrai curseur."""
    calls = {"restore": [], "cursor": []}
    monkeypatch.setattr(computer_client, "wait_for_user_idle", lambda **kwargs: True)
    monkeypatch.setattr(computer_client, "focus_window", lambda **kwargs: {"success": True})
    monkeypatch.setattr(computer_client, "_target_in_front", lambda h: True)  # premier plan relu : cible devant
    monkeypatch.setattr(computer_client, "_focused_is_password", lambda: False)
    monkeypatch.setattr(computer_client, "restore_foreground", lambda h: calls["restore"].append(h) or True)
    monkeypatch.setattr(computer_client.user32, "SetCursorPos", lambda x, y: calls["cursor"].append((x, y)) or 1)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    real_init = computer_client.FocusGuard.__init__

    def init(self, target_hwnd=None, restore=True, wait_idle=True, use_lock=True, purpose="action physique"):
        real_init(self, target_hwnd, restore, wait_idle, use_lock=False, purpose=purpose)

    monkeypatch.setattr(computer_client.FocusGuard, "__init__", init)
    return calls


def test_typing_stops_when_julien_takes_over_and_hands_back(quiet_guard, monkeypatch):
    sent = []
    touched = {"after": 3}

    def send(inputs):
        sent.append(inputs)
        return len(inputs)

    def touched_since(token, include_moves=True):
        return len(sent) >= touched["after"]

    monkeypatch.setattr(computer_client, "_send_inputs", send)
    monkeypatch.setattr(physical_input, "user_touched_since", touched_since)
    with pytest.raises(computer_client.UserInterruptError, match="repris le clavier"):
        computer_client.type_text("abcdefgh", hwnd=1, method="typing", foreground=True)
    assert len(sent) == 3  # arrêt au point de contrôle suivant, pas à la fin du texte
    assert quiet_guard["restore"]  # premier plan rendu
    assert quiet_guard["cursor"] == []  # curseur laissé à Julien, qui s'en sert
    assert computer_client._active_token() is None  # repère retiré


def test_drag_interrupted_by_julien_releases_button(quiet_guard, monkeypatch):
    flags = []

    def send(inputs):
        flags.append(inputs[0].union.mi.dwFlags)
        return 1

    calls = {"n": 0}

    def touched_since(token, include_moves=True):
        calls["n"] += 1
        return calls["n"] >= 3

    monkeypatch.setattr(computer_client, "_send_inputs", send)
    monkeypatch.setattr(physical_input, "user_touched_since", touched_since)
    with pytest.raises(computer_client.UserInterruptError):
        computer_client.drag(0, 0, 50, 50, hwnd=1, coords="screen", steps=6, delay_ms=0, foreground=True)
    assert flags[0] == computer_client.MOUSEEVENTF_LEFTDOWN
    assert flags[-1] == computer_client.MOUSEEVENTF_LEFTUP


def test_mcp_reports_user_interruption():
    def boom():
        raise computer_client.UserInterruptError("Julien a repris le clavier")

    payload = json.loads(mcp_server._format_computer_result(boom))
    assert payload["status"] == "error"
    assert payload["interrupted_by_user"] is True


# =============================================================================
# 2. Messages Win32 directs sur de vrais contrôles (fenêtre jamais affichée)
# =============================================================================
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_u32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_u32.DefWindowProcW.restype = LRESULT
_u32.CreateWindowExW.argtypes = (
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
_u32.CreateWindowExW.restype = wintypes.HWND
_u32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_u32.SendMessageW.restype = LRESULT
_u32.PeekMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT)
_u32.CreateMenu.restype = wintypes.HMENU
_u32.CreatePopupMenu.restype = wintypes.HMENU
_u32.AppendMenuW.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR)
_u32.SetMenu.argtypes = (wintypes.HWND, wintypes.HMENU)
_u32.UnregisterClassW.argtypes = (wintypes.LPCWSTR, wintypes.HINSTANCE)
_u32.DestroyWindow.argtypes = (wintypes.HWND,)
_k32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
_k32.GetModuleHandleW.restype = wintypes.HMODULE  # handle 64 bits : jamais tronqué en int


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


@pytest.fixture
def hidden_controls():
    """Fenêtre parente invisible et ses contrôles standard ; elle enregistre chaque WM_COMMAND reçu."""
    commands: list[tuple[int, int]] = []

    def proc(hwnd, msg, wparam, lparam):
        if msg == 0x0111:
            commands.append((wparam & 0xFFFF, (wparam >> 16) & 0xFFFF))
            return 0
        return _u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wndproc = WNDPROC(proc)
    hinst = _k32.GetModuleHandleW(None)
    cls = f"NexusAGYTest{id(commands)}"
    wc = _WNDCLASSW(lpfnWndProc=wndproc, hInstance=hinst, lpszClassName=cls)
    _u32.RegisterClassW(ctypes.byref(wc))
    parent = _u32.CreateWindowExW(0, cls, "Test", 0x00CF0000, 0, 0, 400, 300, None, None, hinst, None)

    def child(kind: str, text: str, style: int, ident: int) -> int:
        return _u32.CreateWindowExW(
            0, kind, text, 0x50000000 | style, 0, 0, 120, 120, parent, wintypes.HMENU(ident), hinst, None
        )

    ctl = SimpleNamespace(
        parent=parent,
        commands=commands,
        button=child("BUTTON", "Valider", 0x0, 11),
        check=child("BUTTON", "Option", 0x3, 12),
        edit=child("EDIT", "", 0x0080, 13),
        combo=child("COMBOBOX", "", 0x0003, 14),
        listbox=child("LISTBOX", "", 0x0001, 15),
        dupes=child("LISTBOX", "", 0x0001, 16),
    )
    for name in ("Alpha", "Bravo", "Charlie"):
        _u32.SendMessageW(ctl.combo, 0x0143, 0, ctypes.addressof(ctypes.create_unicode_buffer(name)))
    for name in ("Un", "Deux", "Trois"):
        _u32.SendMessageW(ctl.listbox, 0x0180, 0, ctypes.addressof(ctypes.create_unicode_buffer(name)))
    for name in ("Doublon", "Doublon"):
        _u32.SendMessageW(ctl.dupes, 0x0180, 0, ctypes.addressof(ctypes.create_unicode_buffer(name)))
    menubar, filemenu = _u32.CreateMenu(), _u32.CreatePopupMenu()
    _u32.AppendMenuW(filemenu, 0, 401, "&Marquer")
    _u32.AppendMenuW(menubar, 0x10, filemenu, "&Fichier")
    _u32.SetMenu(parent, menubar)

    def pump() -> None:
        msg = wintypes.MSG()
        for _ in range(50):
            while _u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                _u32.TranslateMessage(ctypes.byref(msg))
                _u32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.002)

    ctl.pump = pump
    ctl._keep = wndproc
    try:
        yield ctl
    finally:
        _u32.DestroyWindow(parent)
        _u32.UnregisterClassW(cls, hinst)


def test_button_click_notifies_parent_with_bn_clicked(hidden_controls):
    ctl = hidden_controls
    assert win32_controls.button_click(ctl.button) == "bn_clicked"
    ctl.pump()
    assert (11, win32_controls.BN_CLICKED) in ctl.commands


def test_set_check_sets_state_then_notifies_and_skips_when_already(hidden_controls):
    ctl = hidden_controls
    assert win32_controls.set_check(ctl.check, True) == "bm_setcheck"
    ctl.pump()
    assert win32_controls.get_check(ctl.check) == 1
    assert (12, win32_controls.BN_CLICKED) in ctl.commands
    ctl.commands.clear()
    assert win32_controls.set_check(ctl.check, True) == "already"
    ctl.pump()
    assert ctl.commands == []  # rien envoyé : l'état était déjà le bon


def test_edit_replace_sends_en_change_and_reads_back(hidden_controls):
    ctl = hidden_controls
    win32_controls.edit_set_text(ctl.edit, "Bonjour")
    win32_controls.edit_set_text(ctl.edit, " Julien", append=True)
    ctl.pump()
    assert win32_controls.get_text(ctl.edit) == "Bonjour Julien"
    assert (13, 0x0300) in ctl.commands  # EN_CHANGE émis par le contrôle lui-même


def test_combo_and_listbox_select_notify_and_refuse_ambiguity(hidden_controls):
    ctl = hidden_controls
    assert win32_controls.combo_select(ctl.combo, "bravo") == "cb_setcursel"
    assert win32_controls.combo_selected(ctl.combo) == "Bravo"
    assert win32_controls.listbox_select(ctl.listbox, "Deux") == "lb_setcursel"
    assert win32_controls.listbox_selected(ctl.listbox) == "Deux"
    ctl.pump()
    assert (14, win32_controls.CBN_SELCHANGE) in ctl.commands
    assert (15, win32_controls.LBN_SELCHANGE) in ctl.commands
    assert win32_controls.combo_select(ctl.combo, "Bravo") == "already"
    with pytest.raises(win32_controls.MessageError, match="2 fois"):
        win32_controls.listbox_select(ctl.dupes, "Doublon")
    with pytest.raises(win32_controls.MessageError, match="absente"):
        win32_controls.combo_select(ctl.combo, "Zoulou")


def test_menu_command_posts_wm_command_with_item_id(hidden_controls):
    ctl = hidden_controls
    assert win32_controls.menu_items(ctl.parent) == [("Fichier > Marquer", 401)]
    assert win32_controls.menu_command(ctl.parent, "Fichier > Marquer") == "wm_command_menu"
    ctl.pump()
    assert (401, 0) in ctl.commands
    with pytest.raises(win32_controls.MessageError, match="introuvable"):
        win32_controls.menu_command(ctl.parent, "Fichier > Quitter")


def test_wrong_control_class_is_refused(hidden_controls):
    ctl = hidden_controls
    for func, args in (
        (win32_controls.button_click, (ctl.edit,)),
        (win32_controls.edit_set_text, (ctl.button, "x")),
        (win32_controls.combo_select, (ctl.listbox, "Un")),
        (win32_controls.listbox_select, (ctl.combo, "Alpha")),
    ):
        with pytest.raises(win32_controls.MessageError):
            func(*args)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    "cls,family",
    [
        ("Chrome_WidgetWin_1", "Chromium"),
        ("HwndWrapper[App;;1]", "WPF"),
        ("WindowsForms10.Window.8.app.0.1", "WinForms"),
        ("ApplicationFrameWindow", "UWP"),
        ("#32770", "Win32"),
        ("Notepad", "WinUI"),
    ],
)
def test_family_by_window_class(cls, family):
    with (
        patch.object(win32_controls, "root_of", return_value=5),
        patch.object(win32_controls, "class_name", return_value=cls),
    ):
        assert win32_controls.family(5) == family


def test_winforms_base_class():
    with patch.object(win32_controls, "class_name", return_value="WindowsForms10.BUTTON.app.0.141b42a_r6_ad1"):
        assert win32_controls.base_class(1) == "button"


def _plan(info, own_kind="", button_kind=0, host_kind=""):
    kinds = {info.get("hwnd"): own_kind, info.get("host_hwnd"): host_kind}
    with (
        patch.object(computer_client, "_native_kind", side_effect=lambda h: kinds.get(h, "") if h else ""),
        patch.object(win32_controls, "button_kind", return_value=button_kind),
        patch.object(computer_client, "_read_state", return_value={}),
        patch.object(computer_client, "window_fingerprint", return_value=None),
    ):
        _fam, chain, _verify = computer_client._click_plan(MagicMock(), info, 0)
    return [name for name, _ in chain]


ALL_PATTERNS = {"has_invoke": True, "has_toggle": True, "has_selection_item": True, "has_expand": True}


def test_win32_button_uses_bn_clicked_and_never_uia_invoke():
    info = {"framework": "Win32", "type": "Button", "name": "OK", "hwnd": 7, "props": {"has_invoke": True}}
    assert _plan(info, own_kind="button") == ["BN_CLICKED"]


def test_win32_list_item_uses_lb_setcursel_and_never_uia_select():
    info = {"framework": "Win32", "type": "ListItem", "name": "Deux", "hwnd": 0, "host_hwnd": 9, "props": ALL_PATTERNS}
    names = _plan(info, host_kind="listbox")
    assert names[0] == "LB_SETCURSEL"
    assert "UIA Select" not in names and "UIA Invoke" not in names


def test_winforms_tries_uia_before_messages_and_no_bn_clicked_on_checkbox():
    button = {"framework": "WinForms", "type": "Button", "name": "OK", "hwnd": 7, "props": {"has_invoke": True}}
    assert _plan(button, own_kind="button", button_kind=0) == ["UIA Invoke", "BN_CLICKED"]
    check = {"framework": "WinForms", "type": "CheckBox", "name": "Case", "hwnd": 7, "props": {"has_toggle": True}}
    assert _plan(check, own_kind="checkbox", button_kind=3) == ["UIA Toggle"]


@pytest.mark.parametrize("framework", ["WPF", "XAML", "Chrome"])
def test_uia_only_families_get_no_messages(framework):
    info = {"framework": framework, "type": "Button", "name": "OK", "hwnd": 7, "props": ALL_PATTERNS}
    names = _plan(info, own_kind="button")
    assert names and all(name.startswith("UIA") for name in names)


def test_text_plan_order_by_family():
    def plan(framework):
        info = {"framework": framework, "hwnd": 7}
        with (
            patch.object(computer_client, "_native_kind", return_value="edit"),
            patch.object(computer_client, "_read_state", return_value={"value": ""}),
        ):
            _fam, chain, _verify, expected = computer_client._text_plan(MagicMock(), info, 0, "abc", True, "auto")
        return [name for name, _ in chain], expected

    assert plan("Win32") == (["EM_REPLACESEL", "UIA Value"], "abc")
    assert plan("WinForms") == (["UIA Value", "EM_REPLACESEL"], "abc")
    assert plan("WPF") == (["UIA Value"], "abc")


def test_chain_moves_on_only_when_effect_is_read_absent():
    calls = []
    chain = [
        ("A", lambda: calls.append("A") or "a"),
        ("B", lambda: calls.append("B") or "b"),
        ("C", lambda: calls.append("C") or "c"),
    ]
    verdicts = {"a": (False, "coche inchangée"), "b": (None, ""), "c": (True, "relu")}
    out = computer_client._run_chain(chain, lambda d: verdicts[d], 0)
    assert calls == ["A", "B"]  # effet inconnu après B : jamais de seconde activation par C
    assert out["technique"] == "B" and out["verified"] is None
    assert out["tried"] == [{"technique": "A", "error": "sans effet relu (coche inchangée)"}]


# =============================================================================
# 3. Lecture UIA en un aller-retour : bornes et échecs dits
# =============================================================================
class _FakeArray:
    def __init__(self, items):
        self.items = items
        self.Length = len(items)

    def GetElement(self, i):
        return self.items[i]


class _FakeElement:
    def __init__(self, props, children=()):
        self.props = props
        self.children = list(children)

    def GetCachedPropertyValue(self, pid):
        key = next((k for k, v in uia_fast.PROPS.items() if v == pid), None)
        return self.props.get(key)

    def GetCachedChildren(self):
        return _FakeArray(self.children) if self.children else None


def _reader(root=None, error=None):
    reader = object.__new__(uia_fast.Reader)
    reader.auto_set_focus = False

    def build(hwnd, cache):
        if error:
            raise error
        return root

    reader.uia = SimpleNamespace(ElementFromHandleBuildCache=build, TransactionTimeout=0)  # pyright: ignore[reportAttributeAccessIssue]
    reader.cache_tree = object()  # pyright: ignore[reportAttributeAccessIssue]
    return reader


def test_cached_tree_is_read_in_document_order_with_host_window():
    button = _FakeElement({"control_type": uia_fast.U.UIA_ButtonControlTypeId, "name": " Valider "})
    edit = _FakeElement({"control_type": uia_fast.U.UIA_EditControlTypeId, "hwnd": 42, "value": "abc"})
    pane = _FakeElement({"control_type": uia_fast.U.UIA_PaneControlTypeId, "hwnd": 7}, [button, edit])
    tree = _reader(_FakeElement({"control_type": uia_fast.U.UIA_WindowControlTypeId}, [pane])).read_tree(1)
    assert tree.status == "ok"
    assert [n.control_type for n in tree.nodes] == ["Window", "Pane", "Button", "Edit"]
    assert tree.nodes[2].name == "Valider"
    assert tree.nodes[2].host_hwnd == 7 and tree.nodes[3].host_hwnd == 42


def test_password_value_is_never_read():
    secret = _FakeElement({"control_type": uia_fast.U.UIA_EditControlTypeId, "password": True, "value": "s3cret"})
    tree = _reader(_FakeElement({}, [secret])).read_tree(1)
    assert "value" not in tree.nodes[1].props


def test_cached_tree_truncation_and_failure_are_reported():
    kids = [_FakeElement({"control_type": uia_fast.U.UIA_ButtonControlTypeId}) for _ in range(10)]
    tree = _reader(_FakeElement({}, kids)).read_tree(1, max_nodes=4)
    assert tree.status == "truncated" and len(tree.nodes) == 4 and "4 nœuds" in tree.reason
    failed = _reader(
        error=uia_fast.comtypes.COMError(-2146233083, "timeout", (None, None, None, None, None))
    ).read_tree(1, time_budget=0.5)
    assert failed.status == "failed" and "0.5 s" in failed.reason


def test_window_state_never_returns_a_silent_empty_list(monkeypatch):
    broken = SimpleNamespace(reader=MagicMock(side_effect=RuntimeError("UIAutomationCore indisponible")))
    monkeypatch.setattr(computer_client, "uia_fast", broken)
    monkeypatch.setattr(computer_client, "uia", None)
    hwnd = computer_client.list_windows()[0]["hwnd"]
    state = computer_client.get_window_state(hwnd=hwnd)
    assert state["elements"] == []
    assert state["uia"]["status"] == "failed"
    assert "UIAutomationCore indisponible" in state["uia"]["cache_error"]
    assert state["warning"]


def test_window_state_reports_cached_read_and_element_states(monkeypatch):
    rect = (10, 10, 60, 30)
    nodes = [
        uia_fast.Node(None, {"control_type": uia_fast.U.UIA_WindowControlTypeId}, 0, -1, 1),
        uia_fast.Node(
            "el-check",
            {
                "control_type": uia_fast.U.UIA_CheckBoxControlTypeId,
                "name": "Option",
                "rect": (rect[0], rect[1], 50, 20),
                "has_toggle": True,
                "toggle": 1,
                "framework": "Win32",
                "hwnd": 99,
            },
            1,
            0,
            99,
        ),
    ]
    reader = SimpleNamespace(read_tree=lambda *a, **k: uia_fast.Tree(nodes=nodes, duration_ms=3.0))
    monkeypatch.setattr(computer_client.uia_fast, "reader", lambda: reader)
    win = {"left": 0, "top": 0, "right": 200, "bottom": 100, "width": 200, "height": 100}
    read = computer_client._read_uia_elements(1, win, max_elements=10)
    assert read["report"]["method"] == "uia_cache_subtree" and read["report"]["status"] == "ok"
    element = read["elements"][0]
    assert element["type"] == "CheckBox" and element["checked"] is True
    assert element["box_2d"] == [100, 50, 300, 300]
    assert read["infos"][1]["hwnd"] == 99 and read["infos"][1]["framework"] == "Win32"
    limited = computer_client._read_uia_elements(1, win, max_elements=0)
    assert limited["report"]["status"] == "truncated"


# =============================================================================
# 4. Relecture : success suit verified ; postconditions expect et already
# =============================================================================
def test_fingerprint_ignores_caret_blink_but_sees_real_changes():
    from PIL import Image, ImageDraw

    def image(draw=None):
        img = Image.new("L", (600, 380), 240)
        if draw:
            draw(ImageDraw.Draw(img))
        return img

    base = {"title": "T", "windows": (1,), "image": image(lambda d: d.text((300, 20), "Clics : 2", fill=0))}
    caret = dict(base, image=image(lambda d: (d.text((300, 20), "Clics : 2", fill=0), d.line((40, 100, 40, 116), 0))))
    assert computer_client._fingerprint_changed(base, caret) == ""  # curseur de saisie qui clignote
    digit = dict(base, image=image(lambda d: d.text((300, 20), "Clics : 3", fill=0)))
    assert computer_client._fingerprint_changed(base, digit) == "image de la fenêtre"  # un seul chiffre suffit
    assert computer_client._fingerprint_changed(base, dict(base, title="U")) == "titre de la fenêtre"
    assert computer_client._fingerprint_changed(base, dict(base, windows=(1, 2))) == "fenêtres de l'application"
    assert computer_client._fingerprint_changed(base, dict(base, image=None)) == ""


def test_success_is_never_true_without_read_back():
    assert computer_client._success(True) is True
    assert computer_client._success(None) is None
    assert computer_client._success(False) is False


def test_act_skips_step_whose_postcondition_already_holds(monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(computer_client, "_run_act_step", run)
    monkeypatch.setattr(computer_client, "check_expect", lambda h, e: (True, {"checked": True, "match": "exact"}))
    res = computer_client.act(
        steps=[{"action": "check", "target": "Option", "expect": {"element": "Option", "checked": True}}],
        hwnd=1,
        then="none",
    )
    run.assert_not_called()
    assert res["success"] is True
    assert res["steps"][0]["already"] is True and res["steps"][0]["verified"] is True


def test_act_fails_step_when_postcondition_is_read_false(monkeypatch):
    monkeypatch.setattr(computer_client, "_run_act_step", lambda *a: {"success": None, "verified": None})
    monkeypatch.setattr(computer_client, "check_expect", lambda h, e: (False, {"exists": False}))
    monkeypatch.setattr(computer_client, "wait_expect", lambda h, e: (False, {"exists": False}))
    res = computer_client.act(
        steps=[
            {"action": "click", "target": "OK", "expect": {"element": "Terminé", "exists": True}},
            {"action": "wait", "seconds": 0.01},
        ],
        hwnd=1,
        then="none",
    )
    assert res["success"] is False
    assert res["executed_steps"] == 1
    assert res["steps"][0]["status"] == "failed"
    assert "observé" in res["error"]


def test_act_success_is_none_when_a_step_is_unverified(monkeypatch):
    monkeypatch.setattr(computer_client, "_run_act_step", lambda *a: {"success": None, "verified": None})
    res = computer_client.act(steps=[{"action": "key", "keys": "f5"}], hwnd=1, then="none")
    assert res["success"] is None
    assert res["unverified_steps"] == [0]
    assert res["steps"][0]["status"] == "unverified"
    assert "expect" in res["warning"]


def test_act_marks_user_interruption(monkeypatch):
    def interrupted(*args):
        raise computer_client.UserInterruptError("Julien a repris la souris")

    monkeypatch.setattr(computer_client, "_run_act_step", interrupted)
    res = computer_client.act(steps=[{"action": "drag"}], hwnd=1, then="none")
    assert res["success"] is False and res["interrupted_by_user"] is True
    assert res["steps"][0]["error_type"] == "UserInterruptError"


def test_set_checked_does_nothing_when_already_in_state(monkeypatch):
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(
        computer_client, "_target_element", lambda h, i, t, b=None: (3, MagicMock(), {"framework": "Win32", "hwnd": 5})
    )
    monkeypatch.setattr(computer_client, "_read_state", lambda c, i: {"toggle": 1})
    chain = MagicMock()
    monkeypatch.setattr(computer_client, "_run_chain", chain)
    res = computer_client.set_checked(hwnd=1, element_index=3, checked=True)
    chain.assert_not_called()
    assert res == {
        "success": True,
        "already": True,
        "verified": True,
        "method": "none",
        "family": "Win32",
        "element_index": 3,
        "checked": True,
    }


def test_index_from_another_window_is_refused_not_reread(monkeypatch):
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "_element_cache", {1: MagicMock()})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", 111)
    reread = MagicMock()
    monkeypatch.setattr(computer_client, "get_window_state", reread)
    with pytest.raises(ValueError, match="autre fenêtre"):
        computer_client.select_option("Bravo", hwnd=222, element_index=1)
    reread.assert_not_called()


def test_check_expect_reads_window_title(monkeypatch):
    monkeypatch.setattr(computer_client, "_window_text", lambda h: "Rapport — Enregistré")
    assert computer_client.check_expect(1, {"title_contains": "enregistré"})[0] is True
    assert computer_client.check_expect(1, {"title": "Autre"})[0] is False
    with pytest.raises(ValueError, match="vide"):
        computer_client.check_expect(1, {})


def test_type_text_message_mode_refuses_non_edit(monkeypatch):
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_read_state", lambda c, i: {"value": ""})
    monkeypatch.setattr(computer_client, "_native_kind", lambda h: "")
    with pytest.raises(RuntimeError, match="arrière-plan"):
        computer_client.type_text("x", hwnd=1, element_index=1, method="message")


def test_emergency_stop_still_blocks_background_messages():
    emergency_stop.pressed()
    with pytest.raises(emergency_stop.EmergencyStopError):
        computer_client.select_option("Bravo", hwnd=1, element_index=1)
    with pytest.raises(emergency_stop.EmergencyStopError):
        computer_client.menu_command("Fichier > Marquer", hwnd=1)
    with pytest.raises(emergency_stop.EmergencyStopError):
        computer_client.set_checked(hwnd=1, element_index=1)


# =============================================================================
# 5. Validation réelle : branchée dans test.ps1 -Full
# =============================================================================
def test_test_ps1_full_runs_desktop_validation():
    script = (REPO_ROOT / "test.ps1").read_text(encoding="utf-8")
    assert "tests\\live_computer_validation.py" in script
    assert "live_browser_validation" not in script  # pont Chrome : NexusBrowser\test.ps1 -Full
    live = (REPO_ROOT / "tests" / "live_computer_validation.py").read_text(encoding="utf-8")
    assert "PHYSICAL_IDLE_S = 120.0" in live
    assert "SWP_NOACTIVATE" in live and "ShowWithoutActivation" in live
    assert '"skipped"' in live and "sautée (Julien actif" in live


# =============================================================================
# 6. Liste déroulante Win32/WinForms OUVERTE (banc du 16/10 : « Bravo introuvable », choix perdu)
# =============================================================================
CBN_CLOSEUP = 8


def test_open_combo_is_listed_then_choice_survives_closing_in_the_right_order(hidden_controls):
    ctl = hidden_controls
    drop = win32_controls.combo_list_of(ctl.combo)
    assert drop and win32_controls.class_name(drop) == "ComboLBox"
    assert win32_controls.combo_owning(drop, ctl.parent) == ctl.combo
    assert win32_controls.combo_show_dropdown(ctl.combo, True) == "cb_showdropdown"
    assert win32_controls.combo_dropped(ctl.combo) is True
    assert win32_controls.combo_show_dropdown(ctl.combo, True) == "already"
    assert win32_controls.listbox_items(drop) == ["Alpha", "Bravo", "Charlie"]  # LB_GETTEXT sur la ComboLBox
    ctl.pump()
    ctl.commands.clear()
    assert win32_controls.combo_select(ctl.combo, "Bravo") == "cb_setcursel"
    ctl.pump()
    assert win32_controls.combo_dropped(ctl.combo) is False
    assert win32_controls.combo_selected(ctl.combo) == "Bravo"  # la fermeture (annulation) n'a pas tout défait
    codes = [code for ident, code in ctl.commands if ident == 14]
    # Fermeture d'abord (le contrôle envoie lui-même SELENDCANCEL puis CLOSEUP), choix ensuite : SELENDOK, SELCHANGE.
    assert codes[-2:] == [win32_controls.CBN_SELENDOK, win32_controls.CBN_SELCHANGE]
    assert CBN_CLOSEUP in codes and codes.index(CBN_CLOSEUP) < codes.index(win32_controls.CBN_SELENDOK)


def test_click_on_open_list_item_selects_through_its_combo(hidden_controls, monkeypatch):
    ctl = hidden_controls
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)
    win32_controls.combo_show_dropdown(ctl.combo, True)
    drop = win32_controls.combo_list_of(ctl.combo)
    info = {"type": "ListItem", "name": "Charlie", "hwnd": 0, "host_hwnd": drop, "framework": "Win32"}
    fam, chain, verify = computer_client._click_plan(None, info, ctl.parent)  # combo retrouvé par sa ComboLBox
    assert fam == "Win32" and chain[0][0] == "CB_SETCURSEL"
    assert not any(name == "UIA Invoke" for name, _ in chain)  # jamais l'action MSAA (vrai double-clic)
    out = computer_client._run_chain(chain, verify, 0)
    assert out["verified"] is True and "liste refermée" in out["verified_by"]
    assert win32_controls.combo_selected(ctl.combo) == "Charlie"


def test_click_on_native_combo_toggles_its_list_by_message(hidden_controls, monkeypatch):
    ctl = hidden_controls
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)
    info = {"type": "ComboBox", "name": "Formule", "hwnd": ctl.combo, "host_hwnd": ctl.combo, "framework": "Win32",
            "props": {"has_invoke": True, "has_expand": False}}  # fmt: skip
    _fam, chain, verify = computer_client._click_plan(None, info, ctl.parent)
    assert chain[0][0] == "CB_SHOWDROPDOWN" and not any(name == "UIA Invoke" for name, _ in chain)
    out = computer_client._run_chain(chain, verify, 0)
    assert out["verified"] is True and win32_controls.combo_dropped(ctl.combo) is True
    _fam, chain, verify = computer_client._click_plan(None, info, ctl.parent)
    assert computer_client._run_chain(chain, verify, 0)["verified"] is True
    assert win32_controls.combo_dropped(ctl.combo) is False


def test_set_expanded_opens_native_combo_and_skips_when_already(hidden_controls, monkeypatch):
    ctl = hidden_controls
    info = {"type": "ComboBox", "name": "Formule", "hwnd": ctl.combo, "host_hwnd": ctl.combo, "framework": "Win32"}
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: ctl.parent)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "_target_element", lambda h, i, t, b=None: (5, None, info))
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)
    opened = computer_client.set_expanded(hwnd=ctl.parent, element_index=5, expanded=True)
    assert opened["verified"] is True and opened["technique"] == "CB_SHOWDROPDOWN"
    assert computer_client.set_expanded(hwnd=ctl.parent, element_index=5, expanded=True)["already"] is True
    assert win32_controls.open_combo_lists(ctl.parent) == [(ctl.combo, win32_controls.combo_list_of(ctl.combo))]
    assert computer_client.set_expanded(hwnd=ctl.parent, element_index=5, expanded=False)["verified"] is True
    assert win32_controls.open_combo_lists(ctl.parent) == []


def test_label_missing_from_last_look_is_looked_up_again(monkeypatch):
    """Lot « ouvrir la liste puis choisir » : l'option n'existait pas au dernier look, la fenêtre est relue une fois."""
    reads = []

    def fake_state(hwnd=None, max_elements=80, **kw):
        reads.append(hwnd)
        computer_client._element_cache.clear()
        computer_client._element_info.clear()
        names = ["Formule"] if len(reads) == 1 else ["Formule", "Bravo"]
        for i, name in enumerate(names, start=1):
            computer_client._element_cache[i] = object()
            computer_client._element_info[i] = {"name": name}
        monkeypatch.setattr(computer_client, "_cached_window_hwnd", hwnd)

    monkeypatch.setattr(computer_client, "get_window_state", fake_state)
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", 0)
    computer_client._element_cache.clear()
    computer_client._element_info.clear()
    assert computer_client._resolve_step_target({"target": "Formule"}, 77) == (1, None)
    assert computer_client._resolve_step_target({"target": "Bravo"}, 77) == (2, None)
    assert reads == [77, 77]
    with pytest.raises(ValueError, match="introuvable"):
        computer_client._resolve_step_target({"target": "Zoulou"}, 77)
    computer_client._element_cache.clear()
    computer_client._element_info.clear()


class _LevelElement(_FakeElement):
    """Élément factice qui sait se relire (BuildUpdatedCache) ; les relectures sont notées."""

    rebuilt: list = []

    def BuildUpdatedCache(self, cache):
        type(self).rebuilt.append((self.props.get("hwnd"), cache))
        return self


def test_tree_skips_open_combo_subtree_and_reads_the_rest(monkeypatch):
    ids = uia_fast.U
    item = _LevelElement({"control_type": ids.UIA_ListItemControlTypeId, "name": "Bravo"})
    combo = _LevelElement({"control_type": ids.UIA_ComboBoxControlTypeId, "name": "Formule", "hwnd": 30}, [item])
    button = _LevelElement({"control_type": ids.UIA_ButtonControlTypeId, "name": "Valider", "hwnd": 40})
    root = _LevelElement({"control_type": ids.UIA_WindowControlTypeId, "hwnd": 1}, [combo, button])
    reader = _reader(root)
    reader.cache_level = "niveau"  # pyright: ignore[reportAttributeAccessIssue]
    _LevelElement.rebuilt = []
    monkeypatch.setattr(uia_fast, "_contains", lambda ancestor, hwnd: ancestor in (hwnd, 1))
    tree = reader.read_tree(1, skip_subtrees=[30])
    assert tree.status == "ok" and tree.method == "uia_cache_partial"
    assert [n.name for n in tree.nodes] == ["", "Formule", "Valider"]  # l'option de la liste ouverte n'est pas lue
    assert all(hwnd != 30 for hwnd, _ in _LevelElement.rebuilt)
    assert (40, reader.cache_tree) in _LevelElement.rebuilt


# --- Revue des correctifs du 16/10 au soir (BS_OWNERDRAW, attente COM, ciblage hors champ) ---------------------------


def test_winforms_ownerdraw_checkbox_never_gets_bn_clicked():
    """Cases et boutons radio WinForms sont BS_OWNERDRAW comme les boutons : seul le rôle « Button » reçoit BN_CLICKED."""
    base = {"framework": "WinForms", "hwnd": 7, "props": ALL_PATTERNS}
    ownerdraw = win32_controls.BS_OWNERDRAW
    assert "BN_CLICKED" in _plan({**base, "type": "Button", "name": "OK"}, own_kind="button", button_kind=ownerdraw)
    for role in ("CheckBox", "RadioButton"):
        names = _plan({**base, "type": role, "name": "Case"}, own_kind="button", button_kind=ownerdraw)
        assert "BN_CLICKED" not in names, role


def test_invoke_wait_falls_back_to_join_without_com_on_the_calling_thread():
    """Sans COM sur le fil appelant, CoWaitForMultipleHandles rend la main tout de suite : jamais de faux « pending »."""
    import threading

    pattern = SimpleNamespace(Invoke=lambda: time.sleep(0.3))
    ctrl = SimpleNamespace(GetInvokePattern=lambda: pattern)
    out: list[str] = []
    worker = threading.Thread(target=lambda: out.append(computer_client._invoke_with_timeout(ctrl)))  # fil sans COM
    worker.start()
    worker.join(timeout=10)
    assert out == ["invoked"]


def test_invoke_wait_pumps_com_on_an_sta_thread():
    import threading

    pattern = SimpleNamespace(Invoke=lambda: time.sleep(0.2))
    ctrl = SimpleNamespace(GetInvokePattern=lambda: pattern)
    out: list[object] = []

    def sta() -> None:
        ctypes.windll.ole32.CoInitialize(None)
        try:
            out.append(computer_client._invoke_with_timeout(ctrl))
            done = threading.Thread(target=lambda: None)
            done.start()
            out.append(computer_client._com_wait_thread(done, 1.0))
        finally:
            ctypes.windll.ole32.CoUninitialize()

    worker = threading.Thread(target=sta)
    worker.start()
    worker.join(timeout=10)
    assert out == ["invoked", True]


def _hit_nodes(*nodes):
    root = SimpleNamespace(control_type="Window", rect=(0, 0, 500, 500), props={})
    tree = SimpleNamespace(status="ok", nodes=[root, *nodes])
    return (
        patch.object(computer_client.user32, "IsWindow", return_value=1),
        patch.object(computer_client, "_open_combo_items", return_value=[]),
        patch.object(computer_client, "_window_tree", return_value=tree),
        patch.object(win32_controls, "family", return_value="WinForms"),
        patch.object(
            computer_client, "get_window_rect", return_value={"left": 0, "top": 0, "right": 500, "bottom": 500}
        ),
        patch.object(computer_client, "_node_info", side_effect=lambda node: {"name": node.name}),
        patch.object(computer_client, "_wrap_element", side_effect=lambda element, info: element),
    )


def _node(name, rect, offscreen):
    return SimpleNamespace(control_type="Button", rect=rect, props={"offscreen": offscreen}, name=name, element=name)


def test_hit_test_prefers_visible_control_over_hidden_smaller_one():
    visible = _node("Valider", (100, 100, 200, 140), False)
    hidden_row = _node("ligne masquée", (110, 110, 150, 125), True)  # plus petite, masquée par le défilement
    patches = _hit_nodes(hidden_row, visible)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        _ctrl, info = computer_client._hit_test(5, 120, 115) or (None, {})
    assert info["name"] == "Valider"


def test_hit_test_accepts_offscreen_control_inside_window_as_last_resort():
    """Fenêtre WinForms recouverte : UIA dit tout « hors champ », le contrôle sous le point reste trouvé."""
    covered = _node("Valider", (100, 100, 200, 140), True)
    outside = _node("ailleurs", (600, 600, 700, 700), True)
    patches = _hit_nodes(covered, outside)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        _ctrl, info = computer_client._hit_test(5, 120, 115) or (None, {})
        assert info["name"] == "Valider"
        assert computer_client._hit_test(5, 650, 650) is None
