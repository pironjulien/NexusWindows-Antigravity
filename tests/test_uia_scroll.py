"""Défilement sémantique au point (recette commune du banc NexusWindows, banc du 21/10 23:42 : AGY refusait la
molette au point en WPF) et relecture d'effet des clics postés (faux succès WinForms du même banc). Hors ligne."""

from __future__ import annotations

from typing import Any

import computer_client
import pytest
import uia_scroll
from uia_scroll import Candidate


def test_plan_un_axe_sens_et_extremites_reelles() -> None:
    down = uia_scroll.plan(-1, 0)
    assert (down.vertical, down.forward, down.notches, down.amounts) == (True, True, 1, (2, 4))
    up = uia_scroll.plan(2, 0)
    assert (up.forward, up.notches, up.amounts) == (False, 2, (2, 1))
    right = uia_scroll.plan(0, 1)
    assert (right.vertical, right.forward, right.amounts) == (False, True, (4, 2))
    assert down.at_end(100) and not down.at_end(99.95)  # 99,95 % : il reste de quoi défiler
    assert up.at_end(0) and not up.at_end(0.05)
    with pytest.raises(uia_scroll.NotApplicable):
        uia_scroll.plan(-1, 1)
    with pytest.raises(uia_scroll.NotApplicable):
        uia_scroll.plan(0, 0)


def test_choix_du_conteneur_sous_le_point() -> None:
    parents = [-1, 0, 1, 0]
    outer = Candidate(1, 0, (0, 0, 100, 100))
    inner = Candidate(2, 1, (0, 0, 100, 100))  # même taille, imbriqué : l'intérieur l'emporte
    assert uia_scroll.choose([outer, inner], parents, 10, 10) is inner
    assert uia_scroll.choose([inner, outer], parents, 10, 10) is inner  # ordre indifférent
    small = Candidate(2, 1, (0, 0, 50, 50))
    assert uia_scroll.choose([outer, small], parents, 10, 10) is small  # le plus petit
    assert uia_scroll.choose([outer, small], parents, 80, 80) is outer  # point hors du petit
    sibling = Candidate(3, 0, (0, 0, 100, 100))  # même aire, non imbriqué : ambigu
    with pytest.raises(uia_scroll.NotApplicable):
        uia_scroll.choose([inner, sibling], parents, 10, 10)
    with pytest.raises(uia_scroll.NotApplicable):
        uia_scroll.choose([outer], parents, 500, 500)


class Pattern:
    def __init__(self, percent: float, moves: bool = True, raises: bool = False) -> None:
        self.CurrentVerticalScrollPercent = percent
        self.CurrentHorizontalScrollPercent = -1.0
        self.moves, self.raises, self.calls = moves, raises, []

    def Scroll(self, h: int, v: int) -> None:  # noqa: N802 - nom de l'API UIA
        self.calls.append((h, v))
        if self.raises:
            raise OSError("élément disparu")
        if self.moves:
            self.CurrentVerticalScrollPercent += 1


def run(pattern: Pattern, steps: Any) -> dict[str, Any]:
    ticks = iter(range(1000))
    return uia_scroll.scroll(pattern, steps, sleep=lambda _: None, clock=lambda: next(ticks) * 0.1)


def test_un_pas_par_cran_relu_sans_seconde_technique() -> None:
    moved = Pattern(50.0)
    out = run(moved, uia_scroll.plan(-2, 0))
    assert out["verified"] is True and moved.calls == [(2, 4), (2, 4)]
    still = Pattern(50.0, moves=False)
    assert run(still, uia_scroll.plan(-1, 0))["verified"] is None  # inchangée : incertain, pas d'échec
    end = Pattern(100.0)
    out = run(end, uia_scroll.plan(-1, 0))
    assert out["sent"] is False and end.calls == []  # extrémité réelle : rien n'est envoyé
    broken = Pattern(50.0, raises=True)
    out = run(broken, uia_scroll.plan(-1, 0))
    assert out["verified"] is None and out["sent"] is True  # interrompu après un pas : inconnu, jamais rejoué
    with pytest.raises(uia_scroll.NotApplicable):
        run(Pattern(-1.0), uia_scroll.plan(-1, 0))  # axe non défilable


def test_double_clic_poste_jamais_prouve_par_la_seule_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Banc du 21/10, 23:42 : WinForms, le premier clic sélectionnait l'élément (arbre changé) et le double clic
    passait pour vérifié alors que le labo ne l'avait pas reçu."""
    before = {"title": "T", "windows": (1,), "image": None, "rect": (0, 0, 10, 10), "tree": "a"}
    after = dict(before, tree="b")
    monkeypatch.setattr(computer_client, "window_fingerprint", lambda hwnd, with_tree=False: after)
    monkeypatch.setattr(computer_client, "_tree_digest", lambda hwnd: "b")
    assert computer_client._wait_window_effect(1, before, timeout=0)[0] is True  # clic simple : l'arbre suffit
    assert computer_client._wait_window_effect(1, before, timeout=0, structural_only=True)[0] is None
    opened = dict(before, windows=(1, 2))
    monkeypatch.setattr(computer_client, "window_fingerprint", lambda hwnd, with_tree=False: opened)
    assert computer_client._wait_window_effect(1, before, timeout=0, structural_only=True)[0] is True


def test_taille_prouvee_par_le_rectangle_pas_par_deux_captures() -> None:
    """Banc du 21/10, 23:42 : deux captures de tailles différentes d'une fenêtre recouverte ont validé un clic brut
    que le labo n'avait pas reçu."""
    from PIL import Image

    base = {"title": "T", "windows": (1,), "image": Image.new("L", (100, 80)), "rect": (0, 0, 100, 80)}
    other_capture = dict(base, image=Image.new("L", (90, 80)))
    assert computer_client._fingerprint_changed(base, other_capture) == ""
    resized = dict(base, rect=(0, 0, 120, 80), image=Image.new("L", (120, 80)))
    assert computer_client._fingerprint_changed(base, resized) == "taille de la fenêtre"
