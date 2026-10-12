import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIR = REPO_ROOT / "client"
sys.path.insert(0, str(CLIENT_DIR))

import computer_client  # noqa: E402
import mcp_server  # noqa: E402


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
        assert "gemini_box_2d" in el
        assert len(el["gemini_box_2d"]) == 4


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
        computer_client.press_key("")

    with pytest.raises(ValueError, match="Touche inconnue"):
        computer_client.press_key("ctrl+invalidkey123")


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
    browser_tools = [t.name for t in mcp_server.browser_mcp._tool_manager.list_tools()]
    computer_tools = [t.name for t in mcp_server.computer_mcp._tool_manager.list_tools()]
    combined_tools = [t.name for t in mcp_server.combined_mcp._tool_manager.list_tools()]

    assert len(browser_tools) == 32
    assert len(computer_tools) == 14
    assert len(combined_tools) == 46
    assert all(name.startswith("browser_") for name in browser_tools)
    assert all(name.startswith("computer_") for name in computer_tools)
    assert set(browser_tools).union(set(computer_tools)) == set(combined_tools)


def test_press_key_punctuation():
    # Should resolve punctuation keys properly via VkKeyScanW without hardware side-effects
    with patch.object(computer_client, "_send_inputs", return_value=2):
        res = computer_client.press_key("ctrl+,")
        assert res["success"] is True
        assert len(res["vk_codes"]) >= 2

        res_dot = computer_client.press_key("ctrl+.")
        assert res_dot["success"] is True
        assert len(res_dot["vk_codes"]) >= 2


def test_dwm_bounds_accurate():
    windows = computer_client.list_windows(visible_only=True)
    if windows:
        rect = computer_client.get_window_rect(windows[0]["hwnd"])
        assert rect["width"] > 0
        assert rect["height"] > 0


def test_mouse_move_smooth():
    # Verify smooth calculation without displacing the user's physical mouse cursor
    with patch.object(computer_client.user32, "SetCursorPos", return_value=1):
        res = computer_client.mouse_move(x=10, y=10, smooth=True, steps=3, duration_ms=10)
        assert res["success"] is True
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
            is_prot, reason = computer_client.is_protected_system_window(99999)
            assert is_prot is True
            assert "Shell_TrayWnd" in reason


def test_clipboard_set_verification_and_restore():
    orig = computer_client.get_clipboard_text()
    test_val = "NexusAGY SOTA Verification 🛡️"
    res = computer_client.set_clipboard_text(test_val)
    assert res is True
    read_back = computer_client.get_clipboard_text()
    assert read_back == test_val
    if orig is not None:
        computer_client.set_clipboard_text(orig)
