"""Molette Tk d'une fenêtre entièrement recouverte, déplacée hors écran le temps du geste (recette de NexusWindows Claude
3.7.0 du 27/10) : couverture exacte, même contrôle avant et après, retour relu, échec du retour terminal."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import win32_controls as wc  # noqa: E402

TARGET = (100, 100, 300, 200)


def _env(monkeypatch, covers=None, child_after=43, refuse_back=0, in_front=False, dpi=96, styles=None, regions=()):
    """Fenêtre 42 (TARGET) sous `covers` (fenêtres au-dessus, du bas vers le haut)."""
    calls: list = []
    covers = {1: (0, 0, 1000, 1000)} if covers is None else covers
    order = [42, *covers]
    place = {"left": TARGET[0], "top": TARGET[1]}
    refused = {"n": refuse_back}
    width, height = TARGET[2] - TARGET[0], TARGET[3] - TARGET[1]

    def rect(h):
        return (place["left"], place["top"], place["left"] + width, place["top"] + height)

    def set_pos(h, after, x, y, cx, cy, flags):
        calls.append(("move", x, y))
        if x == TARGET[0] and refused["n"]:
            refused["n"] -= 1
            return 0
        place.update(left=x, top=y)
        return 1

    def prev(h, cmd):
        i = order.index(h)
        return order[i + 1] if i + 1 < len(order) else 0

    monkeypatch.setattr(wc, "_IsZoomed", lambda h: 0)
    monkeypatch.setattr(wc, "_IsIconic", lambda h: 0)
    monkeypatch.setattr(wc, "_IsWindowVisible", lambda h: 1)
    monkeypatch.setattr(wc, "_cloaked", lambda h: False)
    monkeypatch.setattr(wc, "_GetWindowLongW", lambda h, i: (styles or {}).get(h, 0))
    monkeypatch.setattr(wc, "_GetWindowRgnBox", lambda h, r: 1 if h in regions else 0)
    monkeypatch.setattr(wc, "_monitor_dpi", lambda h: dpi)
    monkeypatch.setattr(wc, "_GetDpiForWindow", lambda h: 96)
    monkeypatch.setattr(wc, "_GetWindow", prev)
    monkeypatch.setattr(wc, "_frame", lambda h: rect(h) if h == 42 else covers[h])
    monkeypatch.setattr(wc, "_rect", rect)
    monkeypatch.setattr(wc, "_GetSystemMetrics", lambda i: {wc.SM_XVIRTUALSCREEN: 0, wc.SM_CXVIRTUALSCREEN: 1000}[i])
    monkeypatch.setattr(wc, "_SetWindowPos", set_pos)
    monkeypatch.setattr(wc, "deepest_child_at", lambda top, x, y: 43 if place["left"] == TARGET[0] else child_after)
    monkeypatch.setattr(wc, "_WindowFromPoint", lambda p: child_after)
    monkeypatch.setattr(wc, "_thread_of", lambda h: 6)
    monkeypatch.setattr(wc, "is_window", lambda h: bool(h))
    monkeypatch.setattr(wc, "_in_front", lambda thread: in_front and place["left"] != TARGET[0])
    monkeypatch.setattr(wc, "post", lambda h, m, wp, lp: calls.append(("post", h, m, lp)))
    monkeypatch.setattr(wc.time, "sleep", lambda s: None)
    return calls


def test_wheel_moves_posts_at_the_shifted_point_and_comes_back(monkeypatch):
    calls = _env(monkeypatch)
    assert wc.tk_wheel_offscreen(42, 150, 160, -120) == 43
    dx = 1000 + 50 - 100
    assert calls == [
        ("move", 100 + dx, 100),
        ("post", 43, wc.WM_MOUSEWHEEL, wc._lparam_xy(150 + dx, 160)),
        ("move", 100, 100),
    ]


def test_a_one_pixel_visible_strip_is_enough_to_refuse(monkeypatch):
    calls = _env(monkeypatch, covers={1: (0, 0, 110, 1000), 2: (111, 0, 1000, 1000)})
    with pytest.raises(wc.MessageError, match="en partie visible"):
        wc.tk_wheel_offscreen(42, 150, 160, -120)
    assert calls == []


def test_two_adjacent_windows_cover_together(monkeypatch):
    _env(monkeypatch, covers={1: (0, 0, 200, 1000), 2: (200, 0, 1000, 1000)})
    assert wc.fully_covered(42)


@pytest.mark.parametrize("style", [0x00080000, 0x00000020, 0x00200000])
def test_a_cover_not_proven_opaque_never_counts(monkeypatch, style):
    _env(monkeypatch, styles={1: style})
    assert not wc.fully_covered(42)


def test_a_shaped_cover_never_counts(monkeypatch):
    _env(monkeypatch, regions={1})
    assert not wc.fully_covered(42)


def test_corner_radius_follows_the_monitor_scale(monkeypatch):
    _env(monkeypatch, covers={1: (88, 100, 1000, 1000)}, dpi=240)
    assert not wc.fully_covered(42)


def test_unreadable_monitor_scale_never_counts(monkeypatch):
    _env(monkeypatch, dpi=0)
    assert not wc.fully_covered(42)


def test_another_control_off_screen_sends_nothing_and_comes_back(monkeypatch):
    calls = _env(monkeypatch, child_after=44)
    with pytest.raises(wc.MessageError, match="même contrôle"):
        wc.tk_wheel_offscreen(42, 150, 160, -120)
    assert [c[0] for c in calls] == ["move", "move"] and calls[-1] == ("move", 100, 100)


def test_window_brought_forward_sends_nothing(monkeypatch):
    calls = _env(monkeypatch, in_front=True)
    with pytest.raises(wc.MessageError, match="premier plan"):
        wc.tk_wheel_offscreen(42, 150, 160, -120)
    assert not [c for c in calls if c[0] == "post"] and calls[-1] == ("move", 100, 100)


def test_a_refused_return_is_tried_once_more(monkeypatch):
    calls = _env(monkeypatch, refuse_back=1)
    assert wc.tk_wheel_offscreen(42, 150, 160, -120) == 43
    assert [c for c in calls if c[0] == "move"][-2:] == [("move", 100, 100), ("move", 100, 100)]


def test_a_window_not_put_back_is_terminal(monkeypatch):
    _env(monkeypatch, refuse_back=2)
    with pytest.raises(wc.WindowNotRestored, match="effet inconnu"):
        wc.tk_wheel_offscreen(42, 150, 160, -120)
    assert not issubclass(wc.WindowNotRestored, wc.MessageError)


def test_a_maximized_window_is_never_moved(monkeypatch):
    calls = _env(monkeypatch)
    monkeypatch.setattr(wc, "_IsZoomed", lambda h: 1)
    with pytest.raises(wc.MessageError, match="agrandie"):
        wc.tk_wheel_offscreen(42, 150, 160, -120)
    assert calls == []


def test_horizontal_wheel_is_posted_as_hwheel(monkeypatch):
    calls = _env(monkeypatch)
    wc.tk_wheel_offscreen(42, 150, 160, 120, True)
    assert [c[2] for c in calls if c[0] == "post"] == [wc.WM_MOUSEHWHEEL]


def test_no_control_under_the_point_sends_nothing(monkeypatch):
    calls = _env(monkeypatch)
    monkeypatch.setattr(wc, "deepest_child_at", lambda top, x, y: 0)
    with pytest.raises(wc.MessageError, match="Aucun contrôle"):
        wc.tk_wheel_offscreen(42, 150, 160, -120)
    assert calls == []


def test_overlapped_sees_any_window_above_that_touches_the_frame(monkeypatch):
    _env(monkeypatch, covers={1: (290, 190, 400, 400)}, styles={1: 0x00080000})
    assert wc.overlapped(42)  # même translucide : la copie d'écran ne montrerait pas que la cible


def test_overlapped_ignores_windows_elsewhere(monkeypatch):
    _env(monkeypatch, covers={1: (400, 400, 500, 500)})
    assert not wc.overlapped(42)
