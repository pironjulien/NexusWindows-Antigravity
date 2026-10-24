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


# --- Défilement par la ligne suivante (Chromium sans DevTools), recette de NexusClaude du 23/10 ------------------------
# Une page Chromium recouverte jette la molette (RerouteMouseWheel : fenêtre d'un autre processus sous le point) et ses
# zones qui défilent n'ont pas de ScrollPattern. Comme un lecteur d'écran : la ligne cachée à 3 lignes par cran de la
# zone sous le point est amenée dans la vue (ScrollItem), preuve par l'écart ligne-zone relu (la page autour défile
# aussi). Une ligne n'appartient à une zone que si chaque conteneur entre elles la contient (sinon elle défile dans ce
# conteneur intérieur). Relu par Codex sur NexusClaude (feu vert c97a651).
LINES_PER_NOTCH = 3


def _valid_rect(raw: Any) -> tuple[int, int] | None:
    """(gauche, haut) d'un rectangle relu (gauche, haut, largeur, hauteur) de dimensions non nulles, sinon None : une
    géométrie disparue (0, 0, 0, 0) ne prouve aucun mouvement (relecture de Codex du 24/10)."""
    if not raw or len(raw) != 4:
        return None
    left, top, width, height = (int(round(v)) for v in raw)
    return (left, top) if width > 0 and height > 0 else None


def _lines_of(tree: Any, area: int, children: dict[int, list[int]]) -> list[int]:
    out: list[int] = []

    def visit(index: int, boxes: list[tuple[int, int, int, int]]) -> None:
        for child in children.get(index, []):
            rect = tree.nodes[child].rect
            if rect is None:
                continue
            if not children.get(child):
                if all(rect[1] >= box[1] - 1 and rect[3] <= box[3] + 1 for box in boxes):
                    out.append(child)
            else:
                visit(child, [*boxes, rect])

    visit(area, [])
    return out


def item_at(hwnd: int, x: int, y: int, delta_y: int, check: Callable[[], None]) -> dict[str, Any]:
    """Défilement vertical par la ligne cachée suivante de la zone sous le point écran (x, y) de `hwnd`."""
    import comtypes

    try:
        from . import uia_fast  # type: ignore[attr-defined]
    except ImportError:
        import uia_fast
    from comtypes.gen import UIAutomationClient as U

    if not delta_y:
        raise NotApplicable("défilement par ligne : vertical seulement, rien n'a été envoyé")
    down = delta_y < 0
    tree = uia_fast.reader().read_tree(hwnd, max_nodes=5000, time_budget=2.0)
    if tree.status != "ok":
        raise NotApplicable(f"arbre UI Automation incomplet ({tree.status}) : rien n'a été envoyé")
    children: dict[int, list[int]] = {}
    for index, node in enumerate(tree.nodes):
        children.setdefault(node.parent, []).append(index)

    def holds(index: int) -> bool:
        r = tree.nodes[index].rect
        return r is not None and r[0] <= x < r[2] and r[1] <= y < r[3]

    path: list[int] = []
    current = -1
    while True:  # descente vers le point : l'enfant qui a lui-même des enfants d'abord (volet vide de Chromium)
        covering = [c for c in children.get(current, []) if holds(c)]
        if not covering:
            break
        current = next((c for c in covering if children.get(c)), covering[0])
        path.append(current)
    hidden: list[int] = []
    area = -1
    box_rect: tuple[int, int, int, int] | None = None
    rects: dict[int, tuple[int, int, int, int]] = {}
    for candidate in reversed(path):
        rect = tree.nodes[candidate].rect
        lines = _lines_of(tree, candidate, children)
        rects = {i: r for i in lines if (r := tree.nodes[i].rect) is not None}
        if rect is None or len(rects) < 2:
            continue
        if down:
            hidden = sorted((i for i, r in rects.items() if r[3] > rect[3] + 1), key=lambda i: rects[i][1])
        else:
            hidden = sorted((i for i, r in rects.items() if r[1] < rect[1] - 1), key=lambda i: -rects[i][3])
        if hidden:
            area, box_rect = candidate, rect
            break
    if not hidden or box_rect is None:
        raise NotApplicable("aucune zone sous le point n'a de ligne cachée dans ce sens : rien n'a été envoyé")
    target = hidden[min(abs(delta_y) * LINES_PER_NOTCH, len(hidden)) - 1]
    line, box = tree.nodes[target], tree.nodes[area]
    before = rects[target][1] - box_rect[1]
    try:
        raw = line.element.GetCurrentPattern(U.UIA_ScrollItemPatternId)
        pattern = raw.QueryInterface(U.IUIAutomationScrollItemPattern) if raw else None
    except (comtypes.COMError, AttributeError, ValueError):
        pattern = None
    if pattern is None:
        raise NotApplicable("ligne sans ScrollItem : rien n'a été envoyé")
    check()  # arrêt d'urgence pendant la préparation : rien n'est invoqué
    try:
        pattern.ScrollIntoView()
    except comtypes.COMError as error:
        # Erreur APRÈS l'appel : il a pu agir ; issue inconnue, aucune autre technique par-dessus.
        return {"verified": None, "message": f"ScrollIntoView envoyé puis erreur ({error}) : vérifier l'image"}
    deadline = time.monotonic() + READ_BACK_S
    while time.monotonic() < deadline:
        time.sleep(0.05)
        try:
            now_line = _valid_rect(uia_fast.refresh(line.element).get("rect"))
            now_box = _valid_rect(uia_fast.refresh(box.element).get("rect"))
        except Exception:  # noqa: BLE001 - relecture impossible : on réessaie jusqu'à l'échéance
            continue
        if now_line and now_box and now_line[1] - now_box[1] != before:
            moved = before - (now_line[1] - now_box[1])
            return {"verified": True, "message": f"ligne « {line.name[:30]} » déplacée de {moved:+d} px dans sa zone"}
    return {"verified": None, "message": "ligne amenée dans la vue, zone non vue défiler en 1 s : vérifier l'image"}
