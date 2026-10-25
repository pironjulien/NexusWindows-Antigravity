"""Lecture UI Automation d'une fenêtre en UN SEUL aller-retour inter-processus.

Avant : un GetChildren() puis un GetValuePattern() (et une lecture de propriété par attribut) par nœud, soit des
centaines d'allers-retours vers l'application cible. Ici : une IUIAutomationCacheRequest (propriétés utiles et
disponibilité des motifs, TreeScope_Subtree, vue « contrôle ») et un seul ElementFromHandleBuildCache ; tout le reste
(enfants, propriétés) se lit dans le cache local, sans IPC (inspiré de NexusWindows/claude uia.py).

Réglages :
- AutoSetFocus = False (IUIAutomation2) : par défaut UIA donne le focus à l'élément avant chaque motif (Invoke,
  Toggle…), ce qui active la fenêtre cible. Les éléments lus ici portent ce réglage dans les actions qui suivent.
- TransactionTimeout borné par le budget de temps : une application figée ou un arbre géant ne bloque pas 20 s ;
  le délai dépassé est signalé (status "failed"), jamais rendu comme une fenêtre vide.
- AutomationElementMode_Full : les éléments restent vivants pour agir ensuite par leur index Set-of-Marks
  (AutomationElementMode_None ne permet aucun motif d'action).
- Borne de nœuds : au-delà de max_nodes, l'arbre est coupé et le résultat le dit (status "truncated").
- Sous-arbres à ne pas lire (`skip_subtrees`) : une liste déroulante Win32/WinForms OUVERTE fait échouer toute
  lecture de sous-arbre qui la contient, après ~8 s malgré le délai (mesuré le 16/10 : look de 13 s, éléments perdus).
  Les fenêtres qui la contiennent sont alors lues niveau par niveau, elle seule sans ses enfants, le reste d'un bloc.
"""

from __future__ import annotations

import ctypes
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import comtypes
import comtypes.client

comtypes.client.GetModule("UIAutomationCore.dll")
from comtypes.gen import UIAutomationClient as U  # noqa: E402

TreeScope_Element, TreeScope_Children, TreeScope_Subtree = 1, 2, 7
AutomationElementMode_Full = 1

CONTROL_TYPES: dict[int, str] = {
    getattr(U, name): name[4:-13] for name in dir(U) if name.startswith("UIA_") and name.endswith("ControlTypeId")
}

PROPS: dict[str, int] = {
    "control_type": U.UIA_ControlTypePropertyId,
    "name": U.UIA_NamePropertyId,
    "rect": U.UIA_BoundingRectanglePropertyId,
    "hwnd": U.UIA_NativeWindowHandlePropertyId,
    "class_name": U.UIA_ClassNamePropertyId,
    "automation_id": U.UIA_AutomationIdPropertyId,
    "framework": U.UIA_FrameworkIdPropertyId,
    "enabled": U.UIA_IsEnabledPropertyId,
    "offscreen": U.UIA_IsOffscreenPropertyId,
    "password": U.UIA_IsPasswordPropertyId,
    "value": U.UIA_ValueValuePropertyId,
    "readonly": U.UIA_ValueIsReadOnlyPropertyId,
    "toggle": U.UIA_ToggleToggleStatePropertyId,
    "selected": U.UIA_SelectionItemIsSelectedPropertyId,
    "expand": U.UIA_ExpandCollapseExpandCollapseStatePropertyId,
    "has_invoke": U.UIA_IsInvokePatternAvailablePropertyId,
    "has_value": U.UIA_IsValuePatternAvailablePropertyId,
    "has_toggle": U.UIA_IsTogglePatternAvailablePropertyId,
    "has_selection_item": U.UIA_IsSelectionItemPatternAvailablePropertyId,
    "has_expand": U.UIA_IsExpandCollapsePatternAvailablePropertyId,
    "has_scroll": U.UIA_IsScrollPatternAvailablePropertyId,
    "has_scroll_item": U.UIA_IsScrollItemPatternAvailablePropertyId,
    "runtime_id": U.UIA_RuntimeIdPropertyId,
    "pid": U.UIA_ProcessIdPropertyId,
    "access_key": U.UIA_AccessKeyPropertyId,  # « Alt+E » de « &Envoyer » : ce qu'un raccourci Alt déclencherait
    "focus": U.UIA_HasKeyboardFocusPropertyId,  # élément au focus : ce qu'Entrée ou Espace activeraient
}

FRAMEWORKS = {"win32": "Win32", "winform": "WinForms", "wpf": "WPF", "xaml": "XAML", "directui": "DirectUI"}


class UIAReadError(RuntimeError):
    pass


@dataclass
class Node:
    element: Any
    props: dict[str, Any]
    depth: int
    parent: int  # index du parent dans Tree.nodes (-1 : racine)
    host_hwnd: int  # fenêtre Win32 la plus proche (l'élément lui-même ou un ancêtre)

    @property
    def control_type(self) -> str:
        return CONTROL_TYPES.get(int(self.props.get("control_type") or 0), "Unknown")

    @property
    def name(self) -> str:
        return " ".join(str(self.props.get("name") or "").split())

    @property
    def rect(self) -> tuple[int, int, int, int] | None:
        """(gauche, haut, droite, bas) écran, ou None si vide."""
        r = self.props.get("rect")
        if not r or len(r) != 4:
            return None
        left, top, width, height = (int(round(v)) for v in r)
        if width <= 0 or height <= 0:
            return None
        return (left, top, left + width, top + height)

    @property
    def framework(self) -> str:
        raw = str(self.props.get("framework") or "").lower()
        return FRAMEWORKS.get(raw, raw.capitalize() if raw else "")


@dataclass
class Tree:
    nodes: list[Node] = field(default_factory=list)
    status: str = "ok"  # ok | truncated | failed
    reason: str = ""
    duration_ms: float = 0.0
    method: str = "uia_cache_subtree"


def _contains(ancestor: int, hwnd: int) -> bool:
    """La fenêtre `hwnd` est-elle `ancestor` ou l'une de ses descendantes ?"""
    return bool(ancestor) and (ancestor == hwnd or bool(ctypes.windll.user32.IsChild(ancestor, hwnd)))


def _variant(value: Any) -> Any:
    """Valeurs sentinelles UIA (« non supporté », « mixte » : objets COM) → None."""
    if value is None or hasattr(value, "QueryInterface"):
        return None
    return value


class Reader:
    """Client UIA dédié à un fil COM (créé et utilisé sur le même fil)."""

    def __init__(self) -> None:
        try:
            self.uia = comtypes.client.CreateObject(U.CUIAutomation8, interface=U.IUIAutomation2)
            self.uia.AutoSetFocus = False
            self.uia.ConnectionTimeout = 2000
            self.auto_set_focus = False
        except (OSError, comtypes.COMError, AttributeError):
            self.uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
            self.auto_set_focus = True  # Windows trop ancien : réglage indisponible
        self.cache_tree = self._make_cache(TreeScope_Subtree)
        self.cache_one = self._make_cache(TreeScope_Element)
        self.cache_level = self._make_cache(TreeScope_Element | TreeScope_Children)

    def _make_cache(self, scope: int):
        request = self.uia.CreateCacheRequest()
        for pid in PROPS.values():
            request.AddProperty(pid)
        request.TreeScope = scope
        request.TreeFilter = self.uia.ControlViewCondition
        request.AutomationElementMode = AutomationElementMode_Full
        return request

    def _set_timeout(self, seconds: float) -> None:
        if not self.auto_set_focus:  # IUIAutomation2 disponible
            try:
                setattr(self.uia, "TransactionTimeout", max(200, int(seconds * 1000)))  # IUIAutomation2 seulement
            except (comtypes.COMError, AttributeError):
                pass

    def props(self, element) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, pid in PROPS.items():
            try:
                value = _variant(element.GetCachedPropertyValue(pid))
            except (comtypes.COMError, ValueError):
                continue
            if value is not None and value != "":
                out[key] = value
        if out.get("password"):
            out.pop("value", None)  # jamais la valeur d'un champ mot de passe
        return out

    def read_tree(
        self, hwnd: int, max_nodes: int = 3000, time_budget: float = 2.0, skip_subtrees: Iterable[int] = ()
    ) -> Tree:
        """Arbre « vue contrôle » de la fenêtre en un appel. Jamais d'arbre vide silencieux : échec et coupure
        sont rapportés dans status/reason. skip_subtrees : fenêtres lues sans leurs enfants (voir l'en-tête)."""
        skip = {int(h) for h in skip_subtrees if h}
        if skip:
            return self._read_tree_skipping(hwnd, max_nodes, time_budget, skip)
        tree = Tree()
        t0 = time.perf_counter()
        self._set_timeout(time_budget)
        try:
            root = self.uia.ElementFromHandleBuildCache(hwnd, self.cache_tree)
        except comtypes.COMError as error:
            tree.status = "failed"
            tree.reason = f"Arbre UI Automation illisible (délai de {time_budget:g} s ou application figée) : {error}"
            tree.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            return tree
        if not root:
            tree.status = "failed"
            tree.reason = "UI Automation ne voit pas cette fenêtre."
            tree.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            return tree

        stack: list[tuple[Any, int, int, int]] = [(root, 0, -1, 0)]
        while stack:
            if len(tree.nodes) >= max_nodes:
                tree.status = "truncated"
                tree.reason = f"Arbre coupé à {max_nodes} nœuds : des éléments manquent (préciser query)."
                break
            element, depth, parent, parent_host = stack.pop()
            props = self.props(element)
            own = int(props.get("hwnd") or 0)
            node = Node(element, props, depth, parent, own or parent_host)
            index = len(tree.nodes)
            tree.nodes.append(node)
            try:
                kids = element.GetCachedChildren()
            except (comtypes.COMError, ValueError):
                kids = None
            if kids:  # pointeur NULL quand l'élément n'a pas d'enfant
                # ordre du document conservé : enfants empilés à l'envers
                for i in range(kids.Length - 1, -1, -1):
                    stack.append((kids.GetElement(i), depth + 1, index, node.host_hwnd))
        tree.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        return tree

    def _read_tree_skipping(self, hwnd: int, max_nodes: int, time_budget: float, skip: set[int]) -> Tree:
        """Lecture qui contourne les sous-arbres `skip` : un élément dont la fenêtre contient une fenêtre à éviter
        est lu avec ses seuls enfants (un aller-retour), les autres d'un bloc avec tout leur sous-arbre ; une fenêtre
        à éviter est gardée sans ses enfants. Même format et mêmes garanties que read_tree."""
        tree = Tree(method="uia_cache_partial")
        t0 = time.perf_counter()
        self._set_timeout(time_budget)

        def risky(own: int) -> bool:
            return bool(own) and any(_contains(own, h) for h in skip)

        try:
            root = self.uia.ElementFromHandleBuildCache(hwnd, self.cache_level)
        except comtypes.COMError as error:
            tree.status = "failed"
            tree.reason = f"Arbre UI Automation illisible (délai de {time_budget:g} s ou application figée) : {error}"
            tree.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            return tree
        if not root:
            tree.status = "failed"
            tree.reason = "UI Automation ne voit pas cette fenêtre."
            tree.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            return tree
        # Mode d'un élément : "full" (tout son sous-arbre en cache), "level" (ses enfants seuls en cache), "bare"
        # (rien sous lui en cache : à relire).
        stack: list[tuple[Any, int, int, int, str]] = [(root, 0, -1, 0, "level")]
        while stack:
            if len(tree.nodes) >= max_nodes:
                tree.status = "truncated"
                tree.reason = f"Arbre coupé à {max_nodes} nœuds : des éléments manquent (préciser query)."
                break
            if time.perf_counter() - t0 > time_budget:
                tree.status = "truncated"
                tree.reason = f"Budget de lecture de {time_budget:g} s dépassé : des éléments manquent."
                break
            element, depth, parent, parent_host, mode = stack.pop()
            props = self.props(element)
            own = int(props.get("hwnd") or 0)
            node = Node(element, props, depth, parent, own or parent_host)
            index = len(tree.nodes)
            tree.nodes.append(node)
            if mode == "bare":
                if own in skip:
                    continue  # liste ouverte : l'élément seul, jamais son sous-arbre
                mode = "level" if risky(own) else "full"
                try:
                    element = element.BuildUpdatedCache(self.cache_level if mode == "level" else self.cache_tree)
                except comtypes.COMError:
                    continue
            try:
                kids = element.GetCachedChildren()
            except (comtypes.COMError, ValueError):
                kids = None
            if kids:
                child_mode = "full" if mode == "full" else "bare"
                for i in range(kids.Length - 1, -1, -1):
                    stack.append((kids.GetElement(i), depth + 1, index, node.host_hwnd, child_mode))
        tree.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        return tree

    def refresh(self, element) -> dict[str, Any]:
        """Propriétés actuelles d'un élément (un aller-retour). Lève UIAReadError si l'élément a disparu."""
        try:
            fresh = element.BuildUpdatedCache(self.cache_one)
        except comtypes.COMError as error:
            raise UIAReadError(f"Élément disparu : {error}") from error
        return self.props(fresh)


_local = threading.local()


def reader() -> Reader:
    """Client du fil courant (COM initialisé au besoin, appartement existant conservé)."""
    current = getattr(_local, "reader", None)
    if current is None:
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:  # RPC_E_CHANGED_MODE : appartement déjà choisi pour ce fil
            pass
        current = Reader()
        _local.reader = current
    return current


def raw_element(obj: Any) -> Any:
    """Pointeur IUIAutomationElement d'un objet uiautomation.Control ou d'un pointeur brut."""
    return getattr(obj, "Element", None) or obj


def refresh(obj: Any) -> dict[str, Any]:
    return reader().refresh(raw_element(obj))


def runtime_id(props: dict[str, Any]) -> tuple[int, ...] | None:
    """Identifiant d'exécution UIA (stable tant que l'élément vit) : dédoublonne un même élément vu deux fois (WPF
    montre une option sous la liste ET dans sa surgissante)."""
    value = props.get("runtime_id")
    if not value:
        return None
    try:
        return tuple(int(v) for v in value)
    except (TypeError, ValueError):
        return None


def control_type_name(type_id: int | None) -> str:
    return CONTROL_TYPES.get(int(type_id or 0), "Unknown")
