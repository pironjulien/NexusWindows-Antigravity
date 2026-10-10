"""Live end-to-end test of the background mode through the MCP server, without mouse or keyboard.

The throwaway WinForms window opens behind every other window and stays there: every action goes through UI
Automation while the user's window keeps the foreground. Safe while Julien works: nothing touches the mouse or
the keyboard, and each action waits for a short pause in his input. Run from the project folder:
    .venv\\Scripts\\python.exe tests\\live_background.py
"""

from __future__ import annotations

import asyncio
import ctypes
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Self

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from live_smoke import APP, LIVE, EventLog, check, decode, find_color, results  # noqa: E402

import engine  # noqa: E402

MAX_AWAY_MS = 100  # Longest the user's window may lose the foreground during one action.
TEXT = "fond ✓ éàç 🎉"
ELEMENTS = {
    "option": r'\[(\d+)\] CheckBox "Option"',
    "row": r'\[(\d+)\] ListItem "Ligne 5"',
    "first": r'\[(\d+)\] ListItem "Ligne 1"',
    "field": r'\[(\d+)\] (?:Edit|Document) "[^"]*"',
    "valider": r'\[(\d+)\] Button "Valider"',
}


class ForegroundSampler:
    """Every foreground change, sampled each millisecond by this test process, independently of the server."""

    def __init__(self) -> None:
        self.changes: list[tuple[float, int]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> Self:
        ctypes.windll.winmm.timeBeginPeriod(1)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join()
        ctypes.windll.winmm.timeEndPeriod(1)

    def _run(self) -> None:
        last = None
        while not self._stop.is_set():
            current = engine.foreground()
            if current != last:
                self.changes.append((time.perf_counter(), current))
                last = current
            time.sleep(0.001)

    def away_ms(self, since: float, front: int) -> float:
        """Time the foreground spent away from front after since."""
        away, current, start = 0.0, front, since
        for moment, hwnd in [change for change in self.changes if change[0] >= since]:
            if current != front:
                away += moment - start
            current, start = hwnd, moment
        if current != front:
            away += time.perf_counter() - start
        return 1000 * away


def wait_for_pause(seconds: float = 1.5, timeout: float = 60) -> None:
    """Waits until the user has not touched mouse or keyboard for a moment, so a flicker cannot catch a keystroke."""
    deadline = time.monotonic() + timeout
    while (engine.GetTickCount() - engine.user_input_tick()) / 1000 < seconds and time.monotonic() < deadline:
        time.sleep(0.1)


def z_rank(hwnd: int) -> int:
    order = [window["hwnd"] for window in engine.list_windows()]
    return order.index(hwnd) if hwnd in order else -1


class Scenario:
    def __init__(self, session: ClientSession, sampler: ForegroundSampler, log: EventLog, hwnd: int) -> None:
        self.session, self.sampler, self.log, self.hwnd = session, sampler, log, hwnd

    async def call(self, name: str, **arguments) -> tuple[bool, str, list]:
        result = await self.session.call_tool(name, arguments)
        text = "\n".join(c.text for c in result.content if c.type == "text")
        return bool(result.isError), text, [c for c in result.content if c.type == "image"]

    async def background(self, label: str, name: str, arguments: dict, accept=None) -> None:
        """One background action: its effect, the user's foreground and the target's place in the Z-order."""
        wait_for_pause()
        self.log.drain(0.05)
        # Julien may switch windows between actions: the window to protect is the one in front now.
        front, rank, start = engine.foreground(), z_rank(self.hwnd), time.perf_counter()
        error, text, _ = await self.call(name, hwnd=self.hwnd, **arguments)
        away, still_front = self.sampler.away_ms(start, front), engine.foreground() == front
        events = self.log.wait(accept, 3) if accept else []
        check(f"{label} : effet obtenu", not error and (accept is None or any(accept(e) for e in events)),
              text.splitlines()[0][:110] if text else "")
        kept = check(f"{label} : premier plan gardé (≤ {MAX_AWAY_MS} ms)", away <= MAX_AWAY_MS and still_front,
                     f"{away:.0f} ms hors de {engine.describe(front)}")
        if not kept:
            print("      " + " ".join(f"{1000 * (moment - start):+.0f}ms:{engine.describe(hwnd) if hwnd else 0}"
                                      for moment, hwnd in self.sampler.changes if moment >= start))
        check(f"{label} : place dans l'empilement gardée", z_rank(self.hwnd) == rank, f"rang {rank} → {z_rank(self.hwnd)}")

    async def run(self) -> None:
        error, state, images = await self.call("computer_get_window_state", hwnd=self.hwnd, screenshot=True)
        check("capture annotée en arrière-plan", not error and len(images) == 1 and "arrière-plan" in state, state.splitlines()[-1][:90])
        if images:
            check("numéros dessinés", find_color(decode(images[0]), engine.MARK_RGB) is not None)
        check("la capture n'a pas pris le premier plan", engine.foreground() != self.hwnd)
        found = {key: re.search(pattern, state) for key, pattern in ELEMENTS.items()}
        if not check("éléments trouvés", all(found.values()), str([key for key, match in found.items() if not match])):
            print(state)
            return
        index = {key: int(match.group(1)) for key, match in found.items()}

        await self.background("case cochée", "computer_click", {"element_index": index["option"]},
                              lambda e: e.get("event") == "checked" and e.get("value") is True)
        await self.background("élément de liste sélectionné", "computer_click", {"element_index": index["row"]},
                              lambda e: e.get("event") == "selected" and e.get("index") == 4)
        await self.background("champ rempli", "computer_type_text", {"element_index": index["field"], "text": TEXT, "clear_first": True})
        await self.background("bouton activé, texte reçu", "computer_click", {"element_index": index["valider"]},
                              lambda e: e.get("event") == "button" and e.get("text") == TEXT)
        await self.background("liste défilée", "computer_scroll", {"element_index": index["first"], "direction": "down", "amount": 3})

        self.log.drain(0.05)
        error, text, _ = await self.call("computer_click", hwnd=self.hwnd, x=20, y=20)
        stray = [e for e in self.log.drain(0.5) if e.get("event") == "marker"]
        check("clic souris refusé sans foreground=True", error and "foreground=True" in text and not stray, text[:80])


async def run() -> None:
    LIVE.mkdir(parents=True, exist_ok=True)
    log = EventLog(LIVE / "background.jsonl")
    log.path.unlink(missing_ok=True)
    app = subprocess.Popen(
        ["pwsh", "-NoProfile", "-File", str(APP), "-Log", str(log.path), "-Behind", "-Title", "NexusClaude Background"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], cwd=str(ROOT))
    try:
        ready = [e for e in log.wait(lambda e: e.get("event") == "ready", 20) if e.get("event") == "ready"]
        if check("fenêtre de test ouverte", bool(ready)):
            hwnd = int(ready[0]["hwnd"])
            time.sleep(0.5)
            front = engine.foreground()
            check("ouverte derrière, premier plan intact", front != hwnd and z_rank(hwnd) > 0, engine.describe(front))
            with ForegroundSampler() as sampler:
                async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                    await session.initialize()
                    await Scenario(session, sampler, log, hwnd).run()
    finally:
        app.kill()

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} vérifications réussies" + (f" — échecs : {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(run())
