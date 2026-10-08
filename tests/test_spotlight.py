"""Tests for the Antigravity Desktop Spotlight Launcher & System Tray Companion."""

from pathlib import Path

from client.spotlight_launcher import check_syntax, is_spotlight_running


def test_spotlight_script_exists():
    script_path = Path(__file__).resolve().parent.parent / "client" / "spotlight_launcher.ps1"
    assert script_path.exists(), "spotlight_launcher.ps1 must exist in the client directory"


def test_spotlight_check_syntax():
    assert check_syntax() is True, "spotlight_launcher.ps1 syntax and .NET assembly check must pass"


def test_is_spotlight_running_returns_bool():
    status = is_spotlight_running()
    assert isinstance(status, bool)


def test_mcp_spotlight_status():
    import json

    from client.mcp_server import computer_spotlight_status

    res_raw = computer_spotlight_status()
    res = json.loads(res_raw)
    assert "status" in res
    assert "running" in res
    assert "shortcut" in res
