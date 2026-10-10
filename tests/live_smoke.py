"""Live end-to-end test of the nexus-computer MCP server against a throwaway WinForms window.

Takes mouse and keyboard focus for about a minute. Run from the project folder:
    .venv\\Scripts\\python.exe tests\\live_smoke.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "tests" / "_live"
APP = ROOT / "tests" / "target_app.ps1"
SAMPLE = "Héllo àéèçù € ß 🎉 日本\nligne 2"
EXPECTED_TOOLS = {
    "computer_list_windows", "computer_focus_window", "computer_screenshot", "computer_zoom",
    "computer_get_window_state", "computer_click", "computer_move_mouse", "computer_type_text",
    "computer_press_key", "computer_scroll", "computer_drag",
}  # fmt: skip
FOREGROUND_TOOLS = {
    "computer_click", "computer_move_mouse", "computer_type_text", "computer_press_key", "computer_scroll", "computer_drag",
}  # fmt: skip
RED, BLUE, LIME = (255, 0, 0), (0, 0, 255), (0, 255, 0)
FRAME_RE = re.compile(
    r"image (\d+)×(\d+) px = (\d+)×(\d+) px physiques \(×([\d.]+)\), origine écran \((-?\d+),(-?\d+)\)"
)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}  {detail}", flush=True)
    return bool(ok)


class EventLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        data = self.path.read_bytes()
        chunk, self.offset = data[self.offset :], len(data)
        return [json.loads(line) for line in chunk.decode("utf-8-sig").splitlines() if line.strip()]

    def wait(self, predicate, timeout: float = 3.0) -> list[dict]:
        """Events since the last read, returned as soon as one matches (or at timeout)."""
        events: list[dict] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            events += self._read()
            if any(predicate(event) for event in events):
                time.sleep(0.15)
                return events + self._read()
            time.sleep(0.05)
        return events

    def drain(self, delay: float = 0.5) -> list[dict]:
        time.sleep(delay)
        return self._read()


def launch(log: Path, *args: str) -> subprocess.Popen:
    return subprocess.Popen(
        ["pwsh", "-NoProfile", "-File", str(APP), "-Log", str(log), *args],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


class Client:
    def __init__(self, session: ClientSession) -> None:
        self.session = session

    async def __call__(self, name: str, **arguments):
        if name in FOREGROUND_TOOLS:  # This harness drives a throwaway window: real input is the point, unless a test says otherwise.
            arguments.setdefault("foreground", True)
        result = await self.session.call_tool(name, arguments)
        text = "\n".join(c.text for c in result.content if c.type == "text")
        images = [c for c in result.content if c.type == "image"]
        return bool(result.isError), text, images


def decode(image) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(image.data))).convert("RGB")


def find_color(img: Image.Image, rgb: tuple[int, int, int], region=None):
    """Bounding box (x0, y0, x1, y1) of pixels close to rgb, inside region if given."""
    width, height = img.size
    x0, y0, x1, y1 = region or (0, 0, width, height)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(width, x1), min(height, y1)
    crop = img.crop((x0, y0, x1, y1))
    cw = crop.width
    xs, ys = [], []
    for i, (r, g, b) in enumerate(crop.getdata()):
        if abs(r - rgb[0]) <= 25 and abs(g - rgb[1]) <= 25 and abs(b - rgb[2]) <= 25:
            xs.append(i % cw)
            ys.append(i // cw)
    if len(xs) < 9:
        return None
    return x0 + min(xs), y0 + min(ys), x0 + max(xs), y0 + max(ys)


def center(box) -> tuple[int, int]:
    return round((box[0] + box[2]) / 2), round((box[1] + box[3]) / 2)


def frame_of(text: str) -> dict:
    match = FRAME_RE.search(text)
    if not match:
        raise AssertionError(f"résumé de cadre introuvable dans : {text[:200]}")
    iw, ih, pw, ph, scale, left, top = match.groups()
    return {"iw": int(iw), "ih": int(ih), "pw": int(pw), "ph": int(ph), "scale": float(scale),
            "left": int(left), "top": int(top)}  # fmt: skip


def tolerance(frame: dict) -> int:
    return math.ceil(2 / frame["scale"]) + 2


async def click_markers(call: Client, log: EventLog, hwnd: int, label: str) -> dict:
    error, text, images = await call("computer_screenshot", hwnd=hwnd)
    if not check(f"{label} : capture", not error and len(images) == 1, text.splitlines()[0] if text else ""):
        raise AssertionError(text)
    frame = frame_of(text)
    img = decode(images[0])
    check(
        f"{label} : image PNG aux dimensions annoncées",
        images[0].mimeType == "image/png" and img.size == (frame["iw"], frame["ih"]),
        f"{img.size}, {len(images[0].data) * 3 // 4 // 1024} Kio",
    )
    tol = tolerance(frame)
    for name, rgb in (("red", RED), ("blue", BLUE)):
        box = find_color(img, rgb)
        if not check(f"{label} : repère {name} visible", box is not None, str(box)):
            continue
        x, y = center(box)
        log.drain(0.1)
        error, text, _ = await call("computer_click", hwnd=hwnd, x=x, y=y)
        events = log.wait(lambda e, n=name: e.get("event") == "marker" and e.get("marker") == n)
        hit = [e for e in events if e.get("event") == "marker" and e.get("marker") == name]
        detail = f"({x},{y}) -> " + (f"écart {hit[0]['dx']},{hit[0]['dy']} px (tol {tol})" if hit else f"aucun clic reçu {text}")
        check(f"{label} : clic sur {name} d'après la capture", not error and hit and abs(hit[0]["dx"]) <= tol and abs(hit[0]["dy"]) <= tol, detail)
    return {"frame": frame, "image": img}


async def run() -> None:
    LIVE.mkdir(parents=True, exist_ok=True)
    for stale in LIVE.glob("*.jsonl"):
        stale.unlink()
    log = EventLog(LIVE / "target.jsonl")
    obstacle_log = EventLog(LIVE / "obstacle.jsonl")
    processes: list[subprocess.Popen] = []
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], cwd=str(ROOT))
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            call = Client(session)
            names = {t.name for t in (await session.list_tools()).tools}
            check("11 outils exposés", names == EXPECTED_TOOLS, str(sorted(names ^ EXPECTED_TOOLS)) if names != EXPECTED_TOOLS else "")

            error, text, _ = await call("computer_click", x=10, y=10)
            check("aucune cible : refus sans clic", error and "Aucune cible" in text, text[:90])

            processes.append(launch(log.path))
            ready = [e for e in log.wait(lambda e: e.get("event") == "ready", 20) if e.get("event") == "ready"]
            if not check("fenêtre de test lancée", bool(ready)):
                return
            hwnd = int(ready[0]["hwnd"])

            error, text, _ = await call("computer_list_windows")
            check("computer_list_windows voit la fenêtre", f"hwnd {hwnd} |" in text)

            error, text, _ = await call("computer_click", hwnd=hwnd, x=10, y=10)
            check("pas de capture : refus des coordonnées", error and "Aucune capture" in text, text[:90])

            # Another process takes the foreground, then the target must be brought back.
            processes.append(launch(obstacle_log.path, "-Mode", "Obstacle", "-Title", "Obstacle", "-X", "300", "-Y", "300", "-Width", "600", "-Height", "400"))
            obstacle_log.wait(lambda e: e.get("event") == "obstacle_ready", 20)
            time.sleep(0.3)
            error, text, _ = await call("computer_focus_window", hwnd=hwnd)
            _, listing, _ = await call("computer_list_windows")
            line = next((item for item in listing.splitlines() if item.startswith(f"hwnd {hwnd} |")), "")
            check("premier plan repris à un autre processus", not error and "[premier plan]" in line, text[:90])
            processes.pop().kill()
            time.sleep(0.3)

            normal = await click_markers(call, log, hwnd, "fenêtre normale")

            error, text, images = await call("computer_click", hwnd=hwnd, x=center(find_color(normal["image"], RED))[0],
                                             y=center(find_color(normal["image"], RED))[1], button="right")
            hit = [e for e in log.wait(lambda e: e.get("event") == "marker") if e.get("event") == "marker"]
            check("clic droit", not error and hit and hit[0]["button"] == "Right", str(hit[:1]))
            bx, by = center(find_color(normal["image"], BLUE))
            error, text, _ = await call("computer_click", hwnd=hwnd, x=bx, y=by, click_count=2)
            hit = [e for e in log.wait(lambda e: e.get("event") == "marker" and e.get("clicks") == 2) if e.get("clicks") == 2]
            check("double-clic", not error and bool(hit), str(hit[:1]))

            error, state, _ = await call("computer_get_window_state", hwnd=hwnd)
            saisie = re.search(r'\[(\d+)\] (?:Edit|Document) "[^"]*"', state)
            valider = re.search(r'\[(\d+)\] Button "Valider"', state)
            first_row = re.search(r'\[(\d+)\] ListItem "Ligne 1" \((\d+),(\d+)\)', state)
            check("UI Automation : champ, bouton et liste trouvés", bool(saisie and valider and first_row),
                  f"{state.count(chr(10))} lignes")
            if not (saisie and valider and first_row):
                print(state)
                return
            saisie, valider = int(saisie.group(1)), int(valider.group(1))

            async def submitted() -> str | None:
                log.drain(0.1)
                await call("computer_click", hwnd=hwnd, element_index=valider)
                events = log.wait(lambda e: e.get("event") == "button")
                button = [e for e in events if e.get("event") == "button"]
                return button[0]["text"].replace("\r\n", "\n").replace("\r", "\n") if button else None

            error, text, _ = await call("computer_type_text", hwnd=hwnd, element_index=saisie, text=SAMPLE)
            got = await submitted()
            check("saisie Unicode (accents, €, emoji, CJK, retour ligne)", not error and got == SAMPLE, repr(got))

            error, text, _ = await call("computer_type_text", hwnd=hwnd, element_index=saisie, text="remplacé", clear_first=True)
            got = await submitted()
            check("clear_first remplace le contenu", not error and got == "remplacé", f"{got!r} {text[:60]}")

            await call("computer_click", hwnd=hwnd, element_index=saisie, method="mouse")
            error, text, _ = await call("computer_press_key", hwnd=hwnd, keys="ctrl+a backspace")
            got = await submitted()
            check("suite de touches ctrl+a backspace", not error and got == "", repr(got))

            await call("computer_click", hwnd=hwnd, element_index=saisie, method="mouse")
            error, text, _ = await call("computer_press_key", hwnd=hwnd, keys="2 A ,")
            got = await submitted()
            check("touches seules tapées telles quelles (2, A, virgule sur AZERTY)", not error and got == "2A,", repr(got))

            error, text, _ = await call("computer_type_text", hwnd=hwnd, element_index=saisie, text="abc\n", clear_first=True)
            got = await submitted()
            check("clear_first avec retour ligne : Entrée réellement pressée", not error and got == "abc\n", f"{got!r} {text[:60]}")

            error, text, images = await call("computer_get_window_state", hwnd=hwnd, screenshot=True)
            badge = images and find_color(decode(images[0]), (230, 30, 90))
            check("numéros des éléments dessinés sur la capture", not error and bool(badge), str(badge))

            frame_now = frame_of(text) if not error else {"iw": 0, "ih": 0}
            error, text, _ = await call("computer_click", hwnd=hwnd, x=frame_now["iw"] + 5, y=5)
            check("coordonnées hors de l'image : refus", error and "hors de l'image" in text, text[:90])

            for combo, code in (("ctrl+,", "Oemcomma"), ("ctrl+.", "OemPeriod")):
                log.drain(0.1)
                error, text, _ = await call("computer_press_key", hwnd=hwnd, keys=combo)
                keys = [e for e in log.wait(lambda e, c=code: e.get("code") == c) if e.get("event") == "key"]
                pressed = [e for e in keys if e["code"] == code]
                check(f"raccourci {combo} -> {code}", not error and pressed and "Control" in pressed[0]["mods"],
                      str([e["code"] for e in keys]))

            log.drain(0.1)
            error, text, _ = await call("computer_scroll", hwnd=hwnd, direction="down", amount=3,
                                        x=int(first_row.group(2)), y=int(first_row.group(3)))
            wheels = [e for e in log.drain(0.8) if e.get("event") == "wheel"]
            check("molette : 3 crans vers le bas", not error and sum(e["delta"] for e in wheels) == -360 and wheels[-1]["top"] > 0,
                  str([(e["delta"], e["top"]) for e in wheels]))

            pad = find_color(normal["image"], LIME)
            if check("zone de glisser visible", pad is not None, str(pad)):
                y = (pad[1] + pad[3]) // 2
                error, text, _ = await call("computer_drag", hwnd=hwnd, from_x=pad[0] + 8, from_y=y, to_x=pad[2] - 8, to_y=y)
                events = log.wait(lambda e: e.get("event") == "drag_up")
                down = next((e for e in events if e.get("event") == "drag_down"), None)
                up = next((e for e in events if e.get("event") == "drag_up"), None)
                check("glisser-déposer d'un bord à l'autre", not error and down and up and down["x"] < down["w"] * 0.15 and up["x"] > up["w"] * 0.85,
                      f"down={down and (down['x'], down['w'])} up={up and (up['x'], up['w'])}")

            # A topmost window of another process over the red marker: the click must be refused.
            frame = normal["frame"]
            rx, ry = center(find_color(normal["image"], RED))
            px = frame["left"] + round((rx + 0.5) * frame["pw"] / frame["iw"])
            py = frame["top"] + round((ry + 0.5) * frame["ph"] / frame["ih"])
            processes.append(launch(obstacle_log.path, "-Mode", "Obstacle", "-Title", "Obstacle", "-TopMost", "-X", str(px - 60), "-Y", str(py - 60), "-Width", "120", "-Height", "120"))
            obstacle_log.wait(lambda e: e.get("event") == "obstacle_ready", 20)
            time.sleep(0.3)
            log.drain(0.1)
            error, text, _ = await call("computer_click", hwnd=hwnd, x=rx, y=ry)
            stray = [e for e in log.drain(0.8) if e.get("event") == "marker"]
            check("point recouvert : refus sans clic", error and "recouvert" in text and not stray, text[:100])
            processes.pop().kill()
            time.sleep(0.3)

            # Background mode: another process stays in front, covering the target, for the whole block.
            processes.append(launch(obstacle_log.path, "-Mode", "Obstacle", "-Title", "Obstacle", "-X", "150", "-Y", "150", "-Width", "600", "-Height", "350"))
            obstacle_log.wait(lambda e: e.get("event") == "obstacle_ready", 20)
            time.sleep(0.4)
            front = lambda listing: next((item.split(" | ")[0] for item in listing.splitlines() if "[premier plan]" in item), "")  # noqa: E731
            _, listing, _ = await call("computer_list_windows")
            front_before = front(listing)

            error, text, images = await call("computer_screenshot", hwnd=hwnd)
            covered_red = images and find_color(decode(images[0]), RED)
            check("arrière-plan : capture d'une fenêtre recouverte", not error and "arrière-plan" in text and bool(covered_red), str(covered_red))

            _, state, _ = await call("computer_get_window_state", hwnd=hwnd)
            index = lambda pattern: int(m.group(1)) if (m := re.search(pattern, state)) else None  # noqa: E731
            rows = [(int(i), int(n)) for i, n in re.findall(r'\[(\d+)\] ListItem "Ligne (\d+)"', state)]  # Visible rows only.
            bg_check = index(r'\[(\d+)\] CheckBox "Option"')
            (bg_first, first_number), (bg_row, row_number) = rows[0], rows[1]
            bg_saisie, bg_valider = index(r'\[(\d+)\] (?:Edit|Document) "[^"]*"'), index(r'\[(\d+)\] Button "Valider"')

            async def background(name, tool_args, event, ok_event):
                log.drain(0.1)
                error, text, _ = await call(tool_args.pop("tool"), hwnd=hwnd, foreground=False, **tool_args)
                events = [e for e in log.wait(lambda e: e.get("event") == event, 2) if e.get("event") == event] if event else []
                check(name, not error and (ok_event(events) if event else True), f"{text[:70]} | {events[-1:] if events else ''}")
                return error, text

            await background("arrière-plan : case cochée", {"tool": "computer_click", "element_index": bg_check}, "checked", lambda ev: ev and ev[-1]["value"] is True)
            await background("arrière-plan : élément de liste sélectionné", {"tool": "computer_click", "element_index": bg_row}, "selected", lambda ev: ev and ev[-1]["index"] == row_number - 1)
            await background("arrière-plan : champ rempli sans clavier", {"tool": "computer_type_text", "element_index": bg_saisie, "text": "fond", "clear_first": True}, None, None)
            _, state, _ = await call("computer_get_window_state", hwnd=hwnd)
            check("arrière-plan : valeur du champ relue", '= "fond"' in state, next((item for item in state.splitlines() if "Document" in item or "Edit" in item), "")[:90])
            await background("arrière-plan : bouton activé", {"tool": "computer_click", "element_index": bg_valider}, "button", lambda ev: bool(ev))
            error, text = await background("arrière-plan : défilement de la liste", {"tool": "computer_scroll", "element_index": bg_first, "direction": "down", "amount": 3}, None, None)
            _, state, _ = await call("computer_get_window_state", hwnd=hwnd)
            now_first = next((int(n) for n in re.findall(r'ListItem "Ligne (\d+)"', state)), 0)
            check("arrière-plan : liste effectivement défilée", not error and now_first > first_number, f"première ligne visible : {first_number} -> {now_first}")

            log.drain(0.1)
            error, text, _ = await call("computer_click", hwnd=hwnd, x=50, y=88, foreground=False)
            stray = [e for e in log.drain(0.6) if e.get("event") == "marker"]
            check("sans foreground=True : clic souris refusé", error and "foreground=True" in text and not stray, text[:90])

            _, listing, _ = await call("computer_list_windows")
            check("arrière-plan : premier plan jamais repris", front(listing) == front_before and front_before != f"hwnd {hwnd}", f"{front_before} -> {front(listing)}")
            processes.pop().kill()
            time.sleep(0.3)

            error, text, _ = await call("computer_click", hwnd=hwnd, element_index=999)
            check("élément inconnu : erreur", error and "inconnu" in text, text[:80])

            hidden_log = EventLog(LIVE / "hidden.jsonl")
            startup = subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=0)  # SW_HIDE
            processes.append(subprocess.Popen(
                ["pwsh", "-NoProfile", "-File", str(APP), "-Log", str(hidden_log.path), "-Title", "Fenetre cachee"],
                creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup,
            ))  # fmt: skip
            hidden = [e for e in hidden_log.wait(lambda e: e.get("event") == "ready", 20) if e.get("event") == "ready"]
            if hidden:
                error, text, images = await call("computer_screenshot", hwnd=int(hidden[0]["hwnd"]))
                check("fenêtre invisible : capture refusée", error and "invisible" in text and not images, text[:90])
            processes.pop().kill()

            error, text, _ = await call("computer_press_key", hwnd=hwnd, keys="win+up")
            time.sleep(1.0)
            _, listing, _ = await call("computer_list_windows")
            line = next((item for item in listing.splitlines() if item.startswith(f"hwnd {hwnd} |")), "")
            check("win+up agrandit la fenêtre", "agrandie" in line, line[:120])
            error, text, _ = await call("computer_click", hwnd=hwnd, x=5, y=5)
            check("taille changée : refus des anciennes coordonnées", error and "changé de taille" in text, text[:100])
            maximized = await click_markers(call, log, hwnd, "fenêtre agrandie")
            check("cadre agrandi sans bordures invisibles", maximized["frame"]["left"] >= 0 and maximized["frame"]["top"] >= 0,
                  f"origine ({maximized['frame']['left']},{maximized['frame']['top']})")

            error, text, images = await call("computer_screenshot", hwnd=0)
            if check("capture écran entier", not error and len(images) == 1, text.splitlines()[0] if text else ""):
                screen = frame_of(text)
                window = maximized["frame"]
                to_img = lambda sx, sy: (round((sx - screen["left"]) * screen["iw"] / screen["pw"]), round((sy - screen["top"]) * screen["ih"] / screen["ph"]))  # noqa: E731
                region = (*to_img(window["left"], window["top"]), *to_img(window["left"] + window["pw"], window["top"] + window["ph"]))
                box = find_color(decode(images[0]), RED, region)
                if check("repère rouge visible sur l'écran entier", box is not None, str(box)):
                    x, y = center(box)
                    log.drain(0.1)
                    error, text, _ = await call("computer_click", hwnd=0, x=x, y=y)
                    hit = [e for e in log.wait(lambda e: e.get("event") == "marker") if e.get("event") == "marker"]
                    tol = tolerance(screen)
                    check("clic écran entier d'après la capture", not error and hit and abs(hit[0]["dx"]) <= tol and abs(hit[0]["dy"]) <= tol,
                          f"écart {hit[0]['dx'] if hit else '?'},{hit[0]['dy'] if hit else '?'} (tol {tol})")

            box = find_color(maximized["image"], RED)
            error, text, images = await call("computer_zoom", hwnd=hwnd, x1=max(0, box[0] - 20), y1=max(0, box[1] - 20), x2=box[2] + 20, y2=box[3] + 20)
            if check("zoom", not error and len(images) == 1, text[:80]):
                zoomed = decode(images[0])
                check("zoom : résolution supérieure à la capture", zoomed.width > (box[2] - max(0, box[0] - 20) + 20), f"{zoomed.size}")

            error, text, _ = await call("computer_press_key", hwnd=hwnd, keys="alt+f4")
            closed = [e for e in log.wait(lambda e: e.get("event") == "closed", 5) if e.get("event") == "closed"]
            check("alt+f4 ferme la fenêtre", not error and bool(closed), text[:80])
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} vérifications réussies" + (f" — échecs : {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(run())
