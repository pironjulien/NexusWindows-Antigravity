"""Tests for specialized MCP client adapters (Claude, Codex, Antigravity)."""

import asyncio

from adapters.antigravity import server as antigravity_server
from adapters.claude import server as claude_server
from adapters.codex import server as codex_server


def test_claude_adapter_tools():
    tools = asyncio.run(claude_server.mcp.list_tools())
    tool_names = {t.name for t in tools}
    expected = {
        "computer_list_windows",
        "computer_focus_window",
        "computer_screenshot",
        "computer_zoom",
        "computer_get_window_state",
        "computer_click",
        "computer_move_mouse",
        "computer_type_text",
        "computer_press_key",
        "computer_scroll",
        "computer_drag",
    }
    assert expected.issubset(tool_names), f"Claude adapter missing tools: {expected - tool_names}"
    assert claude_server.mcp.name == "nexus-computer"


def test_codex_adapter_tools():
    tools = asyncio.run(codex_server.mcp.list_tools())
    tool_names = {t.name for t in tools}
    expected = {
        "computer_list_windows",
        "computer_focus_window",
        "computer_screenshot",
        "computer_zoom",
        "computer_get_window_state",
        "computer_click",
        "computer_move_mouse",
        "computer_type_text",
        "computer_press_key",
        "computer_scroll",
        "computer_drag",
    }
    assert expected.issubset(tool_names), f"Codex adapter missing tools: {expected - tool_names}"
    assert codex_server.mcp.name == "nexus-computer"


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
    assert tool_names == expected, f"Antigravity adapter mismatch: {tool_names ^ expected}"
    assert antigravity_server.mcp.name == "nexus-computer"
