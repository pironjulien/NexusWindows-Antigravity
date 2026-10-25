"""Le serveur MCP démarre et liste ses outils (initialize puis tools/list), sur Windows comme sous Linux, où les
annuaires MCP (Glama) le lancent dans un conteneur ; la CI le lance aussi sous Linux. Profil temporaire (HOME,
USERPROFILE). Sous Windows, le serveur est servi sans le bloc __main__ : ni raccourci d'arrêt d'urgence ni Raw Input
pris pendant le test ; ailleurs, le vrai point d'entrée (qui ne les démarre pas hors Windows)."""

import importlib.util
import os
import re
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT = REPO_ROOT / "client"
LISTED = {"windows", "look", "act", "launch", "window"}  # noms communs des trois NexusWindows
# Mots français fréquents (et lettres accentuées) : absents des descriptions, en anglais comme Claude et Codex (3.0.1).
FRENCH = re.compile(
    r"[éèêàùçôî]|\b(fenêtre|élément|clic|exemple|regarde|ouvre|agit|lot|cible|libellé|jamais|avec|sans|pour|les)\b",
    re.IGNORECASE,
)


def _server_params(tmp_path: Path) -> StdioServerParameters:
    env = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    if sys.platform == "win32":
        serve = f"import sys; sys.path.insert(0, {str(CLIENT)!r}); import mcp_server; mcp_server.mcp.run('stdio')"
        args = ["-c", serve]
    elif importlib.util.find_spec("nexus_windows_antigravity") is not None:
        # Roue installée (contrôle de publish.yml) : la commande du paquet, comme `uvx nexus-windows-antigravity`
        args = ["-m", "nexus_windows_antigravity.launch"]
    else:
        args = [str(CLIENT / "mcp_server.py")]
    return StdioServerParameters(command=sys.executable, args=args, env=env)


def test_initialize_and_list_tools(tmp_path):
    params = _server_params(tmp_path)

    async def session_check():
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.server_info.name == "nexus-windows-antigravity"
            assert init.server_info.version and init.server_info.version != "inconnue"
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


def test_initialize_announces_the_family_name_and_english_descriptions(tmp_path):
    """Famille NexusWindows (3.0.1) : nom annoncé = nom du paquet, titre, version du projet, et descriptions d'outils
    et instructions en anglais, comme les éditions Claude et Codex."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'(?m)^version = "([^"]+)"', pyproject).group(1)  # type: ignore[union-attr]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version  # version sémantique du projet, annoncée telle quelle
    params = _server_params(tmp_path)

    async def session_check():
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.server_info.name == "nexus-windows-antigravity"
            assert init.server_info.title == "NexusWindows for Antigravity"
            assert init.server_info.version == version
            assert init.instructions and not FRENCH.search(init.instructions), FRENCH.search(init.instructions or "")
            tools = (await session.list_tools()).tools
            assert {tool.name for tool in tools} == LISTED
            for tool in tools:
                found = FRENCH.search(tool.description or "")
                assert tool.description and not found, (tool.name, found)
                for name, schema in tool.input_schema.get("properties", {}).items():
                    found = FRENCH.search(str(schema.get("description", "")))
                    assert not found, (tool.name, name, found)

    async def check():
        with anyio.fail_after(60):
            await session_check()

    anyio.run(check)
