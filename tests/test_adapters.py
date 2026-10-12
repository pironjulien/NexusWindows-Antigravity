"""Tests for specialized Antigravity MCP adapter."""

import asyncio

from adapters.antigravity import server as antigravity_server


def test_antigravity_adapter_tools():
    tools = asyncio.run(antigravity_server.mcp.list_tools())
    tool_names = {t.name for t in tools}
    expected = {
        "computer_list_windows",
        "computer_list_apps",
        "computer_focus_window",
        "computer_get_window_state",
        "computer_click",
        "computer_mouse_move",
        "computer_type_text",
        "computer_press_key",
        "computer_scroll",
        "computer_drag",
        "computer_take_screenshot",
        "computer_spotlight_status",
        "computer_spotlight_toggle",
    }
    assert expected.issubset(tool_names), f"Antigravity adapter missing tools: {expected - tool_names}"
    assert antigravity_server.mcp.name == "nexus-computer"
