"""Défilement sémantique au point (UI Automation ScrollPattern), en arrière-plan : la molette au point d'une fenêtre
WPF (ou de toute interface qui n'accepte pas la molette postée) passe par le conteneur défilable sous le point.

Recette commune du banc NexusWindows (Codex : ComUia.ScrollContainerAt + ScrollChoice ; Claude :
act_pointer._scroll_container_at + _scroll_uia ; banc du 21/10, 23:42 : AGY répondait « impossible en arrière-plan
(WPF) » là où les deux autres réussissaient) :
- conteneur cherché dans le SOUS-ARBRE UI Automation de la fenêtre cible (jamais un test global au point : une autre
  fenêtre, même du même processus, peut la recouvrir), du processus de la fenêtre, visible, défilable sur l'axe
  demandé, dont le rectangle contient le point ;
- le plus petit ; à aire égale, celui qui descend de tous les autres ; deux d'aire égale non imbriqués : ambigu,
  refus ; arbre tronqué : refus (le bon descendant pouvait manquer) ;
- un petit pas UIA par cran (SmallIncrement / SmallDecrement) ; déjà à l'extrémité RÉELLE (0 ou 100 %) : rien n'est
  envoyé ; position relue jusqu'à 1 s : changée = vérifié, inchangée = incertain, jamais une seconde technique.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

SMALL_DECREMENT, NO_AMOUNT, SMALL_INCREMENT = 1, 2, 4
READ_BACK_S = 1.0


class NotApplicable(RuntimeError):
    """Pas de conteneur sûr sous le point : rien n'a été envoyé."""


@dataclass(frozen=True)
class Candidate:
    index: int  # rang dans l'arbre lu
    parent: int  # rang du parent (-1 : racine)
    rect: tuple[int, int, int, int]  # gauche, haut, droite, bas (écran)


@dataclass(frozen=True)
class Plan:
    vertical: bool
    forward: bool  # vers la fin (bas ou droite)
    notches: int

    @property
    def amounts(self) -> tuple[int, int]:
        """(horizontal, vertical) ScrollAmount d'un pas."""
        step = SMALL_INCREMENT if self.forward else SMALL_DECREMENT
        return (NO_AMOUNT, step) if self.vertical else (step, NO_AMOUNT)

    def at_end(self, percent: float) -> bool:
        """Extrémité RÉELLE seulement (99,9 % d'un long contenu laisse encore de quoi défiler)."""
        return percent >= 100 if self.forward else percent <= 0


def plan(delta_y: int, delta_x: int) -> Plan:
    """Crans d'AGY (delta_y > 0 = vers le haut, delta_x > 0 = vers la droite), un seul axe."""
    if (delta_y == 0) == (delta_x == 0):
        raise NotApplicable("défilement sémantique : un seul axe à la fois, rien n'a été envoyé")
    if delta_y:
        return Plan(True, delta_y < 0, min(abs(delta_y), 50))
    return Plan(False, delta_x > 0, min(abs(delta_x), 50))


def choose(candidates: Sequence[Candidate], parents: Sequence[int], x: int, y: int) -> Candidate:
    """Conteneur visé parmi ceux (déjà filtrés : même processus, visibles, défilables sur l'axe) dont le rectangle
    contient le point. ``parents`` : rang du parent de chaque nœud de l'arbre (ascendance)."""
    inside = [c for c in candidates if c.rect[0] <= x < c.rect[2] and c.rect[1] <= y < c.rect[3]]
    if not inside:
        raise NotApplicable("aucun conteneur défilable sur cet axe sous le point : rien n'a été envoyé")

    def area(c: Candidate) -> int:
        return (c.rect[2] - c.rect[0]) * (c.rect[3] - c.rect[1])

    def descends(child: int, ancestor: int) -> bool:
        current = parents[child] if 0 <= child < len(parents) else -1
        for _ in range(len(parents)):
            if current == ancestor:
                return True
            if current < 0:
                return False
            current = parents[current]
        return False

    smallest = min(area(c) for c in inside)
    tied = [c for c in inside if area(c) == smallest]
    deepest = [c for c in tied if all(o is c or descends(c.index, o.index) for o in tied)]
    if len(deepest) != 1:
        raise NotApplicable("conteneurs défilables ambigus sous le point : rien n'a été envoyé")
    return deepest[0]


def scroll(
    pattern: Any, steps: Plan, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic
) -> dict[str, Any]:
    """Un petit pas par cran sur le ScrollPattern, position relue. Rend {"verified": True|False|None, ...}."""

    def percent() -> float:
        return float(pattern.CurrentVerticalScrollPercent if steps.vertical else pattern.CurrentHorizontalScrollPercent)

    try:
        before = percent()
    except Exception as error:  # noqa: BLE001 - rien n'est encore parti
        raise NotApplicable(
            f"position de défilement illisible ({type(error).__name__}) : rien n'a été envoyé"
        ) from error
    if before < 0:
        raise NotApplicable("ce conteneur ne défile pas sur cet axe : rien n'a été envoyé")
    if steps.at_end(before):
        return {"verified": False, "sent": False, "before": before, "after": before,
                "message": f"déjà à l'extrémité ({before:g} %) : rien n'a été envoyé"}  # fmt: skip
    h, v = steps.amounts
    try:
        for _ in range(steps.notches):
            pattern.Scroll(h, v)
        after = before
        deadline = clock() + READ_BACK_S
        while clock() < deadline:
            after = percent()
            if after != before:
                break
            sleep(0.05)
    except Exception as error:  # noqa: BLE001 - un pas a pu partir : issue inconnue, jamais rejouée
        return {"verified": None, "sent": True, "before": before,
                "message": f"défilement interrompu ({type(error).__name__}) : issue inconnue, ne pas rejouer"}  # fmt: skip
    return {"verified": True if after != before else None, "sent": True, "before": before, "after": after}


def at_point(hwnd: int, x: int, y: int, delta_y: int, delta_x: int, pid: int) -> dict[str, Any]:
    """Défilement sémantique au point écran (x, y) de la fenêtre `hwnd` (processus `pid`)."""
    steps = plan(delta_y, delta_x)
    return scroll(container_at(hwnd, x, y, steps.vertical, pid), steps)


def position_reader(hwnd: int, x: int, y: int, vertical: bool, pid: int) -> Callable[[], float] | None:
    """Lecture de la position (pourcentage) du conteneur défilable visé sous le point, pour prouver une molette
    PHYSIQUE par son effet réel (banc commun du 22/10 : un titre de fenêtre changé passait pour un défilement) ; None si
    aucun conteneur lisible n'est prouvé sous le point."""
    try:
        pattern = container_at(hwnd, x, y, vertical, pid)
    except NotApplicable:
        return None

    def read() -> float:
        return float(pattern.CurrentVerticalScrollPercent if vertical else pattern.CurrentHorizontalScrollPercent)

    try:
        read()
    except Exception:  # noqa: BLE001 - illisible : pas de preuve possible
        return None
    return read


def container_at(hwnd: int, x: int, y: int, vertical: bool, pid: int) -> Any:
    """ScrollPattern du plus petit conteneur défilable sur l'axe sous le point (même processus, visible)."""
    import comtypes

    try:
        from . import uia_fast  # type: ignore[attr-defined]
    except ImportError:
        import uia_fast
    from comtypes.gen import UIAutomationClient as U

    tree = uia_fast.reader().read_tree(hwnd, max_nodes=5000, time_budget=2.0)
    if tree.status != "ok":
        raise NotApplicable(f"arbre UI Automation incomplet ({tree.status}) : rien n'a été envoyé")
    parents = [n.parent for n in tree.nodes]
    candidates: list[Candidate] = []
    patterns: dict[int, Any] = {}
    for index, node in enumerate(tree.nodes):
        props = node.props
        if not props.get("has_scroll") or props.get("offscreen") or int(props.get("pid") or 0) != pid:
            continue
        rect = node.rect
        if rect is None or not (rect[0] <= x < rect[2] and rect[1] <= y < rect[3]):
            continue
        try:
            raw = node.element.GetCurrentPattern(U.UIA_ScrollPatternId)
            pattern = raw.QueryInterface(U.IUIAutomationScrollPattern) if raw else None
        except (comtypes.COMError, AttributeError, ValueError):
            pattern = None
        if pattern is None:
            continue
        try:
            scrollable = pattern.CurrentVerticallyScrollable if vertical else pattern.CurrentHorizontallyScrollable
        except comtypes.COMError:
            continue
        if scrollable:
            candidates.append(Candidate(index, node.parent, rect))
            patterns[index] = pattern
    return patterns[choose(candidates, parents, x, y).index]
