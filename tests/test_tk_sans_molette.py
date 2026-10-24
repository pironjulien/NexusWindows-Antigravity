"""Tk en arrière-plan et défilement sans molette (3.0.2) : garde-fous de la relecture de Codex du 24/10."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import uia_scroll  # noqa: E402
import win32_controls as wc  # noqa: E402


def _tk_env(monkeypatch, sent: list, refuse: set[int] | None = None):
    refuse = refuse or set()
    monkeypatch.setattr(wc, "_thread_of", lambda h: 6)
    monkeypatch.setattr(wc, "_in_front", lambda thread: False)
    monkeypatch.setattr(wc, "send", lambda h, m, *a, **k: sent.append(("send", m)) or 0)

    def post(h, m, *a):
        if m in refuse:
            raise wc.MessageError("refusé")
        sent.append(("post", m))

    monkeypatch.setattr(wc, "post", post)

    class NoState:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    monkeypatch.setattr(wc, "_simulated_keys", NoState)
    monkeypatch.setattr(wc, "_wait_input_idle", lambda h, ms: None)
    monkeypatch.setattr(wc, "SIM_MODIFIERS_HOLD_S", 0.0)


def test_tk_keys_sets_focus_posts_keys_then_kills_focus(monkeypatch):
    sent: list = []
    _tk_env(monkeypatch, sent)
    assert wc.tk_keys(1, 0x4B, [0x11]) == "tk_focus_keys"
    assert sent == [("send", 0x0007), ("post", 0x0100), ("post", 0x0100), ("post", 0x0101), ("post", 0x0101),
                    ("post", 0x0008)]  # fmt: skip


def test_tk_keys_release_refused_is_partial_never_inapplicable(monkeypatch):
    """Appui accepté, relâchement refusé : issue inconnue (jamais rejouée au vrai clavier)."""
    sent: list = []
    _tk_env(monkeypatch, sent, refuse={0x0101})
    with pytest.raises(wc.PartialSendError):
        wc.tk_keys(1, 0x0D, [])


def test_tk_keys_kill_focus_refused_after_keys_is_partial(monkeypatch):
    sent: list = []
    _tk_env(monkeypatch, sent, refuse={0x0008})
    with pytest.raises(wc.PartialSendError, match="focus simulé non défait"):
        wc.tk_keys(1, 0x0D, [])


def test_held_press_watches_the_emergency_stop(monkeypatch):
    """STOP pendant l'attente de la pression : abandon, l'auxiliaire bloqué n'envoie rien de plus que son nettoyage."""
    release = threading.Event()
    sent: list = []
    monkeypatch.setattr(wc, "_thread_of", lambda h: 7)

    class NoState:
        def __init__(self, *a):
            pass

        def __enter__(self):
            release.wait(2)
            return self

        def __exit__(self, *exc):
            pass

    monkeypatch.setattr(wc, "_simulated_keys", NoState)
    monkeypatch.setattr(wc, "send", lambda h, m, *a, **k: sent.append(m) or 0)

    class Stop(Exception):
        pass

    def check():
        raise Stop

    with pytest.raises(Stop):
        wc._held_press(1, 0x01, 0x0201, 0x0202, 1, 0, check)
    release.set()
    for _ in range(100):
        if 7 not in wc._PENDING_PRESS:
            break
        threading.Event().wait(0.02)
    assert sent == []  # abandonnée avant d'envoyer : ni pression ni relâchement


def test_valid_rect_refuses_vanished_geometry():
    assert uia_scroll._valid_rect([0, 0, 0, 0]) is None
    assert uia_scroll._valid_rect([10, 280, 50, 20]) == (10, 280)
    assert uia_scroll._valid_rect(None) is None


def test_stop_just_before_a_fast_press_sends_nothing(monkeypatch):
    """STOP posé pendant la préparation d'un auxiliaire rapide (moins de 20 ms) : relu avant la pression, rien ne part."""
    sent: list = []
    monkeypatch.setattr(wc, "_thread_of", lambda h: 8)

    class NoState:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    monkeypatch.setattr(wc, "_simulated_keys", NoState)
    monkeypatch.setattr(wc, "send", lambda h, m, *a, **k: sent.append(m) or 0)

    class Stop(Exception):
        pass

    def check():
        raise Stop

    with pytest.raises(Stop):
        wc._held_press(1, 0x01, 0x0201, 0x0202, 1, 0, check)
    assert sent == []


def test_stop_between_the_two_clicks_of_a_double_click_is_marked_partial(monkeypatch):
    sent: list = []
    monkeypatch.setattr(wc, "deepest_child_at", lambda top, x, y: 5)
    monkeypatch.setattr(wc, "_thread_of", lambda h: 9)
    monkeypatch.setattr(wc, "_in_front", lambda thread: False)
    monkeypatch.setattr(wc, "is_window", lambda h: True)
    monkeypatch.setattr(wc, "_message_point", lambda h, x, y: (x, y))
    monkeypatch.setattr(wc, "send", lambda h, m, *a, **k: sent.append(m) or 0)
    monkeypatch.setattr(wc, "_held_press", lambda *a, **k: sent.extend([0x0201, 0x0202]))
    calls = {"n": 0}

    class Stop(Exception):
        pass

    def check():
        calls["n"] += 1
        if calls["n"] == 2:
            raise Stop

    with pytest.raises(Stop) as caught:
        wc.tk_click(1, 5, 5, count=2, check=check)
    assert getattr(caught.value, "partial_input", False) is True
    assert sent == [0x0200, 0x0201, 0x0202]


def test_stop_inside_the_second_press_keeps_the_first_click_trace(monkeypatch):
    """Check externe de la seconde pression passé, STOP levé à l'intérieur de son auxiliaire : partial_input conservé."""
    sent: list = []
    monkeypatch.setattr(wc, "deepest_child_at", lambda top, x, y: 5)
    monkeypatch.setattr(wc, "_thread_of", lambda h: 10)
    monkeypatch.setattr(wc, "_in_front", lambda thread: False)
    monkeypatch.setattr(wc, "is_window", lambda h: True)
    monkeypatch.setattr(wc, "_message_point", lambda h, x, y: (x, y))
    monkeypatch.setattr(wc, "send", lambda h, m, *a, **k: sent.append(m) or 0)

    class NoState:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    monkeypatch.setattr(wc, "_simulated_keys", NoState)

    class Stop(Exception):
        pass

    def check():
        if threading.current_thread().name == "agy-held-press" and 0x0201 in sent:
            raise Stop

    with pytest.raises(Stop) as caught:
        wc.tk_click(1, 5, 5, count=2, check=check)
    assert getattr(caught.value, "partial_input", False) is True
    assert sent == [0x0200, 0x0201, 0x0202]
