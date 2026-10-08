import json
import sys
from pathlib import Path

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
        assert "screenshot_data_url" in shot_res["data"]
        assert shot_res["data"]["size_bytes"] < 200 * 1024
