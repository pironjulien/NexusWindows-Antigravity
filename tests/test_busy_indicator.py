"""Logo « agent au travail » : allumé pendant les actions (jamais les lectures), éteint 1,618 s après, rendu du logo."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import busy_indicator
import mcp_server
import pytest


@pytest.fixture
def fresh(monkeypatch):
    """Indicateur neuf dont le fil de dessin n'est jamais lancé (rien à l'écran)."""
    state = busy_indicator.Indicator()
    monkeypatch.setattr(busy_indicator, "INDICATOR", state)
    monkeypatch.setattr(busy_indicator, "enabled", lambda: True)
    monkeypatch.setattr(state, "_run", lambda: None)
    return state


def test_actions_light_it_and_reads_do_not(fresh, monkeypatch):
    seen: list[tuple[int, int]] = []
    monkeypatch.setattr(mcp_server.computer_client, "resolve_window", lambda hwnd: 4242)
    monkeypatch.setattr(mcp_server.computer_client, "list_windows", lambda **_: [])

    def close_window(hwnd):
        seen.append((fresh._active, fresh._target))
        return {"success": True, "verified": True}

    monkeypatch.setattr(mcp_server.computer_client, "close_window", close_window)
    mcp_server.computer_list_windows()
    assert not fresh.busy()
    mcp_server.computer_close_window(4242)
    assert seen == [(1, 4242)]  # allumé pendant l'action, sur la fenêtre pilotée
    assert fresh._active == 0 and fresh.busy()  # encore visible juste après


def test_failed_action_turns_it_off(fresh, monkeypatch):
    def broken(hwnd):
        raise RuntimeError("fenêtre partie")

    monkeypatch.setattr(mcp_server.computer_client, "resolve_window", broken)
    mcp_server.computer_close_window(1)
    assert fresh._active == 0


def test_lingers_then_goes_out(fresh, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(busy_indicator.time, "monotonic", lambda: clock[0])
    with busy_indicator.working(7):
        clock[0] += 30
        assert fresh.busy()
    clock[0] += busy_indicator.LINGER_S - 0.1
    assert fresh.busy()
    clock[0] += 0.2
    assert not fresh.busy()


def test_disabled_draws_nothing(monkeypatch):
    state = busy_indicator.Indicator()
    monkeypatch.setattr(busy_indicator, "INDICATOR", state)
    with busy_indicator.working():  # NEXUS_WINDOWS_INDICATOR=0 (conftest)
        pass
    assert state._thread is None


def test_frames_render_logo_without_halo():
    frames = busy_indicator.render_frames(72, count=8)
    side = round(72 * busy_indicator.CANVAS)
    assert len(frames) == 8 and all(len(f) == side * side * 4 for f in frames)

    def alpha(frame: bytes, x: int, y: int) -> int:
        return frame[(y * side + x) * 4 + 3]

    def opaque_columns(frame: bytes) -> int:
        return sum(alpha(frame, x, side // 2) > 200 for x in range(side))

    assert alpha(frames[0], side // 2, side // 2) == 255
    assert alpha(frames[0], 0, 0) == 0
    assert 60 <= opaque_columns(frames[0]) <= 80
    assert opaque_columns(frames[2]) < opaque_columns(frames[0])  # il tourne sur lui-même
    at = ((side // 2 - 40) * side + side // 2) * 4
    b, g, r, _ = frames[0][at : at + 4]
    assert b == g == r == 0  # plus de halo bleu-violet (Julien, 22/10) : au plus l'ombre noire


def test_imports_off_windows():
    code = (
        "import ctypes, os, sys; del ctypes.WINFUNCTYPE; del ctypes.WinDLL; os.name = 'posix'; "
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / 'client')!r}); "
        "import busy_indicator; assert not busy_indicator.enabled()"
    )
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
