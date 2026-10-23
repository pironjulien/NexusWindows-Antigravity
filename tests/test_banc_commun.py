"""Recettes du banc commun NexusWindows (21/10/2026) et défauts relevés par Codex en relecture croisée."""

from __future__ import annotations

import computer_client
import pytest
import win32_controls


def test_partial_send_after_first_message_is_reported_as_partial(monkeypatch):
    calls = []

    def fake_post(hwnd, msg, wparam, lparam):
        calls.append(msg)
        if len(calls) == 2:
            raise win32_controls.MessageError("refusé")

    monkeypatch.setattr(win32_controls, "post", fake_post)
    monkeypatch.setattr(win32_controls, "deepest_child_at", lambda top, x, y: 5)
    monkeypatch.setattr(win32_controls, "_to_client", lambda h, x, y: (x, y))
    with pytest.raises(win32_controls.PartialSendError):
        win32_controls.post_click(1, 10, 10)


def test_nothing_sent_stays_a_plain_message_error(monkeypatch):
    def refuse(hwnd, msg, wparam, lparam):
        raise win32_controls.MessageError("refusé")

    monkeypatch.setattr(win32_controls, "post", refuse)
    monkeypatch.setattr(win32_controls, "deepest_child_at", lambda top, x, y: 5)
    monkeypatch.setattr(win32_controls, "_to_client", lambda h, x, y: (x, y))
    with pytest.raises(win32_controls.MessageError) as caught:
        win32_controls.post_click(1, 10, 10)
    assert not isinstance(caught.value, win32_controls.PartialSendError)


def test_typing_without_activation_never_sends_a_line_break(monkeypatch):
    sent = []
    monkeypatch.setattr(win32_controls, "post", lambda *a: sent.append(a))
    with pytest.raises(win32_controls.MessageError):
        win32_controls.post_chars(1, "ab\ncd")
    assert sent == []


def test_alt_shortcut_is_refused_before_any_message(monkeypatch):
    sent = []
    monkeypatch.setattr(win32_controls, "post", lambda *a: sent.append(a))
    with pytest.raises(win32_controls.MessageError):
        win32_controls.post_shortcut(1, 0x73, [win32_controls.VK_MENU])
    assert sent == []


def test_partial_send_stops_the_technique_chain():
    calls = []

    def partial():
        calls.append("a")
        raise win32_controls.PartialSendError("envoi partiel")

    chain = [("A", partial), ("B", lambda: calls.append("b"))]
    out = computer_client._run_chain(chain, lambda _d: (True, ""), 0)
    assert calls == ["a"] and out["technique"] == "A" and out["verified"] is None


def test_posted_click_point_is_logical_for_a_dpi_virtualized_window(monkeypatch):
    """Banc commun du 22/10 : à 125 %, une fenêtre non adaptée au DPI lit le message posté en pixels logiques."""
    monkeypatch.setattr(win32_controls, "_to_client", lambda h, x, y: (125, 50))
    monkeypatch.setattr(win32_controls, "_GetWindowDpiAwarenessContext", lambda h: 0x11)
    monkeypatch.setattr(win32_controls, "_MonitorFromWindow", lambda h, f: 1)

    def monitor_dpi(monitor, kind, x, y):
        x._obj.value = 120
        return 0

    monkeypatch.setattr(win32_controls, "_GetDpiForMonitor", monitor_dpi)
    monkeypatch.setattr(win32_controls, "_GetAwarenessFromDpiAwarenessContext", lambda c: 0)  # non adaptée
    assert win32_controls._message_point(1, 0, 0) == (100, 40)
    monkeypatch.setattr(win32_controls, "_GetAwarenessFromDpiAwarenessContext", lambda c: 2)  # par moniteur
    assert win32_controls._message_point(1, 0, 0) == (125, 50)
    monkeypatch.setattr(win32_controls, "_GetAwarenessFromDpiAwarenessContext", lambda c: -1)  # contexte illisible
    assert win32_controls._message_point(1, 0, 0) == (125, 50)
