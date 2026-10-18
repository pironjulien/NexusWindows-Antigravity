"""Le serveur MCP démarre et liste ses outils (initialize puis tools/list), sur Windows comme sous Linux, où les
annuaires MCP (Glama) le lancent dans un conteneur ; la CI le lance aussi sous Linux. Profil temporaire (HOME,
USERPROFILE). Sous Windows, le serveur est servi sans le bloc __main__ : ni raccourci d'arrêt d'urgence ni Raw Input
pris pendant le test ; ailleurs, le vrai point d'entrée (qui ne les démarre pas hors Windows)."""

import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CLIENT = Path(__file__).resolve().parent.parent / "client"
LISTED = {"computer_list_windows", "computer_look", "computer_act", "computer_open_path", "computer_close_window"}


def test_initialize_and_list_tools(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    if sys.platform == "win32":
        serve = f"import sys; sys.path.insert(0, {str(CLIENT)!r}); import mcp_server; mcp_server.mcp.run('stdio')"
        args = ["-c", serve]
    else:
        args = [str(CLIENT / "mcp_server.py")]
    params = StdioServerParameters(command=sys.executable, args=args, env=env)

    async def session_check():
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.server_info.name == "nexus-computer"
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert set(tools) == LISTED
            for tool in tools.values():
                hints = tool.annotations
                assert hints is not None and hints.title, tool.name
                assert hints.read_only_hint is not None and hints.destructive_hint is not None, tool.name

    async def check():
        with anyio.fail_after(60):
            await session_check()

    anyio.run(check)
