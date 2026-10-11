"""nexus-computer adapter for Anthropic Claude (Claude Code and Claude Desktop).

Coordinates are pixels of the last image returned for the target; engine maps them to the screen.
Background execution via UI Automation is prioritized to keep the user uninterrupted.
"""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.stdio import stdio_server

import core.engine as engine
from core.engine import SCREEN, ComputerError

INSTRUCTIONS = """Windows : UI Automation en arrière-plan. Dans Claude Code, web : navigateur intégré.
Lire computer_get_window_state avant d'utiliser [N], puis vérifier l'effet.
Souris/clavier réels : foreground=True seulement si l'action est autorisée par l'utilisateur."""

mcp = FastMCP("nexus-computer", instructions=INSTRUCTIONS, log_level="WARNING")
tool = mcp.tool(structured_output=False)

Content = str | list[Any]
MAX_TEXT = 5000


def _capture(hwnd: int, header: str | None = None, marks: list | None = None) -> list[Any]:
    frame, png, notes = engine.screenshot(hwnd, marks)
    lines = [header] if header else []
    lines += [f"{engine.describe(hwnd)} — {frame.summary()}", *notes]
    return ["\n".join(lines), Image(data=png, format="png")]


def _done(hwnd: int, message: str, screenshot_after: bool, settle_ms: int) -> Content:
    if not screenshot_after:
        return message
    time.sleep(min(max(0, settle_ms), 10_000) / 1000)
    try:
        return _capture(hwnd, message)
    except Exception as error:  # noqa: BLE001
        return f"{message}\n(capture impossible : {error})"


def _bounded(name: str, value: int, low: int, high: int) -> int:
    if not low <= value <= high:
        raise ComputerError(f"{name} doit être compris entre {low} et {high} (reçu : {value}).")
    return value


def _require_foreground(foreground: bool, what: str) -> None:
    if not foreground:
        raise ComputerError(
            f"{what} demande la vraie souris ou le clavier et met la fenêtre devant, ce qui interrompt l'utilisateur. "
            "Demandez son accord, puis relancez avec foreground=True. Rien n'a été envoyé."
        )


def _background(
    target: int, message: str, guard: engine.ForegroundGuard, screenshot_after: bool, settle_ms: int
) -> Content:
    note = guard.summary()
    return _done(target, f"{message} ({note})" if note else message, screenshot_after, settle_ms)


@tool
def computer_list_windows() -> str:
    """Liste les fenêtres d'application visibles, de la plus en avant à la plus en arrière.

    Chaque ligne : hwnd, processus, état, taille et position physiques, titre. Le hwnd sert de cible aux
    autres outils (hwnd=0 désigne l'écran entier).
    """
    lines = []
    for window in engine.list_windows():
        bounds = window["bounds"]
        geometry = f"{bounds[2]}×{bounds[3]} @ ({bounds[0]},{bounds[1]})" if bounds else "—"
        marker = " [premier plan]" if window["foreground"] else ""
        lines.append(
            f"hwnd {window['hwnd']} | {window['process']} | {window['state']} | {geometry} | "
            f"« {window['title'][:100]} »{marker}"
        )
    return "\n".join(lines) or "Aucune fenêtre visible."


@tool
def computer_focus_window(
    hwnd: int | None = None,
    title: str | None = None,
    process_name: str | None = None,
    screenshot_after: bool = False,
) -> Content:
    """Met une fenêtre au premier plan (par hwnd, ou par extrait de titre / nom de processus) et la restaure si réduite."""
    target = hwnd if hwnd is not None else engine.find_window(title, process_name)
    target = engine.resolve_target(target)
    if target == SCREEN:
        return "Cible : écran entier."
    if not engine.bring_to_front(target):
        active = engine.foreground()
        raise ComputerError(
            f"Windows a refusé le premier plan à {engine.describe(target)} "
            f"(actuellement : {engine.describe(active) if active else 'aucune'})."
        )
    return _done(target, f"Au premier plan : {engine.describe(target)}.", screenshot_after, 300)


@tool
def computer_screenshot(hwnd: int | None = None, delay_ms: int = 0, annotate: bool = False) -> Content:
    """Capture une fenêtre sans la mettre devant, même cachée derrière d'autres (ou l'écran entier, hwnd=0)."""
    target = engine.resolve_target(hwnd)
    if delay_ms > 0:
        time.sleep(min(delay_ms, 30_000) / 1000)
    marks = None
    if annotate and target != SCREEN:
        engine.window_elements(target, max_elements=60)
        marks = engine.SESSION.marks
    return _capture(target, marks=marks)


@tool
def computer_zoom(x1: int, y1: int, x2: int, y2: int, hwnd: int | None = None) -> Content:
    """Agrandit une région (x1, y1)–(x2, y2) de la dernière capture pour lire un texte fin."""
    target = engine.resolve_target(hwnd)
    png, summary = engine.zoom(target, x1, y1, x2, y2)
    return [f"{engine.describe(target)} — {summary}", Image(data=png, format="png")]


@tool
def computer_get_window_state(hwnd: int | None = None, max_elements: int = 60, screenshot: bool = False) -> Content:
    """Liste les éléments interactifs de la fenêtre via UI Automation : [N] type "nom" (centre x,y) largeur×hauteur."""
    target = engine.resolve_target(hwnd)
    frame, lines, truncated = engine.window_elements(target, _bounded("max_elements", max_elements, 1, 300))
    if len(lines) < 2:
        time.sleep(0.4)
        frame, lines, truncated = engine.window_elements(target, max_elements)
    header = f"{engine.describe(target)} — {frame.summary()}"
    if truncated:
        lines.append(f"… liste tronquée (max_elements={max_elements} ou 4 s de parcours atteints)")
    text = "\n".join([header, *(lines or ["Aucun élément interactif exposé : utilisez computer_screenshot."])])
    return _capture(target, text, engine.SESSION.marks) if screenshot else text


@tool
def computer_click(
    x: int | None = None,
    y: int | None = None,
    element_index: int | None = None,
    hwnd: int | None = None,
    button: str = "left",
    click_count: int = 1,
    method: str = "auto",
    foreground: bool = False,
    screenshot_after: bool = False,
    settle_ms: int = 500,
) -> Content:
    """Clique sur un élément [N] de computer_get_window_state, ou sur le point (x, y) de la dernière capture."""
    target = engine.resolve_target(hwnd)
    res = engine.click(
        hwnd=target,
        element_index=element_index,
        x=x,
        y=y,
        button=button,
        click_count=click_count,
        foreground=foreground,
        method=method,
    )
    if element_index is not None:
        try:
            control = engine.element(target, element_index)
            label = f"[{element_index}] {engine._quoted(control.Name, 60)}"
        except Exception:
            label = f"[{element_index}]"
    else:
        label = f"en ({x},{y})"

    method_used = res.get("method")
    if method_used == "uia_pattern":
        effect = res.get("effect", "activé")
        note = res.get("guard_note", "")
        msg = f"{label} : {effect}."
        if note:
            msg += f" ({note})"
        return _done(target, msg, screenshot_after, settle_ms)
    elif method_used == "post_message":
        return _done(
            target,
            f"Clic PostMessage {button} ×{click_count} sur {label} (sans vol de focus)."
            if element_index is not None
            else f"Clic PostMessage {button} ×{click_count} en ({x},{y}) (sans vol de focus).",
            screenshot_after,
            settle_ms,
        )
    else:
        return _done(
            target,
            f"Clic souris {button} ×{click_count} sur {label}."
            if element_index is not None
            else f"Clic souris {button} ×{click_count} en ({x},{y}).",
            screenshot_after,
            settle_ms,
        )


@tool
def computer_move_mouse(
    x: int,
    y: int,
    hwnd: int | None = None,
    foreground: bool = False,
    screenshot_after: bool = False,
    settle_ms: int = 600,
) -> Content:
    """Déplace le vrai curseur sur (x, y) de la dernière capture sans cliquer. Exige foreground=True."""
    target = engine.resolve_target(hwnd)
    frame = engine.action_frame(target)
    frame.check(x, y)
    _require_foreground(foreground, "Le survol à la souris")
    point = frame.to_screen(x, y)
    with engine.input_target(target, point):
        engine.move_cursor(*point)
    return _done(target, f"Curseur en ({x},{y}).", screenshot_after, settle_ms)


@tool
def computer_type_text(
    text: str,
    hwnd: int | None = None,
    element_index: int | None = None,
    clear_first: bool = False,
    method: str = "auto",
    foreground: bool = False,
    screenshot_after: bool = False,
    settle_ms: int = 300,
) -> Content:
    """Écrit du texte dans un champ [N] en arrière-plan via UI Automation ou PostMessage WM_CHAR."""
    if len(text) > MAX_TEXT:
        raise ComputerError(f"Texte trop long ({len(text)} caractères, maximum {MAX_TEXT}) : découpez-le.")
    target = engine.resolve_target(hwnd)
    res = engine.type_text(
        text=text,
        hwnd=target,
        element_index=element_index,
        clear_first=clear_first,
        foreground=foreground,
        method=method,
    )
    method_used = res.get("method")
    if method_used == "uia_value_pattern":
        verb = "remplacé par" if clear_first else "complété de"
        note = res.get("guard_note", "")
        msg = f"[{element_index}] {verb} {len(text)} caractères (arrière-plan, valeur relue)."
        if note:
            msg += f" ({note})"
        return _done(target, msg, screenshot_after, settle_ms)
    elif method_used == "post_message_char":
        chars = res.get("length", len(text))
        val_info = f" (valeur vérifiée : {res['verified_value']!r})" if "verified_value" in res else ""
        return _done(
            target,
            f"Saisie PostMessage WM_CHAR ({chars} caractères) envoyée à {engine.describe(target)} sans vol de focus{val_info}.",
            screenshot_after,
            settle_ms,
        )
    else:
        return _done(target, f"{len(text)} caractères tapés au clavier.", screenshot_after, settle_ms)


@tool
def computer_launch_app(
    command: str,
    background: bool = True,
    wait_ms: int = 800,
) -> Content:
    """Lance une application. Si background=True (défaut), la démarre sans voler le premier plan (SW_SHOWMINNOACTIVE)."""
    res = engine.launch_app(command, background=background, wait_ms=wait_ms)
    target = res.get("hwnd") or engine.foreground()
    title = res.get("title") or command
    pid = res.get("pid")
    mode = "arrière-plan (sans vol de focus)" if background else "premier plan"
    return f"Application lancée en {mode} : PID {pid}, {f'hwnd {target} (« {title} »)' if res.get('hwnd') else 'processus en cours'}."


@tool
def computer_press_key(
    keys: str,
    hwnd: int | None = None,
    repeat: int = 1,
    foreground: bool = False,
    screenshot_after: bool = False,
    settle_ms: int = 400,
) -> Content:
    """Presse une touche, une combinaison ou une suite séparée par des espaces. Exige foreground=True."""
    combos = keys.split()
    if not combos:
        raise ComputerError("Aucune touche indiquée.")
    _bounded("repeat", repeat, 1, 50)
    for combo in combos:
        engine.parse_combo(combo)
    target = engine.resolve_target(hwnd)
    _require_foreground(foreground, "Le clavier")
    with engine.input_target(target):
        for _ in range(repeat):
            for combo in combos:
                engine.press_combo(combo)
    return _done(
        target,
        f"Touches envoyées : {keys}" + (f" ×{repeat}" if repeat > 1 else "") + ".",
        screenshot_after,
        settle_ms,
    )


@tool
def computer_scroll(
    direction: str = "down",
    amount: int = 3,
    element_index: int | None = None,
    x: int | None = None,
    y: int | None = None,
    hwnd: int | None = None,
    foreground: bool = False,
    screenshot_after: bool = False,
    settle_ms: int = 400,
) -> Content:
    """Fait défiler (up, down, left, right) en arrière-plan via UI Automation ou via molette."""
    _bounded("amount", amount, 1, 50)
    target = engine.resolve_target(hwnd)
    if element_index is not None:
        control = engine.element(target, element_index)
        with engine.ForegroundGuard(target) as guard:
            scrolled = engine.background_scroll(control, direction, amount)
        if scrolled:
            return _background(
                target,
                f"Défilement {direction} ×{amount} (arrière-plan) : {scrolled}.",
                guard,
                screenshot_after,
                settle_ms,
            )
        if not foreground:
            raise ComputerError(
                f"[{element_index}] n'est dans aucun conteneur qui peut défiler vers {direction} : soit il n'y a rien "
                "à faire défiler, soit l'application ne l'expose pas. Rien n'a été envoyé."
            )
    if x is not None and y is not None:
        frame = engine.action_frame(target)
        frame.check(x, y)
        point = frame.to_screen(x, y)
    else:
        frame = engine.current_frame(target)
        point = (frame.left + frame.width // 2, frame.top + frame.height // 2)
    _require_foreground(foreground, "La molette de la souris")
    with engine.input_target(target, point):
        engine.scroll_at(*point, direction, amount)
    return _done(target, f"Défilement molette {direction} ×{amount}.", screenshot_after, settle_ms)


@tool
def computer_drag(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    hwnd: int | None = None,
    foreground: bool = False,
    screenshot_after: bool = False,
    settle_ms: int = 400,
) -> Content:
    """Glisse-dépose avec le bouton gauche de (from_x, from_y) à (to_x, to_y). Exige foreground=True."""
    target = engine.resolve_target(hwnd)
    frame = engine.action_frame(target)
    frame.check(from_x, from_y)
    frame.check(to_x, to_y)
    _require_foreground(foreground, "Le glisser-déposer")
    start, end = frame.to_screen(from_x, from_y), frame.to_screen(to_x, to_y)
    with engine.input_target(target, start, end):
        engine.drag(start, end)
    return _done(target, f"Glissé de ({from_x},{from_y}) à ({to_x},{to_y}).", screenshot_after, settle_ms)


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
