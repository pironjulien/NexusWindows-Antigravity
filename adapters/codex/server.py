"""nexus-computer adapter for OpenAI Codex and ChatGPT Desktop.

Optimized for OpenAI function calling, deterministic background UI Automation,
stale element detection, and token-efficient descriptions.
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
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.stdio import stdio_server

import core.engine as engine
from core.engine import SCREEN, ComputerError

CODEX_INSTRUCTIONS = """Windows desktop via background UI Automation.
1. Inspect UI elements with computer_get_window_state to get [N] element IDs.
2. Interact using element_index in computer_click or computer_type_text (silent, background).
3. If an action fails with STALE_ELEMENT, re-run computer_get_window_state.
4. Physical mouse/keyboard requires explicit foreground=True."""

mcp = FastMCP("nexus-computer", instructions=CODEX_INSTRUCTIONS, log_level="WARNING")
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
        return f"{message}\n(capture failed: {error})"


def _require_foreground(foreground: bool, what: str) -> None:
    if not foreground:
        raise ComputerError(
            f"{what} requires physical mouse/keyboard and steals user foreground. "
            "Rerun with foreground=True only if authorized by user. No action was taken."
        )


def _background(
    target: int, message: str, guard: engine.ForegroundGuard, screenshot_after: bool, settle_ms: int
) -> Content:
    note = guard.summary()
    return _done(target, f"{message} ({note})" if note else message, screenshot_after, settle_ms)


@tool
def computer_list_windows() -> str:
    """Lists visible desktop windows ordered from foreground to background in structured JSON."""
    windows = engine.list_windows(visible_only=True)
    payload = {
        "schema": "nexus-computer/1",
        "count": len(windows),
        "windows": [
            {
                "hwnd": w["hwnd"],
                "title": w["title"],
                "process": w["process_name"],
                "pid": w["pid"],
                "state": w["state"],
                "foreground": w["foreground"],
                "bounds": [w["bounds"][0], w["bounds"][1], w["bounds"][2], w["bounds"][3]] if w["bounds"] else None,
            }
            for w in windows
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


@tool
def computer_focus_window(
    hwnd: int | None = None,
    title: str | None = None,
    process_name: str | None = None,
    screenshot_after: bool = False,
) -> Content:
    """Brings a window to the foreground and un-minimizes if needed."""
    target = hwnd if hwnd is not None else engine.find_window(title, process_name)
    target = engine.resolve_target(target)
    if target == SCREEN:
        return "Target: Full screen."
    if not engine.bring_to_front(target):
        active = engine.foreground()
        raise ComputerError(
            f"Windows refused foreground to {engine.describe(target)} "
            f"(active: {engine.describe(active) if active else 'none'})."
        )
    return _done(target, f"Foreground: {engine.describe(target)}.", screenshot_after, 300)


@tool
def computer_screenshot(hwnd: int | None = None, delay_ms: int = 0, annotate: bool = False) -> Content:
    """Captures a window offscreen without bringing it to the front (hwnd=0 for entire screen)."""
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
    """Zooms into a bounding box (x1, y1)-(x2, y2) of the latest screenshot."""
    target = engine.resolve_target(hwnd)
    png, summary = engine.zoom(target, x1, y1, x2, y2)
    return [f"{engine.describe(target)} — {summary}", Image(data=png, format="png")]


@tool
def computer_get_window_state(hwnd: int | None = None, max_elements: int = 60, screenshot: bool = False) -> Content:
    """Extracts interactive UI Automation elements for the window with structured JSON schema."""
    target = engine.resolve_target(hwnd)
    frame, lines, truncated = engine.window_elements(target, min(max(1, max_elements), 300))
    if len(lines) < 2:
        time.sleep(0.4)
        frame, lines, truncated = engine.window_elements(target, max_elements)

    elements_list = []
    for idx, ctrl in sorted(engine.SESSION.elements.items()):
        box = engine.SESSION.marks.get(idx)
        if not box:
            continue
        try:
            name = (ctrl.Name or "")[:80]
            ctype = ctrl.ControlTypeName.removesuffix("Control")
        except Exception:
            continue
        elements_list.append(
            {
                "id": idx,
                "role": ctype,
                "name": name,
                "bbox_px": list(box),
                "center_px": [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2],
            }
        )

    obs_payload = {
        "schema": "nexus-computer/1",
        "observation_id": f"obs_{target}_{int(time.time() * 1000)}",
        "target": {
            "hwnd": target,
            "title": engine.window_title(target),
            "process": engine.process_name(engine.window_pid(target)),
            "pid": engine.window_pid(target),
        },
        "frame": {
            "image_px": [frame.image_width, frame.image_height],
            "physical_px": [frame.width, frame.height],
            "origin": [frame.left, frame.top],
            "scale": round(frame.image_width / max(1, frame.width), 4),
        },
        "truncated": truncated,
        "element_count": len(elements_list),
        "elements": elements_list,
    }
    json_text = json.dumps(obs_payload, indent=2, ensure_ascii=False)
    if screenshot:
        _, png, _ = engine.screenshot(target, engine.SESSION.marks)
        return [json_text, Image(data=png, format="png")]
    return json_text


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
    """Clicks an element [N] in background via UI Automation, or clicks at (x, y) coordinates."""
    target = engine.resolve_target(hwnd)
    if method not in ("auto", "uia", "mouse"):
        raise ComputerError(f"Unknown method: {method!r} (expected auto, uia, or mouse).")
    simple = button == "left" and click_count == 1
    if element_index is not None:
        if target != engine.SESSION.elements_hwnd or element_index not in engine.SESSION.elements:
            raise ComputerError(
                f"STALE_ELEMENT: Element [{element_index}] not found in target window (hwnd={target}). "
                "The UI tree may have changed or the window was reloaded. Call computer_get_window_state to refresh element IDs."
            )
        try:
            control = engine.element(target, element_index)
        except Exception:
            raise ComputerError(
                f"STALE_ELEMENT: Element [{element_index}] is stale or inaccessible in target window. "
                "Call computer_get_window_state to refresh element IDs."
            ) from None
        label = f"[{element_index}] {engine._quoted(control.Name, 60)}"
        if method != "mouse" and simple:
            with engine.ForegroundGuard(target) as guard:
                effect = engine.background_activate(control)
            if effect:
                return _background(target, f"{label}: {effect}.", guard, screenshot_after, settle_ms)
        if method == "uia":
            raise ComputerError(f"{label} does not support UI Automation click. Try mouse click with foreground=True.")
        _require_foreground(foreground, f"Click on {label}")
        engine.ensure_input_target(target)
        center = engine.element_center(control, engine.current_frame(target))
        if center is None:
            raise ComputerError(f"{label} is not currently visible in window.")
        engine.ensure_point(target, *center)
        engine.click_at(*center, button=button, count=click_count)
        return _done(target, f"Physical mouse click {button} x{click_count} on {label}.", screenshot_after, settle_ms)

    if x is None or y is None:
        raise ComputerError("Specify either element_index or both x and y.")
    frame = engine.action_frame(target)
    frame.check(x, y)
    _require_foreground(foreground, "Click at coordinates")
    point = frame.to_screen(x, y)
    engine.ensure_input_target(target)
    engine.ensure_point(target, *point)
    engine.click_at(*point, button=button, count=click_count)
    return _done(target, f"Physical click {button} x{click_count} at ({x},{y}).", screenshot_after, settle_ms)


@tool
def computer_move_mouse(
    x: int,
    y: int,
    hwnd: int | None = None,
    foreground: bool = False,
    screenshot_after: bool = False,
    settle_ms: int = 600,
) -> Content:
    """Moves physical mouse cursor to (x, y). Requires foreground=True."""
    target = engine.resolve_target(hwnd)
    frame = engine.action_frame(target)
    frame.check(x, y)
    _require_foreground(foreground, "Mouse hover")
    point = frame.to_screen(x, y)
    engine.ensure_input_target(target)
    engine.ensure_point(target, *point)
    engine.move_cursor(*point)
    return _done(target, f"Cursor moved to ({x},{y}).", screenshot_after, settle_ms)


@tool
def computer_type_text(
    text: str,
    hwnd: int | None = None,
    element_index: int | None = None,
    clear_first: bool = False,
    foreground: bool = False,
    screenshot_after: bool = False,
    settle_ms: int = 300,
) -> Content:
    """Types text into an element [N] via UI Automation ValuePattern in background."""
    if len(text) > MAX_TEXT:
        raise ComputerError(f"Text too long ({len(text)} chars, maximum {MAX_TEXT}). Split into smaller batches.")
    target = engine.resolve_target(hwnd)
    if element_index is not None:
        if target != engine.SESSION.elements_hwnd or element_index not in engine.SESSION.elements:
            raise ComputerError(
                f"STALE_ELEMENT: Element [{element_index}] not found in target window (hwnd={target}). "
                "The UI tree may have changed or the window was reloaded. Call computer_get_window_state to refresh element IDs."
            )
        try:
            control = engine.element(target, element_index)
        except Exception:
            raise ComputerError(
                f"STALE_ELEMENT: Element [{element_index}] is stale or inaccessible in target window. "
                "Call computer_get_window_state to refresh element IDs."
            ) from None
        with engine.ForegroundGuard(target) as guard:
            written = engine.set_value(control, text, append=not clear_first)
        if written:
            verb = "replaced with" if clear_first else "appended"
            return _background(
                target,
                f"[{element_index}] {verb} {len(text)} chars (background UIA).",
                guard,
                screenshot_after,
                settle_ms,
            )
        _require_foreground(foreground, f"Keyboard input into [{element_index}]")
        engine.ensure_input_target(target)
        if not engine.focus_element(control):
            raise ComputerError(f"[{element_index}] could not receive keyboard focus. Re-inspect window state.")
    else:
        _require_foreground(foreground, "Keyboard input without element_index")
        engine.ensure_input_target(target)
    if clear_first:
        engine.press_combo("ctrl+a")
        engine.press_combo("backspace")
    engine.type_unicode(text)
    return _done(target, f"Typed {len(text)} characters via keyboard.", screenshot_after, settle_ms)


@tool
def computer_press_key(
    keys: str,
    hwnd: int | None = None,
    repeat: int = 1,
    foreground: bool = False,
    screenshot_after: bool = False,
    settle_ms: int = 400,
) -> Content:
    """Sends keystrokes or combinations ('enter', 'ctrl+c', 'alt+f4'). Requires foreground=True."""
    combos = keys.split()
    if not combos:
        raise ComputerError("No keys specified.")
    repeat = min(max(1, repeat), 50)
    for combo in combos:
        engine.parse_combo(combo)
    target = engine.resolve_target(hwnd)
    _require_foreground(foreground, "Keyboard shortcut")
    engine.ensure_input_target(target)
    for _ in range(repeat):
        for combo in combos:
            engine.press_combo(combo)
    return _done(
        target,
        f"Keys sent: {keys}" + (f" x{repeat}" if repeat > 1 else "") + ".",
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
    """Scrolls a container in the background via UI Automation or via physical wheel."""
    amount = min(max(1, amount), 50)
    target = engine.resolve_target(hwnd)
    if element_index is not None:
        try:
            control = engine.element(target, element_index)
        except Exception:
            raise ComputerError(
                f"STALE_ELEMENT: Element [{element_index}] not found. Call computer_get_window_state to refresh."
            ) from None
        with engine.ForegroundGuard(target) as guard:
            scrolled = engine.background_scroll(control, direction, amount)
        if scrolled:
            return _background(
                target,
                f"Scrolled {direction} x{amount} (background UIA): {scrolled}.",
                guard,
                screenshot_after,
                settle_ms,
            )
        if not foreground:
            raise ComputerError(
                f"[{element_index}] does not support background scroll. Rerun with foreground=True for mouse wheel."
            )
    if x is not None and y is not None:
        frame = engine.action_frame(target)
        frame.check(x, y)
        point = frame.to_screen(x, y)
    else:
        frame = engine.current_frame(target)
        point = (frame.left + frame.width // 2, frame.top + frame.height // 2)
    _require_foreground(foreground, "Mouse wheel scroll")
    engine.ensure_input_target(target)
    engine.ensure_point(target, *point)
    engine.scroll_at(*point, direction, amount)
    return _done(target, f"Scrolled mouse wheel {direction} x{amount}.", screenshot_after, settle_ms)


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
    """Drags mouse from (from_x, from_y) to (to_x, to_y). Requires foreground=True."""
    target = engine.resolve_target(hwnd)
    frame = engine.action_frame(target)
    frame.check(from_x, from_y)
    frame.check(to_x, to_y)
    _require_foreground(foreground, "Drag and drop")
    start, end = frame.to_screen(from_x, from_y), frame.to_screen(to_x, to_y)
    engine.ensure_input_target(target)
    engine.ensure_point(target, *start)
    engine.ensure_point(target, *end)
    engine.drag(start, end)
    return _done(target, f"Dragged from ({from_x},{from_y}) to ({to_x},{to_y}).", screenshot_after, settle_ms)


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
