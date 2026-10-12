#!/usr/bin/env python3
"""
NexusAGY Browser Bridge - Native MCP Server (Model Context Protocol)
Exposes Chrome DevTools Protocol automation as native API tools for Antigravity.
"""

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

try:
    from . import computer_client, spotlight_launcher
    from .bridge_client import call_bridge
except ImportError:
    import computer_client
    import spotlight_launcher
    from bridge_client import call_bridge


browser_mcp = FastMCP(
    name="nexus-browser",
    instructions="Native Chrome browser automation bridge controlling tabs, CDP, Set-of-Marks, Playwright selectors, and Side Panel.",
)

computer_mcp = FastMCP(
    name="nexus-computer",
    instructions="SOTA Windows OS Computer Use & Spotlight Companion bridge (UI Automation 3.0, Set-of-Marks, SendInput, Spotlight launcher).",
)

combined_mcp = FastMCP(
    name="nexus-browser",
    instructions="Native browser & Windows desktop automation bridge controlling Chrome tabs, CDP, Set-of-Mark, Playwright selectors, and OS-level Computer Use.",
)

mcp = combined_mcp


def _register_browser_tool(func: Any) -> Any:
    browser_mcp.add_tool(func)
    combined_mcp.add_tool(func)
    return func


def _register_computer_tool(func: Any) -> Any:
    computer_mcp.add_tool(func)
    combined_mcp.add_tool(func)
    return func


def _call_bridge(action: str, params: dict | None = None, timeout: float = 20.0) -> str:
    try:
        data = call_bridge(action, params, timeout)
        output = (params or {}).get("output")
        if output and action in {"screenshot", "pdf", "vision-inspect"}:
            key = {"screenshot": "dataUrl", "pdf": "pdfBase64", "vision-inspect": "screenshotDataUrl"}[action]
            encoded = data[key]
            if key != "pdfBase64":
                encoded = encoded.split(",", 1)[1]
            content = base64.b64decode(encoded, validate=True)
            destination = Path(output).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                os.replace(temporary, destination)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            data = {**data, "output_path": str(destination)}
            data.pop(key)
        return json.dumps({"status": "success", "data": data}, ensure_ascii=False, indent=2)
    except (OSError, RuntimeError, ValueError, KeyError, IndexError) as error:
        return json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False)


@_register_browser_tool
def browser_list_tabs() -> str:
    """Liste tous les onglets ouverts dans Google Chrome avec leurs identifiants, titres et URLs."""
    return _call_bridge("list-tabs")


@_register_browser_tool
def browser_active_tab() -> str:
    """Récupère les métadonnées de l'onglet actuellement actif dans Google Chrome."""
    return _call_bridge("active-tab")


@_register_browser_tool
def browser_select_tab(tab_id: int) -> str:
    """Active et met au premier plan l'onglet spécifié par son ID."""
    return _call_bridge("select-tab", {"tab_id": tab_id})


@_register_browser_tool
def browser_new_tab(
    url: str | None = None,
    background: bool = True,
    group: str | None = "Antigravity",
) -> str:
    """Ouvre un nouvel onglet dans Google Chrome vers l'URL spécifiée (ou about:blank).

    Par défaut, s'ouvre en arrière-plan (background=True) sans voler le focus de l'utilisateur,
    et s'associe automatiquement au groupe d'onglets dédié 'Antigravity'.
    """
    params: dict = {
        "url": url or "about:blank",
        "background": background,
        "active": not background,
    }
    if group:
        params["group"] = group
    return _call_bridge("create-tab", params)


@_register_browser_tool
def browser_group_tabs(
    tab_ids: list[int] | None = None,
    title: str = "Antigravity",
    color: str = "purple",
    collapsed: bool = False,
) -> str:
    """Regroupe un ou plusieurs onglets Chrome dans un groupe d'onglets nommé et coloré.

    Permet d'isoler visuellement les onglets de travail de l'agent sans encombrer les onglets de l'utilisateur.
    Couleurs supportées : 'grey', 'blue', 'red', 'yellow', 'green', 'pink', 'purple', 'cyan', 'orange'.
    """
    params: dict = {
        "title": title,
        "color": color,
        "collapsed": collapsed,
    }
    if tab_ids:
        params["tabIds"] = tab_ids
    return _call_bridge("group-tabs", params)


@_register_browser_tool
def browser_close_tab(tab_id: int | None = None) -> str:
    """Ferme l'onglet spécifié par son ID (ou l'onglet actif)."""
    return _call_bridge("close-tab", {"tab_id": tab_id})


@_register_browser_tool
def browser_reload(tab_id: int | None = None, bypass_cache: bool = False) -> str:
    """Recharge la page de l'onglet actif ou cible."""
    return _call_bridge("reload", {"tab_id": tab_id, "bypassCache": bypass_cache})


@_register_browser_tool
def browser_navigate(url: str, tab_id: int | None = None) -> str:
    """Navigue vers l'URL spécifiée dans l'onglet actif ou cible."""
    return _call_bridge("navigate", {"url": url, "tab_id": tab_id})


@_register_browser_tool
def browser_wait_load(timeout_ms: int = 10000, tab_id: int | None = None) -> str:
    """Attend la stabilisation et l'état complet du document (document.readyState === 'complete')."""
    return _call_bridge("wait-load", {"timeout": timeout_ms, "tab_id": tab_id})


@_register_browser_tool
def browser_hover(
    selector: str | None = None,
    text: str | None = None,
    mark: int | None = None,
    timeout_ms: int = 1200,
    tab_id: int | None = None,
) -> str:
    """Survole un élément (hover) via déplacement curseur CDP et événements DOM (mouseenter/mouseover).

    Révèle menus déroulants, sous-menus, tooltips et popovers masqués.
    Ciblage au choix :
    - mark: Numéro de badge issu de browser_interactive_map ou vision_inspect (ex: mark=5)
    - selector: Sélecteur CSS ou hash de marqueur (ex: "#5", ".dropdown-trigger")
    - text: Texte visible de l'élément (ex: "Options")
    """
    params: dict = {"tab_id": tab_id, "timeoutMs": timeout_ms}
    if mark is not None:
        params["selector"] = f"#{mark}"
    elif selector:
        params["selector"] = selector
    if text:
        params["text"] = text
    return _call_bridge("hover", params)


@_register_browser_tool
def browser_click(
    selector: str | None = None,
    text: str | None = None,
    mark: int | None = None,
    index: int = 0,
    timeout_ms: int = 1200,
    tab_id: int | None = None,
) -> str:
    """Clique sur un élément avec auto-wait adaptatif Playwright-grade et pulsation visuelle laser.

    Traverse automatiquement le Shadow DOM (Web Components, Lit).
    Ciblage au choix :
    - mark: Numéro direct du marqueur issu de browser_interactive_map (ex: mark=2)
    - selector: Sélecteur CSS standard ou marqueur (ex: "#2", "button.primary")
    - text: Recherche par libellé textuel visible (ex: "Soumettre")
    - index: Index si plusieurs éléments correspondent au même sélecteur (0 par défaut)
    """
    params: dict = {"tab_id": tab_id, "index": index, "timeoutMs": timeout_ms}
    if mark is not None:
        params["mark"] = mark
    if selector:
        params["selector"] = selector
    if text:
        params["text"] = text
    return _call_bridge("click", params)


@_register_browser_tool
def browser_semantic_click(role: str, name: str | None = None, tab_id: int | None = None) -> str:
    """Clique sur un élément de façon robuste style Playwright via son rôle ARIA (button, link, tab) et son nom accessible."""
    return _call_bridge("semantic-click", {"role": role, "name": name, "tab_id": tab_id})


@_register_browser_tool
def browser_fill(
    selector: str | None = None,
    value: str = "",
    mark: int | None = None,
    timeout_ms: int = 1200,
    tab_id: int | None = None,
) -> str:
    """Remplit un champ de texte, textarea ou élément contenteditable (React 18/19, Gmail, Notion).

    Déclenche les setters de prototypes natifs pour une prise en compte immédiate par les frameworks réactifs.
    Traverse automatiquement le Shadow DOM.
    Ciblage au choix :
    - mark: Numéro du marqueur issu de browser_interactive_map (ex: mark=3)
    - selector: Sélecteur CSS standard ou marqueur (ex: "#3", "input[type='email']")
    - Omission du sélecteur : remplit le champ actuellement actif (document.activeElement)
    """
    params: dict = {"value": value, "tab_id": tab_id, "timeoutMs": timeout_ms}
    if mark is not None:
        params["mark"] = mark
    if selector:
        params["selector"] = selector
    return _call_bridge("fill", params)


@_register_browser_tool
def browser_semantic_fill(label: str, value: str, tab_id: int | None = None) -> str:
    """Remplit un champ de formulaire de façon robuste style Playwright ciblé par son étiquette (label) ou son placeholder."""
    return _call_bridge("semantic-fill", {"label": label, "value": value, "tab_id": tab_id})


@_register_browser_tool
def browser_select_option(
    selector: str, text: str | None = None, value: str | None = None, tab_id: int | None = None
) -> str:
    """Sélectionne une option dans un menu déroulant HTML <select> avec déclenchement des événements input et change."""
    return _call_bridge("select-option", {"selector": selector, "text": text, "value": value, "tab_id": tab_id})


@_register_browser_tool
def browser_press_key(key: str, tab_id: int | None = None) -> str:
    """Presse une touche spéciale via CDP (Enter, Escape, Tab, Backspace, ArrowDown, ArrowUp)."""
    return _call_bridge("press-key", {"key": key, "tab_id": tab_id})


@_register_browser_tool
def browser_upload(files: list[str], selector: str | None = None, tab_id: int | None = None) -> str:
    """Téléverse un ou plusieurs fichiers (ex: .aab, .apk, .zip) sans ouvrir ni bloquer sur la boîte de dialogue native Windows."""
    return _call_bridge("upload", {"files": files, "selector": selector, "tab_id": tab_id})


@_register_browser_tool
def browser_vision_inspect(output_path: str | None = None, tab_id: int | None = None) -> str:
    """Injecte des badges néon Set-of-Mark (SoM) et capture la vue pour analyse spatiale multimodale.

    Retourne la liste complète des éléments détectés avec coordonnées Gemini box_2d [ymin, xmin, ymax, xmax] sur base [0-1000].
    RÈGLE SOTA ANTI-CRASH 400 : Ne jamais appeler `view_file` sur l'image PNG brute générée si > 500 Ko.
    Exploiter directement la liste structurée des marqueurs JSON ou compresser l'image avant affichage.
    """
    return _call_bridge("vision-inspect", {"output": output_path, "tab_id": tab_id})


@_register_browser_tool
def browser_click_mark(mark: int, tab_id: int | None = None) -> str:
    """Clique au centre géométrique exact du badge Set-of-Mark (SoM) identifié par la vision Gemini."""
    return _call_bridge("click-mark", {"mark": mark, "tab_id": tab_id})


@_register_browser_tool
def browser_check_handoff(tab_id: int | None = None) -> str:
    """Détecte proactivement la présence d'un écran 2FA (SMS, Google Authenticator), CAPTCHA ou Cloudflare Turnstile."""
    return _call_bridge("check-handoff", {"tab_id": tab_id})


@_register_browser_tool
def browser_content(mode: str = "interactive", tab_id: int | None = None) -> str:
    """Extrait le contenu de la page web. Modes disponibles : interactive (éléments cliquables/inputs), text (texte brut), html (DOM)."""
    return _call_bridge("content", {"mode": mode, "tab_id": tab_id})


@_register_browser_tool
def browser_axtree(tab_id: int | None = None) -> str:
    """Extrait l'arbre d'accessibilité sémantique complet (AXTree) de la page via CDP."""
    return _call_bridge("axtree", {"tab_id": tab_id})


@_register_browser_tool
def browser_logs(tab_id: int | None = None) -> str:
    """Récupère le flux d'erreurs et messages de la console DevTools de l'onglet actif."""
    return _call_bridge("logs", {"tab_id": tab_id})


@_register_browser_tool
def browser_screenshot(
    output_path: str | None = None,
    selector: str | None = None,
    mark: int | None = None,
    tab_id: int | None = None,
) -> str:
    """Capture une capture d'écran de l'onglet actif ou d'un élément précis rogné au pixel près (PNG).

    RÈGLE ANTI-CRASH 400 : Ne pas ouvrir avec view_file si le fichier dépasse 500 Ko.
    Ciblage :
    - selector: Sélecteur CSS de l'élément à rogner (ex: "#dashboard-card")
    - mark: Numéro de marqueur à rogner (ex: mark=4)
    - output_path: Chemin absolu où sauvegarder le PNG (optionnel, renvoie dataUrl si omis)
    """
    params: dict = {"output": output_path, "tab_id": tab_id}
    if mark is not None:
        params["selector"] = f"#{mark}"
    elif selector:
        params["selector"] = selector
    return _call_bridge("screenshot", params)


@_register_browser_tool
def browser_pdf(output_path: str, tab_id: int | None = None) -> str:
    """Génère un export PDF vectoriel A4 haute fidélité de la page active."""
    return _call_bridge("pdf", {"output": output_path, "tab_id": tab_id})


@_register_browser_tool
def browser_eval(script: str, tab_id: int | None = None) -> str:
    """Exécute une expression JavaScript dans le contexte de la page web et renvoie le résultat."""
    return _call_bridge("eval", {"script": script, "tab_id": tab_id})


@_register_browser_tool
def browser_scroll(direction: str = "down", y: int = 400, tab_id: int | None = None) -> str:
    """Fait défiler la page web de y pixels vers le bas (down) ou le haut (up)."""
    return _call_bridge("scroll", {"direction": direction, "y": y, "tab_id": tab_id})


@_register_browser_tool
def browser_wait_network_idle(idle_ms: int = 300, timeout_ms: int = 8000, tab_id: int | None = None) -> str:
    """Attend la stabilisation des flux réseau (0 requête Fetch/XHR active pendant idle_ms).

    CRITIQUE : Appeler après un clic, soumission ou navigation sur toute Single Page App
    (React, Angular, Vue, consoles Google Cloud / Play Store) avant d'inspecter le DOM.
    """
    return _call_bridge("wait-network-idle", {"idleMs": idle_ms, "timeoutMs": timeout_ms, "tab_id": tab_id})


@_register_browser_tool
def browser_get_cookies(urls: list[str] | None = None, tab_id: int | None = None) -> str:
    """Récupère les cookies de session et de domaine réels via CDP Network.getCookies pour réutilisation API."""
    params: dict = {"tab_id": tab_id}
    if urls:
        params["urls"] = urls
    return _call_bridge("get-cookies", params)


@_register_browser_tool
def browser_cdp_send(method: str, params: dict | None = None, tab_id: int | None = None) -> str:
    """Exécute une commande brute du Chrome DevTools Protocol (CDP) sur l'onglet spécifié."""
    return _call_bridge("cdp-send", {"method": method, "commandParams": params or {}, "tab_id": tab_id})


@_register_browser_tool
def browser_interactive_map(viewport_only: bool = True, max_elements: int = 60, tab_id: int | None = None) -> str:
    """Extrait une carte condensée SOTA des éléments interactifs visibles ([#1] bouton, [#2] input...).

    OUTIL SOTA RECOMMANDÉ : Économise 85 % à 95 % de tokens par rapport au HTML ou AXTree brut.
    Fournit pour chaque élément visible : son numéro mark, tag, rôle ARIA, label textuel,
    sélecteur CSS optimisé et coordonnées spatiales Gemini box_2d [ymin, xmin, ymax, xmax] (0-1000).
    Permet d'enchaîner directement des clics et remplissages avec browser_click(mark=N) ou browser_fill(mark=N, value=...).
    """
    return _call_bridge(
        "interactive-map", {"viewportOnly": viewport_only, "maxElements": max_elements, "tab_id": tab_id}
    )


@_register_browser_tool
def browser_drag_and_drop(
    from_selector: str | None = None,
    to_selector: str | None = None,
    from_mark: int | None = None,
    to_mark: int | None = None,
    from_coordinates: dict | None = None,
    to_coordinates: dict | None = None,
    steps: int = 12,
    tab_id: int | None = None,
) -> str:
    """Effectue un glisser-déposer fluide (drag & drop) ou manipulation de curseur/slider entre deux cibles (sélecteurs, numéros de marqueurs ou coordonnées {x, y})."""
    return _call_bridge(
        "drag-and-drop",
        {
            "from_selector": from_selector,
            "to_selector": to_selector,
            "from_mark": from_mark,
            "to_mark": to_mark,
            "from_coordinates": from_coordinates,
            "to_coordinates": to_coordinates,
            "steps": steps,
            "tab_id": tab_id,
        },
    )


# =============================================================================
# SOTA Windows OS Computer Use Tools
# =============================================================================
def _format_computer_result(func: Any, *args: Any, **kwargs: Any) -> str:
    try:
        data = func(*args, **kwargs) if callable(func) else func
        return json.dumps({"status": "success", "data": data}, ensure_ascii=False, indent=2)
    except Exception as error:
        return json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False)


@_register_computer_tool
def computer_list_windows(visible_only: bool = True) -> str:
    """Liste toutes les fenêtres ouvertes du bureau Windows avec HWND, titre, PID, nom du processus exécutable, coordonnées et état actif/arrière-plan."""
    return _format_computer_result(computer_client.list_windows, visible_only=visible_only)


@_register_computer_tool
def computer_list_apps() -> str:
    """Liste les applications graphiques en cours d'exécution groupées par processus (ex. Chrome, Bloc-notes, VS Code, Explorer)."""
    return _format_computer_result(computer_client.list_apps)


@_register_computer_tool
def computer_focus_window(
    hwnd: int | None = None,
    title: str | None = None,
    process_name: str | None = None,
) -> str:
    """Met la fenêtre cible au premier plan, la restaure si elle est réduite et lui donne le focus clavier/souris."""
    return _format_computer_result(computer_client.focus_window, hwnd=hwnd, title=title, process_name=process_name)


@_register_computer_tool
def computer_close_window(hwnd: int) -> str:
    """Ferme proprement la fenêtre cible via UI Automation WindowPattern.Close() avec repli automatique sur Win32 WM_CLOSE.
    Permet de fermer les applications Win32, WPF ainsi que les fenêtres UWP/Store modernes (Calculatrice, Paramètres, etc.).
    """
    return _format_computer_result(computer_client.close_window, hwnd=hwnd)


@_register_computer_tool
def computer_get_window_state(
    hwnd: int | None = None,
    max_elements: int = 80,
    capture_screenshot: bool = False,
    output_path: str | None = None,
    max_depth: int = 30,
    annotate_screenshot: bool = False,
    query: str | None = None,
) -> str:
    """Extrait l'état complet de la fenêtre ciblée (ou fenêtre active) :
    - Arbre UI Automation compact avec marqueurs Set-of-Marks [#1], [#2]...
    - Type de contrôle, libellé textuel, valeur actuelle, centre relatif et coordonnées spatiales Gemini box_2d [ymin, xmin, ymax, xmax] (0-1000).
    - Capture WebP haute résolution compressée sous 200 Ko (Règle Anti-Crash 400 garantie) si capture_screenshot=True ou output_path fourni.
    - query: Filtre optionnel pour cibler directement un élément par mot-clé (ex: query='prompt', query='search', query='submit').
    - annotate_screenshot=True : superpose visuellement les bounding boxes et badges [#N] directement sur l'image WebP.
    """
    return _format_computer_result(
        computer_client.get_window_state,
        hwnd=hwnd,
        max_elements=max_elements,
        capture_screenshot=capture_screenshot,
        output_path=output_path,
        max_depth=max_depth,
        annotate_screenshot=annotate_screenshot,
        query=query,
    )


@_register_computer_tool
def computer_click(
    hwnd: int | None = None,
    element_index: int | None = None,
    x: int | None = None,
    y: int | None = None,
    box_2d: list[int] | None = None,
    button: str = "left",
    click_count: int = 1,
    foreground: bool = True,
    restore_focus: bool = False,
) -> str:
    """Clique sur un élément de l'interface par son index [#N], ses coordonnées spatiales Gemini box_2d [ymin, xmin, ymax, xmax] (0-1000), ou coordonnées relatives (x, y).
    - Boutons / onglets UIA standards : exécutés en arrière-plan sans vol de focus ni mouvement de souris.
    - Applications Electron / Web ou coordonnées : clic physique rapide.
    - restore_focus=True : restaure instantanément la fenêtre active et la position du curseur de Julien pour ne jamais interrompre son travail.
    """
    return _format_computer_result(
        computer_client.click,
        hwnd=hwnd,
        element_index=element_index,
        x=x,
        y=y,
        box_2d=box_2d,
        button=button,
        click_count=click_count,
        foreground=foreground,
        restore_focus=restore_focus,
    )


@_register_computer_tool
def computer_mouse_move(
    x: int,
    y: int,
    hwnd: int | None = None,
    smooth: bool = True,
    steps: int = 10,
    duration_ms: int = 200,
    foreground: bool = True,
) -> str:
    """Déplace le curseur de la souris vers des coordonnées (x, y) relatives à la fenêtre ou absolues à l'écran.
    Supporte le déplacement fluide ease-in-out (smooth=True).
    """
    return _format_computer_result(
        computer_client.mouse_move,
        x=x,
        y=y,
        hwnd=hwnd,
        smooth=smooth,
        steps=steps,
        duration_ms=duration_ms,
        foreground=foreground,
    )


@_register_computer_tool
def computer_type_text(
    text: str,
    hwnd: int | None = None,
    element_index: int | None = None,
    x: int | None = None,
    y: int | None = None,
    box_2d: list[int] | None = None,
    clear_first: bool = False,
    submit: bool = False,
    method: str = "auto",
    foreground: bool = True,
    restore_clipboard: bool = True,
    restore_focus: bool = False,
) -> str:
    """Saisit du texte ultra-rapidement sans jamais couper les prompts ni perturber Julien.
    - method='auto' (défaut) / 'paste' : collage atomique via le presse-papier Windows (Ctrl+V) en < 30 ms.
      Insensible aux newlines (aucun appui prématuré sur Entrée au milieu du prompt !).
      Préserve et restaure automatiquement le contenu personnel du presse-papier de Julien (restore_clipboard=True).
    - box_2d : Coordonnées Gemini [ymin, xmin, ymax, xmax] (0-1000) pour cliquer et coller directement au centre du champ.
    - submit=True : Envoie la touche Entrée après insertion pour valider/envoyer le prompt en 1 seule action.
    - restore_focus=True : Restaure instantanément la fenêtre où Julien est en train de travailler pour un fonctionnement furtif.
    """
    return _format_computer_result(
        computer_client.type_text,
        text=text,
        hwnd=hwnd,
        element_index=element_index,
        x=x,
        y=y,
        box_2d=box_2d,
        clear_first=clear_first,
        submit=submit,
        method=method,
        foreground=foreground,
        restore_clipboard=restore_clipboard,
        restore_focus=restore_focus,
    )


@_register_computer_tool
def computer_press_key(
    keys: str,
    hwnd: int | None = None,
    foreground: bool = True,
    restore_focus: bool = False,
) -> str:
    """Presse une touche ou une combinaison de touches système (raccourcis clavier).
    Exemples : 'enter', 'tab', 'escape', 'backspace', 'ctrl+c', 'ctrl+v', 'alt+tab', 'alt+f4', 'win+r', 'ctrl+shift+p'.
    restore_focus=True : restaure instantanément la fenêtre active de Julien.
    """
    return _format_computer_result(
        computer_client.press_key,
        keys=keys,
        hwnd=hwnd,
        foreground=foreground,
        restore_focus=restore_focus,
    )


@_register_computer_tool
def computer_scroll(
    delta_y: int = 0,
    delta_x: int = 0,
    hwnd: int | None = None,
    x: int | None = None,
    y: int | None = None,
    element_index: int | None = None,
    foreground: bool = False,
) -> str:
    """Fait défiler un conteneur en arrière-plan (UI Automation ScrollPattern si element_index fourni) ou la molette de la souris (delta_y > 0 = haut, delta_y < 0 = bas).
    Le défilement par molette physique exige foreground=True.
    """
    return _format_computer_result(
        computer_client.scroll,
        delta_y=delta_y,
        delta_x=delta_x,
        hwnd=hwnd,
        x=x,
        y=y,
        element_index=element_index,
        foreground=foreground,
    )


@_register_computer_tool
def computer_drag(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    hwnd: int | None = None,
    steps: int = 12,
    delay_ms: int = 15,
    foreground: bool = False,
) -> str:
    """Effectue un glisser-déposer fluide à la souris entre deux coordonnées relatives dans la fenêtre. Exige foreground=True."""
    return _format_computer_result(
        computer_client.drag,
        from_x=from_x,
        from_y=from_y,
        to_x=to_x,
        to_y=to_y,
        hwnd=hwnd,
        steps=steps,
        delay_ms=delay_ms,
        foreground=foreground,
    )


@_register_computer_tool
def computer_take_screenshot(
    hwnd: int | None = None,
    full_screen: bool = False,
    output_path: str | None = None,
    annotate_screenshot: bool = False,
) -> str:
    """Prend une capture d'écran de la fenêtre ciblée ou du bureau complet Windows.
    Garantie Anti-Crash 400 : compressée en WebP sous 200 Ko, enregistrée vers output_path ou cache local.
    annotate_screenshot=True : dessine les badges Set-of-Marks [#N] et bounding boxes sur la capture.
    """

    def _action() -> dict[str, Any]:
        import time

        elements_to_draw = None
        if annotate_screenshot:
            target_hwnd = hwnd or computer_client.user32.GetForegroundWindow()
            state = computer_client.get_window_state(hwnd=target_hwnd, capture_screenshot=False)
            elements_to_draw = state.get("elements")

        data_bytes, meta = computer_client.capture_window_image(
            hwnd=hwnd,
            full_screen=full_screen,
            return_meta=True,
            elements_to_annotate=elements_to_draw,
        )
        dest_path = output_path
        if not dest_path:
            cache_dir = Path.home() / ".nexusagy" / "screenshots"
            cache_dir.mkdir(parents=True, exist_ok=True)
            computer_client.cleanup_screenshot_cache(max_files=50, max_age_hours=24.0)
            timestamp = int(time.time() * 1000)
            dest_path = str(cache_dir / f"screenshot_{timestamp}.webp")

        dest = Path(dest_path).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data_bytes)
        return {
            "output_path": str(dest),
            "size_bytes": len(data_bytes),
            "dimensions": meta.get("captured_size"),
            "original_bounds": meta.get("original_bounds"),
            "scale_factor": meta.get("scale_factor"),
            "annotated": annotate_screenshot,
        }

    return _format_computer_result(_action)


@_register_computer_tool
def computer_spotlight_status() -> str:
    """Vérifie si le compagnon de bureau Antigravity Spotlight (Alt + Espace) et l'icône de zone de notification sont actifs."""
    running = spotlight_launcher.is_spotlight_running()
    return json.dumps(
        {
            "status": "online" if running else "stopped",
            "running": running,
            "shortcut": "Alt + Space (ou Alt + Shift + Space)",
            "script": str(spotlight_launcher.SPOTLIGHT_SCRIPT_PATH),
        },
        indent=2,
        ensure_ascii=False,
    )


@_register_computer_tool
def computer_spotlight_toggle(action: str = "start") -> str:
    """Démarre ou arrête le compagnon de bureau Antigravity Spotlight (Alt + Espace).
    action: 'start' pour démarrer en arrière-plan, 'stop' pour arrêter.
    """
    if action == "stop":
        success = spotlight_launcher.stop_spotlight()
        return json.dumps({"action": "stop", "success": success}, indent=2)
    success = spotlight_launcher.start_spotlight_background()
    return json.dumps(
        {
            "action": "start",
            "success": success,
            "shortcut": "Alt + Space",
        },
        indent=2,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NexusAGY Model Context Protocol Server")
    parser.add_argument(
        "--server",
        choices=["browser", "computer", "all"],
        default="all",
        help="Target MCP server scope: browser (31 tools), computer (12 tools), or all (43 tools)",
    )
    args = parser.parse_args()

    if args.server == "browser":
        browser_mcp.run(transport="stdio")
    elif args.server == "computer":
        computer_mcp.run(transport="stdio")
    else:
        combined_mcp.run(transport="stdio")
