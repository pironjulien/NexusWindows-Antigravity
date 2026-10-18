"""Durcissement 2026-10-15 : arrêt d'urgence commun, gardes des entrées physiques, act sans perte, Invoke honnête,
recadrage PrintWindow (le pont Chrome et ses tests vivent dans NexusBrowser)."""

import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "client"))

import computer_client  # noqa: E402
import emergency_stop  # noqa: E402

from client import emergency_stop as package_stop  # noqa: E402
from client import mcp_server  # noqa: E402


def _write_stop(path: Path, age_s: float = 0.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"by": "Test", "nonce": os.urandom(4).hex()}), encoding="utf-8")
    if age_s:
        stamp = time.time() - age_s
        os.utime(path, (stamp, stamp))


class RecordingGuard:
    """FocusGuard factice : enregistre son usage sans jeton réel, sans attente ni déplacement du focus."""

    uses: list = []

    def __init__(self, target_hwnd=None, restore=True, wait_idle=True, use_lock=True, purpose="action physique"):
        self.target_hwnd = target_hwnd
        self.restore = restore

    def __enter__(self):
        emergency_stop.check()
        RecordingGuard.uses.append((self.target_hwnd, self.restore))
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def guard():
    RecordingGuard.uses = []
    with (
        patch.object(computer_client, "FocusGuard", RecordingGuard),
        # garde factice : cible tenue pour relue au premier plan, aucun champ mot de passe sous le focus
        patch.object(computer_client, "_require_front", lambda what="": None),
        patch.object(computer_client, "_focused_is_password", return_value=False),
    ):
        yield RecordingGuard


# -----------------------------------------------------------------------------
# Arrêt d'urgence commun
# -----------------------------------------------------------------------------
def test_stop_files_are_redirected_in_tests():
    real = Path.home() / ".nexus" / "stop"
    for module in (emergency_stop, package_stop):
        assert module.STOP_FILE != real
        assert module.OWNER_FILE != real.with_name("stop.owner")


def test_fresh_stop_blocks_actions_but_not_reads():
    _write_stop(emergency_stop.STOP_FILE)
    assert 0 < emergency_stop.remaining_s() <= emergency_stop.HOLD_S
    with patch.object(computer_client, "mouse_click") as mouse_click:
        with pytest.raises(emergency_stop.EmergencyStopError, match="Arrêt d'urgence demandé par Julien"):
            computer_client.click(x=1, y=1, coords="screen")
        mouse_click.assert_not_called()
    for action in (
        lambda: computer_client.press_key("enter"),
        lambda: computer_client.scroll(delta_y=-1),
        lambda: computer_client.drag(0, 0, 5, 5, coords="screen"),
        lambda: computer_client.mouse_move(1, 1, coords="screen"),
        lambda: computer_client.open_path("C:\\"),
        lambda: computer_client.act(steps=[{"action": "wait", "seconds": 0.01}], then="none"),
    ):
        with pytest.raises(emergency_stop.EmergencyStopError):
            action()
    assert isinstance(computer_client.list_windows(), list)  # lecture permise


def test_old_stop_file_is_ignored():
    _write_stop(emergency_stop.STOP_FILE, age_s=200)
    assert emergency_stop.remaining_s() == 0
    emergency_stop.check()


def test_deleting_the_stop_file_does_not_lift_the_stop():
    _write_stop(emergency_stop.STOP_FILE)
    assert emergency_stop.remaining_s() > 0
    emergency_stop.STOP_FILE.unlink()
    assert emergency_stop.remaining_s() > 100
    with pytest.raises(emergency_stop.EmergencyStopError):
        emergency_stop.check()


def test_hotkey_press_writes_shared_stop_and_heartbeat():
    emergency_stop.pressed()
    data = json.loads(emergency_stop.STOP_FILE.read_text(encoding="utf-8"))
    assert data["by"] == "NexusAGY"
    assert data["pid"] == os.getpid()
    assert data["hold_s"] == 120
    assert set(data) == {"by", "pid", "at", "hold_s", "nonce"}
    assert emergency_stop.remaining_s() > 119
    first_nonce = data["nonce"]
    emergency_stop.request()
    assert json.loads(emergency_stop.STOP_FILE.read_text(encoding="utf-8"))["nonce"] != first_nonce

    emergency_stop.heartbeat()
    beat = json.loads(emergency_stop.OWNER_FILE.read_text(encoding="utf-8"))
    assert set(beat) == {"owner", "pid", "version", "ts"}
    assert beat["owner"] == "NexusAGY"
    owner = emergency_stop.owner()
    assert owner is not None and owner["pid"] == os.getpid()


def test_watch_thread_latches_stop_while_idle():
    until = threading.Event()
    with patch.object(emergency_stop, "WATCH_S", 0.01):
        watcher = threading.Thread(target=emergency_stop._watch, args=(until,), daemon=True)
        watcher.start()
        try:
            _write_stop(emergency_stop.STOP_FILE)
            deadline = time.monotonic() + 2
            while emergency_stop._latched_until == 0.0 and time.monotonic() < deadline:
                time.sleep(0.01)
        finally:
            until.set()
            watcher.join(timeout=2)
    assert emergency_stop._latched_until > 0
    emergency_stop.STOP_FILE.unlink()
    assert emergency_stop.remaining_s() > 0


def test_act_stops_between_steps_and_keeps_report():
    original = computer_client._run_act_step
    calls = []

    def run_then_press(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(args[0])
        emergency_stop.pressed()  # Julien appuie pendant la première étape
        return result

    with patch.object(computer_client, "_run_act_step", side_effect=run_then_press):
        res = computer_client.act(
            steps=[{"action": "wait", "seconds": 0.01}, {"action": "wait", "seconds": 0.01}], hwnd=1, then="none"
        )
    assert calls == ["wait"]
    assert res["success"] is False
    assert res["executed_steps"] == 2
    assert res["steps"][0]["status"] == "ok"
    assert res["steps"][1]["error_type"] == "EmergencyStopError"


def test_typing_stops_at_next_character(guard):
    sent = []

    def send(inputs):
        sent.append(inputs)
        if len(sent) == 2:
            emergency_stop.pressed()
        return len(inputs)

    with patch.object(computer_client, "_send_inputs", side_effect=send):
        with patch.object(computer_client, "is_protected_system_window", return_value=(False, "")):
            with pytest.raises(emergency_stop.EmergencyStopError):
                computer_client.type_text("abcdefgh", hwnd=1, method="typing", foreground=True)
    assert len(sent) == 2


# -----------------------------------------------------------------------------
# Point 9 : scroll, drag et mouse_move passent par FocusGuard
# -----------------------------------------------------------------------------
def test_scroll_wheel_goes_through_focus_guard(guard):
    with (
        patch.object(computer_client, "_send_inputs", return_value=1) as send,
        patch.object(computer_client, "_wait_window_effect", return_value=(None, "")),  # fenêtre réelle de Julien
    ):
        res = computer_client.scroll(delta_y=-2, hwnd=1, x=5, y=5, foreground=True)
    assert res["success"] is None  # molette envoyée, aucun effet relu : inconnu, pas « réussi »
    assert res["verified"] is None
    assert len(guard.uses) == 1
    assert guard.uses[0][1] is True  # restauration du focus et du curseur par défaut
    send.assert_called_once()


def test_drag_goes_through_focus_guard_and_always_releases_button(guard):
    flags = []

    def send(inputs):
        flags.append(inputs[0].union.mi.dwFlags)
        return 1

    with patch.object(computer_client, "_send_inputs", side_effect=send):
        with patch.object(computer_client.user32, "SetCursorPos", return_value=1):
            res = computer_client.drag(0, 0, 10, 10, hwnd=1, coords="screen", steps=2, delay_ms=0, foreground=True)
            assert res["success"] is None
            assert res["verified"] is None
            assert len(guard.uses) == 1
            assert flags == [computer_client.MOUSEEVENTF_LEFTDOWN, computer_client.MOUSEEVENTF_LEFTUP]

            flags.clear()
            checks = {"n": 0}
            real_check = emergency_stop.check

            def check_then_stop():
                checks["n"] += 1
                if checks["n"] == 4:  # arrêt pendant le geste, bouton enfoncé (1 : drag, 2 : garde, 3 : avant appui)
                    emergency_stop.pressed()
                real_check()

            with patch.object(emergency_stop, "check", side_effect=check_then_stop):
                with pytest.raises(emergency_stop.EmergencyStopError):
                    computer_client.drag(0, 0, 10, 10, hwnd=1, coords="screen", steps=5, delay_ms=0, foreground=True)
    assert flags[-1] == computer_client.MOUSEEVENTF_LEFTUP


def test_mouse_move_goes_through_focus_guard(guard):
    with (
        patch.object(computer_client.user32, "SetCursorPos", return_value=1),
        patch.object(computer_client, "_cursor_pos", return_value=(5, 5)),
    ):
        res = computer_client.mouse_move(
            5, 5, hwnd=1, coords="screen", smooth=False, restore_focus=False, foreground=True
        )
    assert res["success"] is True
    assert guard.uses == [(1, False)]


# -----------------------------------------------------------------------------
# Point 10 : act rend toujours le compte rendu et un succès fidèle
# -----------------------------------------------------------------------------
def test_act_reports_executed_steps_when_a_step_raises():
    res = computer_client.act(
        steps=[{"action": "wait", "seconds": 0.01}, {"action": "voler"}, {"action": "wait", "seconds": 0.01}],
        hwnd=1,
        then="none",
    )
    assert res["success"] is False
    assert res["executed_steps"] == 2
    assert res["total_steps"] == 3
    assert res["steps"][0]["status"] == "ok"
    assert res["steps"][1]["status"] == "error"
    assert "voler" in res["steps"][1]["error"]
    assert "error" in res


def test_act_success_reflects_step_failure(guard):
    with patch.object(computer_client, "focus_window", return_value={"success": False}):
        res = computer_client.act(
            steps=[{"action": "focus"}, {"action": "wait", "seconds": 0.01}], hwnd=1, then="none", foreground=True
        )
    assert res["success"] is False
    assert res["executed_steps"] == 1
    assert res["steps"][0]["status"] == "failed"
    assert res["steps"][0]["mark"] == "✗"


def test_act_focus_without_foreground_is_refused_explicitly():
    with patch.object(computer_client, "focus_window") as focus:
        res = computer_client.act(steps=[{"action": "focus"}], hwnd=1, then="none")
    focus.assert_not_called()
    assert res["success"] is False
    assert res["steps"][0]["error_type"] == "NeedsForegroundError"


# -----------------------------------------------------------------------------
# Point 11 : Invoke honnête, jamais de clic physique après un Invoke sans retour
# -----------------------------------------------------------------------------
def _invoke_ctrl(invoke_side_effect=None):
    ctrl = MagicMock()
    invoke = MagicMock()
    invoke.Invoke.side_effect = invoke_side_effect
    ctrl.GetInvokePattern.return_value = invoke
    ctrl.GetTogglePattern.return_value = None
    ctrl.GetSelectionItemPattern.return_value = None
    ctrl.GetExpandCollapsePattern.return_value = None
    ctrl.BoundingRectangle = MagicMock(left=0, right=10, top=0, bottom=10)
    return ctrl


def test_invoke_success_is_not_claimed_verified():
    with patch.object(computer_client, "get_cached_element", return_value=_invoke_ctrl()):
        with patch.object(computer_client, "mouse_click") as mouse_click:
            res = computer_client.click(hwnd=1234, element_index=1)
    assert res["success"] is None  # Invoke parti, aucun effet relu : jamais « réussi »
    assert res["method"] == "uia_invoke"
    assert res["verified"] is None
    mouse_click.assert_not_called()


def test_invoke_timeout_never_chains_a_physical_click():
    release = threading.Event()
    ctrl = _invoke_ctrl(lambda: release.wait(5))
    try:
        with patch.object(computer_client, "INVOKE_TIMEOUT_S", 0.1):
            with patch.object(computer_client, "get_cached_element", return_value=ctrl):
                with patch.object(computer_client, "mouse_click") as mouse_click:
                    res = computer_client.click(hwnd=1234, element_index=1)
        assert res["pending"] is True
        assert res["success"] is None
        assert res["verified"] is None
        mouse_click.assert_not_called()
        ctrl.GetTogglePattern.assert_not_called()
    finally:
        release.set()


def test_invoke_error_falls_back_and_reports_it(guard):
    ctrl = _invoke_ctrl(RuntimeError("COM Invoke Failed"))
    with patch.object(computer_client, "get_cached_element", return_value=ctrl):
        with patch.object(computer_client, "is_point_occluded", return_value=False):
            with patch.object(computer_client, "mouse_click") as mouse_click:
                res = computer_client.click(hwnd=1234, element_index=1, restore_focus=False, foreground=True)
    assert res["method"] == "element_center"
    assert "COM Invoke Failed" in res["invoke_error"]
    mouse_click.assert_called_once()


# -----------------------------------------------------------------------------
# Point 12 : PrintWindow recadré sur le cadre DWM
# -----------------------------------------------------------------------------
def test_dwm_crop_box_removes_invisible_borders():
    window = {"left": 100, "top": 50, "right": 916, "bottom": 657}
    frame = {"left": 107, "top": 50, "right": 909, "bottom": 650}
    assert computer_client._dwm_crop_box(window, frame) == (7, 0, 809, 600)
    assert computer_client._dwm_crop_box(window, {"left": 0, "top": 0, "right": 0, "bottom": 0}) == (0, 0, 816, 607)


def test_background_capture_matches_dwm_bounds():
    foreground = computer_client.user32.GetForegroundWindow()
    for window in computer_client.list_windows(visible_only=True):
        if window["hwnd"] == foreground:
            continue
        image = computer_client.capture_window_background_gdi(window["hwnd"])
        if image is None:
            continue
        rect = computer_client.get_window_rect(window["hwnd"])
        assert image.size == (rect["width"], rect["height"])
        return
    pytest.skip("Aucune fenêtre d'arrière-plan capturable par PrintWindow")


# -----------------------------------------------------------------------------
# Points 3 à 8 côté pont Chrome : tests déplacés dans NexusBrowser (tests/test_hardening.py)
# -----------------------------------------------------------------------------
def test_hotkey_note_surfaces_in_computer_results(monkeypatch):
    monkeypatch.setattr(package_stop, "hotkey_note", lambda: "Arrêt d'urgence NON GARANTI")
    result = json.loads(mcp_server.computer_list_apps())
    assert result["warning"] == "Arrêt d'urgence NON GARANTI"


# -----------------------------------------------------------------------------
# Mise au premier plan voulue : jeton commun (essai de cohabitation du 16/10)
# -----------------------------------------------------------------------------
def _shared_lock_module():
    shared_dir = REPO_ROOT.parent / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    import foreground_lock

    return foreground_lock


def test_focus_window_takes_and_releases_shared_token(tmp_path):
    lock = _shared_lock_module()
    seen = {}

    def activate(hwnd):
        seen["holder"] = lock.holder()
        return True

    with (
        patch.object(lock, "LOCK_FILE", tmp_path / "foreground.lock"),
        patch.object(computer_client, "ensure_default_desktop"),
        patch.object(computer_client, "resolve_window", return_value=4242),
        patch.object(computer_client, "_activate_window", side_effect=activate),
        patch.object(computer_client, "_target_in_front", return_value=True),
        patch.object(computer_client, "get_window_rect", return_value={}),
    ):
        res = computer_client.focus_window(hwnd=4242)
        assert res["success"] is True
        assert seen["holder"]["owner"] == "NexusAGY"
        assert seen["holder"]["purpose"] == "mise au premier plan (computer_focus_window)"
        assert lock.holder() is None  # rendu aussitôt après


def test_focus_window_does_nothing_when_another_agent_holds_token():
    lock = _shared_lock_module()
    with (
        patch.object(lock.ForegroundLock, "acquire", return_value=False),
        patch.object(lock, "holder", return_value={"owner": "NexusClaude", "purpose": "lot au premier plan"}),
        patch.object(computer_client, "ensure_default_desktop"),
        patch.object(computer_client, "resolve_window", return_value=4242),
        patch.object(computer_client, "_activate_window") as activate,
    ):
        with pytest.raises(TimeoutError, match="NexusClaude tient la souris et le premier plan"):
            computer_client.focus_window(hwnd=4242)
        activate.assert_not_called()


def test_computer_tool_descriptions_say_token_is_automatic():
    """AGY ne doit pas aller lire le code pour savoir si le jeton est géré (essai du 16/10)."""
    act_doc = mcp_server.computer_act.__doc__ or ""
    assert "Surpasse" not in act_doc
    assert "sans lire le code" in act_doc
    assert "foreground=True" in act_doc and "jeton commun" in act_doc
    assert "jamais pour préparer" in (mcp_server.computer_focus_window.__doc__ or "")
    skill = (REPO_ROOT / "plugins/nexus-computer/skills/nexus-computer/SKILL.md").read_text(encoding="utf-8")
    assert "sans lire le code" in skill and "foreground.lock" in skill
