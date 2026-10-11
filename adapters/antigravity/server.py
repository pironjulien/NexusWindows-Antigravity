"""nexus-computer adapter for Google Antigravity & Gemini Multimodal.

Exposes native tools with Anti-Crash 400 WebP enforcement (< 200 KB),
Gemini box_2d [ymin, xmin, ymax, xmax] spatial grounding (0-1000),
Set-of-Marks [#1..#N], and Spotlight companion supervision (Alt + Space).
Directly powered by unified core.engine and core.spotlight.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server

import core.engine as engine
import core.spotlight as spotlight

ANTIGRAVITY_INSTRUCTIONS = """SOTA Windows OS Computer Use & Spotlight Companion bridge for Antigravity.
- UI Automation in background by default.
- Anti-Crash 400 WebP (< 200 KB) for vision analysis.
- Gemini box_2d [ymin, xmin, ymax, xmax] coordinates (0-1000) for visual grounding.
- Spotlight companion supervision (Alt + Space)."""

mcp = FastMCP("nexus-computer", instructions=ANTIGRAVITY_INSTRUCTIONS, log_level="WARNING")
tool = mcp.tool(structured_output=False)


def _format_result(func: Any, *args: Any, **kwargs: Any) -> str:
    try:
        data = func(*args, **kwargs) if callable(func) else func
        return json.dumps({"status": "success", "data": data}, ensure_ascii=False, indent=2)
    except Exception as error:
        return json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False)


@tool
def computer_list_windows(visible_only: bool = True) -> str:
    """Liste toutes les fenêtres ouvertes du bureau Windows avec HWND, titre, PID, nom du processus, coordonnées et état premier plan."""
    return _format_result(engine.list_windows, visible_only=visible_only)


@tool
def computer_list_apps() -> str:
    """Liste les applications graphiques en cours d'exécution groupées par processus."""
    return _format_result(engine.list_apps)


@tool
def computer_focus_window(
    hwnd: int | None = None,
    title: str | None = None,
    process_name: str | None = None,
) -> str:
    """Met la fenêtre cible au premier plan, la restaure si réduite et lui donne le focus."""
    return _format_result(engine.focus_window, hwnd=hwnd, title=title, process_name_filter=process_name)


@tool
def computer_get_window_state(
    hwnd: int | None = None,
    max_elements: int = 50,
    capture_screenshot: bool = False,
    output_path: str | None = None,
    max_depth: int = 30,
    annotate_screenshot: bool = False,
) -> str:
    """Extrait l'état complet de la fenêtre ciblée avec arbre UI Automation compact [#1..#N],
    coordonnées Gemini box_2d [ymin, xmin, ymax, xmax] (0-1000), et capture WebP < 200 Ko."""
    return _format_result(
        engine.get_window_state,
        hwnd=hwnd,
        max_elements=max_elements,
        capture_screenshot=capture_screenshot,
        output_path=output_path,
        max_depth=max_depth,
        annotate_screenshot=annotate_screenshot,
    )


@tool
def computer_click(
    hwnd: int | None = None,
    element_index: int | None = None,
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    click_count: int = 1,
    foreground: bool = False,
    method: str = "auto",
) -> str:
    """Clique sur un élément [#N] (en arrière-plan via UI Automation ou PostMessage) ou sur (x, y)."""
    return _format_result(
        engine.click,
        hwnd=hwnd,
        element_index=element_index,
        x=x,
        y=y,
        button=button,
        click_count=click_count,
        foreground=foreground,
        method=method,
    )


@tool
def computer_mouse_move(
    x: int,
    y: int,
    hwnd: int | None = None,
    smooth: bool = True,
    steps: int = 10,
    duration_ms: int = 200,
    foreground: bool = False,
) -> str:
    """Déplace le curseur vers des coordonnées (x, y). Exige foreground=True pour confirmer le pilotage physique."""
    return _format_result(
        engine.mouse_move,
        x=x,
        y=y,
        hwnd=hwnd,
        smooth=smooth,
        steps=steps,
        duration_ms=duration_ms,
        foreground=foreground,
    )


@tool
def computer_type_text(
    text: str,
    hwnd: int | None = None,
    element_index: int | None = None,
    clear_first: bool = False,
    foreground: bool = False,
    method: str = "auto",
) -> str:
    """Saisit du texte dans un élément [#N] en arrière-plan via UI Automation ValuePattern ou PostMessage WM_CHAR."""
    return _format_result(
        engine.type_text,
        text=text,
        hwnd=hwnd,
        element_index=element_index,
        clear_first=clear_first,
        foreground=foreground,
        method=method,
    )


@tool
def computer_launch_app(
    command: str,
    background: bool = True,
    wait_ms: int = 800,
) -> str:
    """Lance une application. Si background=True (défaut), la démarre sans voler le premier plan (SW_SHOWMINNOACTIVE)."""
    return _format_result(engine.launch_app, command=command, background=background, wait_ms=wait_ms)


@tool
def computer_press_key(keys: str, hwnd: int | None = None, foreground: bool = False) -> str:
    """Presse une combinaison de touches système (raccourcis clavier). Exige foreground=True."""
    return _format_result(engine.press_key, keys=keys, hwnd=hwnd, foreground=foreground)


@tool
def computer_scroll(
    delta_y: int = 0,
    delta_x: int = 0,
    hwnd: int | None = None,
    x: int | None = None,
    y: int | None = None,
    element_index: int | None = None,
    foreground: bool = False,
) -> str:
    """Fait défiler un conteneur en arrière-plan via UI Automation ou via molette."""
    return _format_result(
        engine.scroll,
        delta_y=delta_y,
        delta_x=delta_x,
        hwnd=hwnd,
        x=x,
        y=y,
        element_index=element_index,
        foreground=foreground,
    )


@tool
def computer_drag(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    hwnd: int | None = None,
    steps: int = 12,
    delay_ms: int = 15,
    foreground: bool = False,
) -> str:
    """Effectue un glisser-déposer fluide à la souris entre deux coordonnées. Exige foreground=True."""
    return _format_result(
        engine.drag,
        start=from_x,
        end=from_y,
        to_x=to_x,
        to_y=to_y,
        hwnd=hwnd,
        steps=steps,
        delay_ms=delay_ms,
        foreground=foreground,
    )


@tool
def computer_take_screenshot(
    hwnd: int | None = None,
    full_screen: bool = False,
    output_path: str | None = None,
    annotate_screenshot: bool = False,
) -> str:
    """Prend une capture d'écran compressée en WebP sous 200 Ko (Règle Anti-Crash 400)."""

    def _action() -> dict[str, Any]:
        elements_to_draw = None
        if annotate_screenshot:
            target_hwnd = hwnd or engine.foreground()
            state = engine.get_window_state(hwnd=target_hwnd, capture_screenshot=False)
            elements_to_draw = state.get("elements")

        data_bytes, meta = engine.capture_window_image(
            hwnd=hwnd,
            full_screen=full_screen,
            return_meta=True,
            elements_to_annotate=elements_to_draw,
        )
        dest_path = output_path
        if dest_path:
            dest_p = Path(dest_path).expanduser().resolve()
            dest_path = str(dest_p)
        else:
            cache_dir = Path.home() / ".nexusagy" / "screenshots"
            cache_dir.mkdir(parents=True, exist_ok=True)
            engine.cleanup_screenshot_cache(max_files=50, max_age_hours=24.0)
            timestamp = int(time.time() * 1000)
            dest_path = str(cache_dir / f"screenshot_{timestamp}.webp")

        with open(dest_path, "wb") as f:
            f.write(data_bytes)

        return {
            "path": dest_path,
            "format": "webp",
            "size_bytes": len(data_bytes),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "capture_mode": meta.get("capture_mode", "offscreen_gdi"),
            "original_bounds": meta.get("original_bounds"),
            "scale_factor": meta.get("scale_factor"),
            "annotated": annotate_screenshot,
        }

    return _format_result(_action)


@tool
def computer_spotlight_status() -> str:
    """Vérifie si le compagnon Antigravity Spotlight (Alt + Espace) est actif."""
    running = spotlight.is_spotlight_running()
    return json.dumps(
        {
            "status": "online" if running else "stopped",
            "running": running,
            "shortcut": "Alt + Space (ou Alt + Shift + Space)",
            "script": str(spotlight.SPOTLIGHT_SCRIPT_PATH),
        },
        indent=2,
        ensure_ascii=False,
    )


@tool
def computer_spotlight_toggle(action: str = "start") -> str:
    """Démarre ou arrête le compagnon Antigravity Spotlight (Alt + Espace)."""
    if action == "stop":
        success = spotlight.stop_spotlight()
        return json.dumps({"action": "stop", "success": success}, indent=2)
    success = spotlight.start_spotlight_background()
    return json.dumps(
        {
            "action": "start",
            "success": success,
            "shortcut": "Alt + Space",
        },
        indent=2,
    )


def main() -> None:
    os.chdir(Path(__file__).resolve().parent.parent.parent)
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "wb")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr

    async def serve() -> None:
        output = anyio.wrap_file(io.TextIOWrapper(protocol, encoding="utf-8"))
        async with stdio_server(stdout=output) as (read_stream, write_stream):
            await mcp._mcp_server.run(read_stream, write_stream, mcp._mcp_server.create_initialization_options())

    anyio.run(serve)


if __name__ == "__main__":
    main()
