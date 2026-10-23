import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIR = REPO_ROOT / "client"
sys.path.insert(0, str(CLIENT_DIR))

import computer_client  # noqa: E402
import mcp_server  # noqa: E402


class _NoOpGuard:
    """FocusGuard neutre : ni jeton réel, ni attente de pause, ni restauration du curseur pendant les tests."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_list_windows_returns_valid_structure():
    windows = computer_client.list_windows(visible_only=True)
    assert isinstance(windows, list)
    if windows:
        first = windows[0]
        assert "hwnd" in first
        assert "title" in first
        assert "process_name" in first
        assert "bounds" in first
        assert "width" in first["bounds"]
        assert "height" in first["bounds"]
        assert "is_foreground" in first


def test_list_apps_aggregates_windows():
    apps = computer_client.list_apps()
    assert isinstance(apps, list)
    if apps:
        app = apps[0]
        assert "process_name" in app
        assert "window_count" in app
        assert "windows" in app
        assert app["window_count"] >= 1


def test_get_window_state_extracts_elements():
    windows = computer_client.list_windows(visible_only=True)
    if not windows:
        pytest.skip("No visible windows found on system")
    target = windows[0]["hwnd"]
    state = computer_client.get_window_state(hwnd=target, max_elements=20, capture_screenshot=False)
    assert state["hwnd"] == target
    assert "title" in state
    assert "bounds" in state
    assert "elements" in state
    assert isinstance(state["elements"], list)
    if state["elements"]:
        el = state["elements"][0]
        assert "index" in el
        assert "type" in el
        assert "relative_center" in el
        assert "box_2d" in el
        assert len(el["box_2d"]) == 4


def test_capture_window_image_anti_crash_400():
    windows = computer_client.list_windows(visible_only=True)
    if not windows:
        pytest.skip("No visible windows found on system")
    target = windows[0]["hwnd"]
    webp_bytes = computer_client.capture_window_image(hwnd=target)
    assert isinstance(webp_bytes, bytes)
    assert len(webp_bytes) > 0
    # Must strictly satisfy Anti-Crash 400 (< 200 KB)
    assert len(webp_bytes) < 200 * 1024


def test_press_key_validation():
    with pytest.raises(ValueError, match="Combinaison de touches vide"):
        computer_client.press_key("", hwnd=0)

    with pytest.raises(ValueError, match="Touche inconnue"):
        computer_client.press_key("ctrl+invalidkey123", hwnd=0)


def test_mcp_server_computer_tools():
    # 1. computer_list_windows tool
    res_raw = mcp_server.computer_list_windows()
    res = json.loads(res_raw)
    assert res["status"] == "success"
    assert isinstance(res["data"], list)

    # 2. computer_list_apps tool
    res_apps_raw = mcp_server.computer_list_apps()
    res_apps = json.loads(res_apps_raw)
    assert res_apps["status"] == "success"
    assert isinstance(res_apps["data"], list)

    # 3. computer_take_screenshot tool
    windows = res["data"]
    if windows:
        target = windows[0]["hwnd"]
        shot_raw = mcp_server.computer_take_screenshot(hwnd=target)
        shot_res = json.loads(shot_raw)
        assert shot_res["status"] == "success"
        assert shot_res["data"]["size_bytes"] < 200 * 1024


def test_mcp_modular_scopes():
    computer_tools = [t.name for t in mcp_server.computer_mcp._tool_manager.list_tools()]

    # 5 noms communs listés (windows, look, act, launch, window) + 15 noms computer_… appelables, non listés
    common = {"windows", "look", "act", "launch", "window"}
    assert len(computer_tools) == 20
    assert set(mcp_server.listed_tool_names(mcp_server.computer_mcp)) == common  # ce que Gemini voit
    assert all(name.startswith("computer_") for name in set(computer_tools) - common)
    assert not hasattr(mcp_server, "browser_mcp")


def test_press_key_punctuation():
    # Should resolve punctuation keys properly via VkKeyScanW without hardware side-effects
    with (
        patch.object(computer_client, "_send_inputs", return_value=2),
        patch.object(computer_client, "FocusGuard", _NoOpGuard),
        patch.object(computer_client, "_wait_window_effect", return_value=(None, "")),
    ):
        res = computer_client.press_key("ctrl+,", hwnd=4242, foreground=True)
        assert res["sent"] is True
        assert res["success"] is not False
        assert len(res["vk_codes"]) >= 2

        res_dot = computer_client.press_key("ctrl+.", hwnd=4242, foreground=True)
        assert res_dot["sent"] is True
        assert len(res_dot["vk_codes"]) >= 2


def test_dwm_bounds_accurate():
    windows = computer_client.list_windows(visible_only=True)
    if windows:
        rect = computer_client.get_window_rect(windows[0]["hwnd"])
        assert rect["width"] > 0
        assert rect["height"] > 0


def test_mouse_move_smooth():
    # Verify smooth calculation without displacing the user's physical mouse cursor
    with (
        patch.object(computer_client.user32, "SetCursorPos", return_value=1),
        patch.object(computer_client, "_cursor_pos", return_value=(10, 10)),
        patch.object(computer_client, "FocusGuard", _NoOpGuard),
        patch.object(computer_client, "_require_front", lambda what="": None),
    ):
        res = computer_client.mouse_move(
            x=10, y=10, hwnd=4242, coords="screen", smooth=True, steps=3, duration_ms=10, foreground=True
        )
        assert res["success"] is True
        assert res["verified"] is True  # position du curseur relue
        assert res["smooth"] is True


def test_cleanup_screenshot_cache():
    cleaned = computer_client.cleanup_screenshot_cache(max_files=100, max_age_hours=48.0)
    assert isinstance(cleaned, int)
    assert cleaned >= 0


def test_annotate_screenshot_som():
    windows = computer_client.list_windows(visible_only=True)
    if windows:
        target = windows[0]["hwnd"]
        state = computer_client.get_window_state(
            hwnd=target, max_elements=5, capture_screenshot=True, annotate_screenshot=True
        )
        assert state["hwnd"] == target
        assert "screenshot_path" in state


def test_is_point_occluded_validation():
    assert computer_client.is_point_occluded(0, 0, 0) is False


def test_clipboard_set_get_unicode():
    orig = computer_client.get_clipboard_text()
    test_str = "Prompt Antigravity SOTA 🚀 | Ligne 2: éàçù | Ligne 3: `code`"
    success = computer_client.set_clipboard_text(test_str)
    assert success is True
    read_back = computer_client.get_clipboard_text()
    assert read_back == test_str
    # Restore original clipboard
    if orig is not None:
        computer_client.set_clipboard_text(orig)


def test_resolve_box_2d_coords():
    windows = computer_client.list_windows(visible_only=True)
    if not windows:
        pytest.skip("No visible windows found on system")
    target = windows[0]["hwnd"]
    rect = computer_client.get_window_rect(target)
    # Box in center [400, 400, 600, 600]
    box = [400, 400, 600, 600]
    sx, sy = computer_client.resolve_box_2d_coords(box, target)
    expected_x = rect["left"] + int(0.5 * rect["width"])
    expected_y = rect["top"] + int(0.5 * rect["height"])
    assert abs(sx - expected_x) <= 2
    assert abs(sy - expected_y) <= 2


def test_is_electron_window_detection():
    # If Antigravity is open, it should be recognized as Electron
    windows = computer_client.list_windows(visible_only=True)
    for w in windows:
        if "antigravity" in w["process_name"].lower():
            assert computer_client.is_electron_window(w["hwnd"]) is True
            break


def test_computer_logger_records_actions():
    import computer_logger

    logger = computer_logger.get_logger()
    assert logger is not None
    computer_logger.log_action(
        action="test_action",
        method="unit_test",
        target=12345,
        duration_ms=12.5,
        status="SUCCESS",
        details={"key": "value"},
    )
    log_path = computer_logger.LOG_FILE
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "[TEST_ACTION]" in content
    assert "unit_test" in content


def test_get_window_state_query_filtering():
    windows = computer_client.list_windows(visible_only=True)
    if not windows:
        pytest.skip("No visible windows found on system")
    target = windows[0]["hwnd"]
    state_all = computer_client.get_window_state(hwnd=target, max_elements=50)
    assert "elements" in state_all
    # Filter with an impossible query
    state_filtered = computer_client.get_window_state(hwnd=target, max_elements=50, query="XYZNONEXISTENT9999")
    assert len(state_filtered["elements"]) == 0


def test_close_window_validation():
    with pytest.raises(ValueError, match="invalide ou fenêtre déjà fermée"):
        computer_client.close_window(0)


def test_get_cached_element_rejects_cross_window_controls():
    # Setup dummy cache for window 11111
    class DummyCtrl:
        NativeWindowHandle = 11111
        BoundingRectangle = None

    computer_client._element_cache = {1: DummyCtrl()}
    computer_client._cached_window_hwnd = 11111
    computer_client._cached_window_title = "Window A"

    # Must reject if targeted window differs (Eliminates Codex's 'contrôle provenant d'une autre fenêtre')
    with pytest.raises(ValueError, match="Contrôle provenant d'une autre fenêtre"):
        computer_client.get_cached_element(1, target_hwnd=22222)

    # Must reject out-of-bounds index
    with pytest.raises(ValueError, match="introuvable"):
        computer_client.get_cached_element(999, target_hwnd=11111)

    # Must reject if cache is empty
    computer_client._element_cache = {}
    computer_client._cached_window_hwnd = 0
    with pytest.raises(ValueError, match="Aucun élément en cache"):
        computer_client.get_cached_element(1, target_hwnd=11111)


def test_system_window_protection():
    is_prot, reason = computer_client.is_protected_system_window(0)
    assert is_prot is False

    with patch.object(computer_client.user32, "IsWindow", return_value=1):

        def _fake_class(h, buf, sz):
            buf.value = "Shell_TrayWnd"
            return len("Shell_TrayWnd")

        with patch.object(computer_client.user32, "GetClassNameW", side_effect=_fake_class):
            with patch.object(computer_client, "get_process_image_path", return_value=("", "explorer.exe")):
                is_prot, reason = computer_client.is_protected_system_window(99999)
                assert is_prot is False  # Taskbar is allowed for symbiose

        with patch.object(computer_client, "get_process_image_path", return_value=("", "consent.exe")):
            is_prot, reason = computer_client.is_protected_system_window(88888)
            assert is_prot is True
            assert "consent.exe" in reason


def test_clipboard_set_verification_and_restore():
    orig = computer_client.get_clipboard_text()
    test_val = "NexusAGY SOTA Verification 🛡️"
    res = computer_client.set_clipboard_text(test_val)
    assert res is True
    read_back = computer_client.get_clipboard_text()
    assert read_back == test_val
    if orig is not None:
        computer_client.set_clipboard_text(orig)


def test_resolve_window():
    # 1. Target integer > 0 returns same integer
    assert computer_client.resolve_window(12345) == 12345

    # 2. Target 0 returns 0
    assert computer_client.resolve_window(0) == 0

    # 3. String digits return int
    assert computer_client.resolve_window("12345") == 12345

    # Bureau simulé : le résultat ne dépend jamais des fenêtres réellement ouvertes (deux Explorateurs, etc.).
    def win(hwnd: int, title: str, proc: str) -> dict:
        return {"hwnd": hwnd, "title": title, "process_name": proc, "bounds": {}, "is_foreground": False}

    desktop = [win(101, "Sans titre - Bloc-notes", "notepad.exe"), win(202, "Documents", "explorer.exe"),
               win(203, "Téléchargements", "explorer.exe")]  # fmt: skip
    with patch.object(computer_client, "list_windows", return_value=desktop):
        # 4. Unknown string raises ValueError
        with pytest.raises(ValueError, match="Aucune fenêtre ouverte"):
            computer_client.resolve_window("DEFINITELY_NON_EXISTENT_WINDOW_99999")

        # 5. Process name (with or without .exe) or partial title designating a single window
        assert computer_client.resolve_window("notepad") == 101
        assert computer_client.resolve_window("notepad.exe") == 101
        assert computer_client.resolve_window("bloc-notes") == 101
        assert computer_client.resolve_window("Téléchargements") == 203

        # 6. Two windows of the same process: refused with both candidates, never the first one by default
        with pytest.raises(ValueError, match="désigne 2 fenêtres") as ambiguous:
            computer_client.resolve_window("explorer")
        assert "202" in str(ambiguous.value) and "203" in str(ambiguous.value)


def test_look_function():
    windows = computer_client.list_windows(visible_only=True)
    if not windows:
        pytest.skip("No visible windows found on system")
    target = windows[0]["hwnd"]
    state = computer_client.look(hwnd=target, max_elements=10, capture_screenshot=False)
    assert state["hwnd"] == target
    assert "elements" in state
    assert isinstance(state["elements"], list)


def test_act_batch_execution():
    windows = computer_client.list_windows(visible_only=True)
    if not windows:
        pytest.skip("No visible windows found on system")
    target = windows[0]["hwnd"]

    # Execute a safe macro-action batch in background (no focus theft)
    steps = [
        {"action": "wait", "delay_ms": 10},
        {"action": "wait", "seconds": 0.01},
    ]
    res = computer_client.act(steps=steps, hwnd=target, then="state", foreground=False)
    assert res["success"] is True
    assert res["executed_steps"] == 2
    assert "state" in res
    assert res["state"]["hwnd"] == target


def test_mcp_server_look_and_act():
    windows = computer_client.list_windows(visible_only=True)
    if not windows:
        pytest.skip("No visible windows found on system")
    target = windows[0]["hwnd"]

    # Test computer_look MCP tool
    look_raw = mcp_server.computer_look(hwnd=target, max_elements=5, capture_screenshot=False, format="json")
    look_res = json.loads(look_raw)
    assert look_res["status"] == "success"
    assert "elements" in look_res["data"]

    # Test computer_act MCP tool
    act_raw = mcp_server.computer_act(
        steps=[{"action": "wait", "delay_ms": 10}],
        hwnd=target,
        then="none",
        foreground=False,
    )
    act_res = json.loads(act_raw)
    assert act_res["status"] == "success"
    assert act_res["data"]["executed_steps"] == 1
    assert "state" not in act_res["data"]


def test_open_path_and_coords(tmp_path):
    # 1. open_path : dossier existant ouvert, ouverture relue (nouvelle fenêtre portant son nom)
    folder = tmp_path / "Dossier essai"
    folder.mkdir()
    opened = [{"hwnd": 1, "title": "Autre"}]
    shown = {"hwnd": 77, "title": "Dossier essai", "process_name": "explorer.exe"}
    with (
        patch("os.startfile", side_effect=lambda p: opened.append(shown)) as mock_start,
        patch.object(computer_client, "list_windows", side_effect=lambda visible_only=True: list(opened)),
        patch.object(computer_client, "_restore_if_stolen", return_value=False),
    ):
        res = computer_client.open_path(str(folder))
        assert res["success"] is True and res["verified"] is True and res["hwnd"] == 77
        mock_start.assert_called_once_with(str(folder))

        opened[:] = [{"hwnd": 1, "title": "Autre"}]
        mcp_res = json.loads(mcp_server.computer_open_path(str(folder)))
        assert mcp_res["status"] == "success"
        assert mcp_res["data"]["path"] == str(folder)

    # 2. Test click with coords="screen" (no window offset applied)
    with (
        patch.object(computer_client, "mouse_click", return_value=True) as mock_click,
        # la fenêtre active réelle (celle de Julien) peut changer d'elle-même : relecture neutralisée
        patch.object(computer_client, "_wait_window_effect", return_value=(None, "")),
        # point sans élément connu : jamais une action d'arrière-plan sur une vraie fenêtre de Julien
        patch.object(computer_client, "_hit_test", return_value=None),
        patch.object(computer_client, "FocusGuard", _NoOpGuard),
    ):
        # sans foreground=True : refus explicite, rien n'est envoyé
        with pytest.raises(computer_client.NeedsForegroundError, match="rien n'a été envoyé"):
            computer_client.click(hwnd=4242, x=100, y=200, coords="screen", foreground=False)
        mock_click.assert_not_called()
        res = computer_client.click(hwnd=4242, x=100, y=200, coords="screen", foreground=True)
        # Clic sans effet visible relu : jamais « réussi » sur la seule base de l'envoi
        assert res["success"] is None
        assert res["verified"] is None
        assert res["method"] == "screen_coordinates"
        assert res["screen_coords"] == (100, 200)
        mock_click.assert_called_once_with(100, 200, button="left", click_count=1)

    # 3. Test mouse_move with coords="screen"
    with (
        patch.object(computer_client.user32, "SetCursorPos") as mock_set_cur,
        patch.object(computer_client, "_cursor_pos", return_value=(300, 400)),
        patch.object(computer_client, "FocusGuard", _NoOpGuard),
        patch.object(computer_client, "_require_front", lambda what="": None),
    ):
        res = computer_client.mouse_move(x=300, y=400, hwnd=4242, smooth=False, coords="screen", foreground=True)
        assert res["success"] is True
        assert res["screen_coords"] == (300, 400)
        mock_set_cur.assert_called_once_with(300, 400)


def test_restore_focus_defaults():
    import inspect

    sig_click = inspect.signature(computer_client.click)
    assert sig_click.parameters["restore_focus"].default is True

    sig_type = inspect.signature(computer_client.type_text)
    assert sig_type.parameters["restore_focus"].default is True

    sig_press = inspect.signature(computer_client.press_key)
    assert sig_press.parameters["restore_focus"].default is True


def test_user_idle_detection():
    idle_s = computer_client.get_idle_duration_s()
    assert isinstance(idle_s, float)
    assert idle_s >= 0.0
    res = computer_client.wait_for_user_idle(threshold_s=0.0, max_wait_s=0.1)
    assert res is True


def test_type_text_clipboard_safety_on_error():
    """Erreur pendant le collage : le presse-papiers sauvé (tous formats) est rendu quand même."""
    saved = computer_client.ClipboardSnapshot([(computer_client.CF_UNICODETEXT, "à Julien".encode("utf-16-le"))])
    with (
        patch.object(computer_client, "clipboard_snapshot", return_value=saved),
        patch.object(computer_client, "clipboard_restore") as restore,
        patch.object(computer_client, "set_clipboard_text", return_value=True),
        patch.object(computer_client, "press_key", side_effect=RuntimeError("Simulated paste error")),
        patch.object(computer_client, "mouse_click"),
        patch.object(computer_client, "FocusGuard", _NoOpGuard),
        patch.object(computer_client, "_focused_is_password", return_value=False),
        patch.object(computer_client, "_hit_test", return_value=None),
    ):
        with pytest.raises(RuntimeError, match="Simulated paste error"):
            computer_client.type_text(
                "failed_text", hwnd=4242, x=10, y=10, method="paste", restore_clipboard=True, foreground=True
            )
    restore.assert_called_once_with(saved)


def test_click_uia_invoke_error_fallback():
    mock_ctrl = MagicMock()
    mock_invoke = MagicMock()
    mock_invoke.Invoke.side_effect = RuntimeError("COM Invoke Failed")
    mock_ctrl.GetInvokePattern.return_value = mock_invoke
    mock_ctrl.GetTogglePattern.return_value = None
    mock_ctrl.GetSelectionItemPattern.return_value = None
    mock_ctrl.GetExpandCollapsePattern.return_value = None

    mock_rect = MagicMock()
    mock_rect.left = 100
    mock_rect.right = 200
    mock_rect.top = 100
    mock_rect.bottom = 200
    mock_ctrl.BoundingRectangle = mock_rect

    with patch.object(computer_client, "get_cached_element", return_value=mock_ctrl):
        with patch.object(computer_client, "mouse_click") as mock_mouse_click:
            with patch.object(computer_client, "FocusGuard", _NoOpGuard):
                res = computer_client.click(hwnd=1234, element_index=0, restore_focus=False, foreground=True)
                assert res["success"] is None  # clic physique de repli sans effet relisible
                assert res["method"] == "element_center"
                assert "COM Invoke Failed" in res["invoke_error"]
                mock_mouse_click.assert_called_once()


def test_shared_foreground_lock():
    import sys
    from pathlib import Path

    shared_dir = Path(computer_client.__file__).resolve().parent.parent.parent / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    import foreground_lock

    lock1 = foreground_lock.ForegroundLock(owner="TestAGY", timeout=1.0)
    assert lock1.acquire() is True
    assert lock1.acquired is True

    lock2 = foreground_lock.ForegroundLock(owner="TestClaude", timeout=0.1)
    assert lock2.acquire() is False

    lock1.release()
    assert lock1.acquired is False

    assert lock2.acquire() is True
    lock2.release()


def test_focus_guard_aborts_when_lock_held():
    import sys
    from pathlib import Path

    shared_dir = Path(computer_client.__file__).resolve().parent.parent.parent / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    import foreground_lock

    with patch.object(foreground_lock.ForegroundLock, "acquire", return_value=False):
        with patch.object(computer_client, "focus_window") as mock_focus:
            with pytest.raises(TimeoutError) as exc_info:
                with computer_client.FocusGuard(target_hwnd=99999, use_lock=True):
                    pass
            assert "action reportée" in str(exc_info.value)
            mock_focus.assert_not_called()


def test_focus_guard_aborts_when_user_typing():
    with patch.object(computer_client, "wait_for_user_idle", return_value=False):
        with patch.object(computer_client, "focus_window") as mock_focus:
            with pytest.raises(TimeoutError) as exc_info:
                with computer_client.FocusGuard(target_hwnd=99999, wait_idle=True, use_lock=False):
                    pass
            assert "Julien est en train de taper" in str(exc_info.value)
            mock_focus.assert_not_called()


def test_focus_guard_refuses_when_lock_unavailable():
    """Jeton inaccessible : refus clair, jamais d'action physique sans lui (protocole foreground-token.md)."""
    shared_dir = Path(computer_client.__file__).resolve().parent.parent.parent / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    import foreground_lock

    with patch.object(foreground_lock.ForegroundLock, "acquire", side_effect=OSError(5, "accès refusé")):
        with patch.object(computer_client, "focus_window") as mock_focus:
            with pytest.raises(RuntimeError, match="action physique refusée"):
                with computer_client.FocusGuard(target_hwnd=99999, use_lock=True):
                    pass
            mock_focus.assert_not_called()


def test_focus_guard_writes_purpose_in_token(tmp_path):
    """Le détenteur dit pourquoi il tient le jeton : les autres agents peuvent nommer l'action qu'ils attendent."""
    shared_dir = Path(computer_client.__file__).resolve().parent.parent.parent / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    import foreground_lock

    with (
        patch.object(foreground_lock, "LOCK_FILE", tmp_path / "foreground.lock"),
        patch.object(computer_client, "restore_foreground"),
        patch.object(computer_client.user32, "SetCursorPos"),
    ):
        with computer_client.FocusGuard(target_hwnd=None, wait_idle=False, purpose="lot au premier plan (essai)"):
            who = foreground_lock.holder()
        assert who is not None
        assert who["owner"] == "NexusAGY"
        assert who["purpose"] == "lot au premier plan (essai)"
        assert foreground_lock.holder() is None


def _shared_lock_module():
    shared_dir = Path(computer_client.__file__).resolve().parent.parent.parent / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    import foreground_lock

    return foreground_lock


def test_shared_lock_reentrant_per_thread_not_per_agent(tmp_path):
    """Un appel abandonné encore en cours (fil A) et un nouvel appel (fil B) du même agent : B attend, il ne passe
    jamais en « imbriqué » ; la prise de A n'est rendue qu'une fois, et le compteur ne devient jamais négatif."""
    import threading

    foreground_lock = _shared_lock_module()
    with patch.object(foreground_lock, "LOCK_FILE", tmp_path / "foreground.lock"):
        a = foreground_lock.ForegroundLock(owner="NexusAGY", timeout=1.0)
        assert a.acquire()
        result: list[bool] = []
        b_thread = threading.Thread(
            target=lambda: result.append(foreground_lock.ForegroundLock(owner="NexusAGY", timeout=0.2).acquire())
        )
        b_thread.start()
        b_thread.join(timeout=5)
        assert result == [False]  # même agent, autre fil : attend le verrou comme un autre agent
        inner = foreground_lock.ForegroundLock(owner="NexusAGY", timeout=0.1)
        assert inner.acquire() and inner._nested  # même fil : imbriqué, sans second verrou
        inner.release()
        a.release()
        assert foreground_lock.holder() is None
        assert all(depth > 0 for depth in foreground_lock._NESTED.values())


def test_shared_lock_wait_is_interrupted_by_abort(tmp_path):
    """Arrêt d'urgence pendant l'attente du jeton : l'attente s'arrête aussitôt (pas 8 s)."""
    import threading
    import time

    emergency_stop = computer_client.emergency_stop

    foreground_lock = _shared_lock_module()
    with patch.object(foreground_lock, "LOCK_FILE", tmp_path / "foreground.lock"):
        holder_lock = foreground_lock.ForegroundLock(owner="NexusClaude", timeout=1.0)
        errors: list[BaseException] = []

        def other_agent() -> None:  # un autre fil = un autre détenteur
            assert holder_lock.acquire()

        t = threading.Thread(target=other_agent)
        t.start()
        t.join(timeout=5)

        def abort() -> None:
            raise emergency_stop.EmergencyStopError("arrêt")

        started = time.monotonic()
        try:
            foreground_lock.ForegroundLock(owner="NexusAGY", timeout=8.0, abort=abort).acquire()
        except emergency_stop.EmergencyStopError as error:
            errors.append(error)
        assert errors and time.monotonic() - started < 1.0
        holder_lock.release()


def test_restore_if_stolen_never_overrides_another_agent_holding_the_token():
    """foreground-token.md : un autre agent a mis sa fenêtre devant avec le jeton → NexusAGY ne la lui reprend pas."""
    foreground_lock = _shared_lock_module()
    with (
        patch.object(foreground_lock, "holder", return_value={"owner": "NexusClaude", "purpose": "frappe"}),
        patch.object(computer_client.user32, "GetForegroundWindow", return_value=222),
        patch.object(computer_client.user32, "IsWindow", return_value=1),
        patch.object(computer_client, "restore_foreground") as restore,
    ):
        assert computer_client._restore_if_stolen(111) is False
        restore.assert_not_called()
    with (
        patch.object(foreground_lock, "holder", return_value=None),
        patch.object(computer_client.user32, "GetForegroundWindow", return_value=222),
        patch.object(computer_client.user32, "IsWindow", return_value=1),
        patch.object(computer_client, "restore_foreground") as restore,
    ):
        assert computer_client._restore_if_stolen(111) is True
        restore.assert_called_once_with(111)


def test_act_foreground_holds_token_for_whole_batch_and_hands_back():
    """foreground=True = vraie souris/clavier en REPLI : la garde du lot (jeton tenu sans trou, fenêtre devant sous le
    jeton, premier plan rendu à la fin) n'est prise qu'au premier geste physique nécessaire, une seule fois, et rendue
    même après une étape en échec. Les étapes d'arrière-plan qui précèdent ne touchent pas au premier plan."""
    events = []

    class LotGuard:
        def __init__(self, target_hwnd=None, restore=True, wait_idle=True, use_lock=True, purpose="action physique"):
            self.args = (target_hwnd, restore, purpose)

        def __enter__(self):
            events.append(("enter", *self.args))
            return self

        def __exit__(self, *exc):
            events.append(("exit",))
            return False

    def step(action, s, target_hwnd, foreground, i):
        if s.get("physical"):
            computer_client._physical_gate(target_hwnd, foreground, "geste de test")
        events.append(("step", i))
        if s.get("boom"):
            raise RuntimeError("échec simulé")
        return {"success": True, "verified": True}

    with (
        patch.object(computer_client, "FocusGuard", LotGuard),
        patch.object(computer_client, "resolve_window", return_value=4242),
        patch.object(computer_client, "ensure_default_desktop"),
        patch.object(computer_client, "focus_window") as mock_focus,
        patch.object(computer_client, "_run_act_step", side_effect=step),
    ):
        lot = [{"action": "click"}, {"action": "key", "physical": True}, {"action": "click", "physical": True}]
        res = computer_client.act(lot, hwnd=4242, then="none", foreground=True)
        assert res["success"] is True
        assert res["physical_steps"] == 2
        assert events == [
            ("step", 0),  # arrière-plan d'abord : aucune garde
            ("enter", 4242, True, "lot au premier plan (act)"),  # premier geste physique
            ("step", 1),
            ("step", 2),  # même garde, jeton tenu sans trou
            ("exit",),
        ]
        mock_focus.assert_not_called()  # la mise au premier plan passe par la garde, donc sous le jeton

        events.clear()
        res = computer_client.act(
            [{"action": "click", "physical": True, "boom": True}], hwnd=4242, then="none", foreground=True
        )
        assert res["success"] is False
        assert events == [("enter", 4242, True, "lot au premier plan (act)"), ("step", 0), ("exit",)]

        events.clear()
        res = computer_client.act([{"action": "click"}], hwnd=4242, then="none", foreground=True)
        assert events == [("step", 0)]  # tout en arrière-plan : aucune garde de lot, aucun jeton

        events.clear()
        res = computer_client.act([{"action": "click", "physical": True}], hwnd=4242, then="none", foreground=False)
        assert events == []  # sans foreground=True : refus explicite, rien envoyé
        assert res["steps"][0]["error_type"] == "NeedsForegroundError"
        assert res["next"].startswith("étape 0 : ✗ échec")
