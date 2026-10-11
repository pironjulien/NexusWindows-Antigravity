# Changelog

Toutes les modifications notables apportées au projet **Antigravity Computer Use** seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/), et ce projet adhère au versioning sémantique.

## [2.4.2] - 2026-10-11

### Corrigé
- **Protection Intègre du Titre de Fenêtre & Sécurité Mémoire dans `clear_first` (`WM_SETTEXT`)** :
  - `WM_SETTEXT` n'est désormais **jamais** envoyé au handle de fenêtre racine (`target != hwnd`), éliminant l'écrasement intempestif du titre de la fenêtre lors d'une saisie non scopée ou sur contrôle sans handle propre.
  - Résolution automatique du contrôle enfant ayant le focus clavier via `GetGUIThreadInfo().hwndFocus` lorsqu'aucun `element_index` n'est spécifié. En l'absence de champ focalisé, l'action échoue proprement avec `ComputerError` au lieu d'envoyer des frappes dans le vide.
  - Remplacement de `SendMessageW` par `SendMessageTimeoutW` avec drapeaux `SMTO_ABORTIFHUNG | SMTO_NORMAL` et délai de garde de 1 000 ms, prévenant tout blocage du serveur MCP en cas d'application cible non réactive.
  - Élimination de la désallocation mémoire prématurée du tampon ctypes : allocation persistante avec `ctypes.create_unicode_buffer("")` garantissant zéro corruption mémoire ou caractères parasites.
- **Prise en Charge des Chemins Entre Guillemets & Diffing Pré/Post Lancement dans `launch_app`** :
  - Transmission directe de la commande à `subprocess.Popen(command, shell=False)` sous Windows (`CreateProcessW` gérant nativement les chemins entre guillemets tels que `"C:\Program Files\..."` et leurs arguments sans dépendre de `shlex.split`).
  - Détection de fenêtre par comparaison différentielle des HWND avant et après création (`before_hwnds`), assurant la découverte immédiate de la fenêtre principale même pour les applications multi-processus, déléguées ou à instance unique.
  - Suppression de la condition erronée sur le caractère `&` (qui forçait indûment `shell=True` pour toute URL avec paramètres de requête).
- **Vérification Stricte et Déterministe de la Valeur Saisie dans `type_text`** :
  - Comparaison systématique de la valeur relue (`GetValuePattern().Value`) avec le texte attendu. En cas d'incohérence, d'échec d'injection ou de champ en lecture seule, levée immédiate d'une `ComputerError` explicite au lieu d'un faux succès.
  - Repli propre sur `val_pat.SetValue("")` pour `clear_first` sur les contrôles UIA sans HWND Win32 natif (Chromium, WPF, WinUI).

### Tests
- Suite étendue à 100 tests unitaires 100 % passants (98 auparavant), couvrant la protection du titre racine sous `WM_SETTEXT`, le timeout `SendMessageTimeoutW`, la validation stricte de relecture textuelle et le rejet de saisie non focalisée.

## [2.4.1] - 2026-10-11

### Corrigé
- **Détection de Processus & Fenêtres dans `launch_app`** : suppression du `shell=True` aveugle lors du lancement d'applications standard. Utilisation de `shlex.split(command, posix=False)` et `shell=False` afin que `proc.pid` appartienne directement à l'exécutable cible (et non à un processus intermédiaire éphémère `cmd.exe`). L'application hérite directement des indicateurs de démarrage `SW_SHOWMINNOACTIVE` et son `HWND` principal est immédiatement et précisément détecté en filtrant les fenêtres d'aide système (`Tooltip`, `Default IME`, `CiceroUIWndFrame`).
- **Ciblage Précis des Contrôles & Saisie Furtive dans `type_text`** :
  - Transmission systématique de `target_control_hwnd` (extrait de `control.NativeWindowHandle`) vers `post_message_type`, permettant aux contrôles Win32 de premier rang (`EditControl`, zones de texte) de recevoir directement les messages `WM_CHAR`.
  - Prise en charge intégrale de `clear_first=True` via l'envoi préalable du message Win32 `WM_SETTEXT` (0x000C) avec chaîne vide.
  - Relecture et vérification immédiate de la valeur textuelle modifiée via `GetValuePattern().Value` de UI Automation, intégrée dans le retour d'exécution (`verified_value`).
- **Résolution Hiérarchique de Contrôles dans `post_message_click` sans interférence d'occlusion** :
  - Remplacement de `WindowFromPoint` (qui retournait les fenêtres visibles au premier plan au lieu de la fenêtre ciblée en arrière-plan) par une descente hiérarchique récursive via l'API Win32 `RealChildWindowFromPoint(hwnd, pt_client)` ou le `target_control_hwnd` explicite. Le clic furtif atteint invariablement le bon contrôle enfant même lorsque la fenêtre cible est complètement recouverte ou hors champ.
- **Conformité Totale Ruff & Formatage** : reformatage complet de l'ensemble du dépôt (26 fichiers) selon `ruff format` et résolution des lambdas multilignes dans les tests de fumée. 0 avertissement `ruff check` et 0 fichier non formaté sous `ruff format --check`.

### Tests
- Suite étendue à 98 tests unitaires 100 % passants (95 auparavant), incluant la vérification de la résolution hiérarchique de sous-contrôles (`RealChildWindowFromPoint`), le nettoyage préventif `WM_SETTEXT`, la relecture de valeur après saisie message, et le lancement avec tubes de commande shell.

## [2.4.0] - 2026-10-11

### Ajouté
- **Contrôle Furtif Win32 par Messages Directs (`PostMessageW`)** :
  - `post_message_click(hwnd, x, y, button, count)` : injection de clics souris (`WM_LBUTTONDOWN`, `WM_LBUTTONUP`, `WM_LBUTTONDBLCLK`, `WM_RBUTTON*`, `WM_MBUTTON*`) directement dans la file de messages du HWND cible (avec résolution de sous-contrôle via `WindowFromPoint` et conversion client `ScreenToClient`). Zéro déplacement du curseur physique, zéro vol de focus.
  - `post_message_type(hwnd, text)` : saisie de caractères Unicode en tâche de fond directe via `WM_CHAR` et `VK_RETURN`/`VK_TAB` sans nécessiter le focus clavier système.
  - Option `method='post_message'` intégrée dans `click` et `type_text` à travers tous les serveurs et adaptateurs (`server.py`, `adapters/claude`, `adapters/codex`, `adapters/antigravity`).
- **Lancement d'Applications en Arrière-Plan (`SW_SHOWMINNOACTIVE`)** :
  - Nouvelle fonction `launch_app(command, background=True, wait_ms=500)` et outil MCP `@tool computer_launch_app` : démarre une application ou processus sans voler le premier plan de l'utilisateur grâce au flag Win32 `SW_SHOWMINNOACTIVE` (7) ou `SW_HIDE` (0), et détecte automatiquement le `hwnd` et `title` du processus créé.

### Tests
- Suite étendue à 95 tests unitaires 100 % passants (89 auparavant), couvrant l'injection par messages, le lparam packing, la validation de `method`, et le lancement d'applications sans focus.

## [2.3.4] - 2026-10-10

### Corrigé
- **Course au premier plan entre agents** : la vérification et l'activation de la fenêtre cible se faisaient avant la prise du verrou `Local
exus-computer-input`. Pendant l'attente (jusqu'à 5 s), un autre agent pouvait mettre une autre fenêtre devant, et le clic ou la frappe y arrivait. Le nouveau gestionnaire `engine.input_target(hwnd, *points)` tient le verrou de l'activation (ou du contrôle du premier plan) jusqu'à la dernière entrée. Il est utilisé par les trois serveurs (`server.py`, `adapters/claude`, `adapters/codex`) et par toute la couche héritée (`click`, `mouse_move`, `type_text`, `press_key`, `scroll`, `drag`).
- **Couche héritée (Antigravity) avec `foreground=True`** : la fenêtre cible n'était jamais mise au premier plan, et l'entrée partait vers la fenêtre active de Julien. Elle est désormais activée puis vérifiée, et chaque point est contrôlé (`ensure_point`) avant l'envoi. Sans `foreground=True`, le premier plan n'est jamais pris.
- **`STALE_ELEMENT`** : un seul résolveur, `_cached_element`, n'accepte qu'une liste d'éléments relevée pour la fenêtre ciblée. Cela supprime la relecture non contrôlée de `_element_cache` dans `click()` et le cache sans contrôle de fenêtre dans `scroll()`. Le clic physique réutilise l'élément déjà validé. Seul le clic gauche simple passe par UI Automation.
- **`press_key()` hérité** : il lève `ComputerError` (plus de `RuntimeError` ni de `ValueError`) et valide la combinaison avant de toucher au premier plan. Il utilise le même analyseur que les serveurs (`parse_combo`, qui gère la disposition du clavier et les touches F1 à F24). Les alias `cmd`, `page_up` et `page_down` sont conservés.
- **`drag()`** : les deux signatures appellent `ensure_default_desktop()` et refusent un `hwnd` inexistant. Le tracé est commun (`_drag_path`). La position de la fenêtre est mesurée après son activation.
- **Défilement physique hérité** : sans `x`/`y`, la molette agit au centre de la fenêtre ciblée, plus à la position courante du curseur.

### Supprimé
- `_send_inputs`, `VK_MAP` et `EXTENDED_VKEYS`, doublons de `_send`, `_KEY_NAMES` et `_EXTENDED_VKS`.

### Tests
- 89 tests unitaires (72 auparavant), dont un test de régression de la course au verrou pour chaque action physique. Les tests vérifient aussi qu'aucun serveur n'active une fenêtre hors de `input_target`. Les tests des actions héritées n'envoient plus aucune entrée réelle.

## [2.3.3] - 2026-10-10

### Corrigé
- **Correction Bloquante `scroll_at` (`core/engine.py`)** :
  - Alignement de l'appel de défilement physique sur la signature réelle `scroll_at(x, y, direction, amount)`, éliminant l'erreur `TypeError: scroll_at() got an unexpected keyword argument 'vertical'`.
- **Garantie de Relâchement du Bouton dans `drag()` (`core/engine.py`)** :
  - Encadrement strict par `try ... finally: _send(_mouse_input(up))` empêchant tout blocage du bouton gauche enfoncé en cas d'interruption ou d'exception en cours de glisser.
  - Émission systématique de l'événement `MOUSEEVENTF_MOVE` à chaque pas pour tous les formats d'appel.
- **Verrouillage Mutex Transactionnel & Rejet `INPUT_BUSY` (`core/engine.py`)** :
  - Le mutex nommé `Local\nexus-computer-input` protège désormais l'intégralité de l'action physique macro (`click_at`, `scroll_at`, `drag`, `_try_foreground`).
  - En cas de timeout (5 s), le moteur lève formellement une exception `ComputerError("INPUT_BUSY: ...")` plutôt que d'exécuter silencieusement l'action hors verrou.
- **Élimination de la Faille `STALE_ELEMENT` (`core/engine.py`)** :
  - Suppression de la condition laxiste `or not _cached_window_hwnd` dans `click()` et `type_text()` : validation stricte de l'appartenance à la fenêtre active (`_cached_window_hwnd == target_hwnd and _cached_window_hwnd != 0`).
- **Suite de Tests Portée à 72 Tests (100% Succès)** :
  - Ajout de tests unitaires couvrant le rejet `INPUT_BUSY`, le relâchement garanti dans `drag()` en cas d'erreur, et le défilement physique bidirectionnel.

## [2.3.2] - 2026-10-10

### Corrigé
- **Correction du Bug Bloquant `drag()` (`core/engine.py`)** :
  - Élimination du masquage de fonction où l'argument `foreground: bool` écrasait l'appel `foreground()`, provoquant `TypeError: 'bool' object is not callable`.
  - Utilisation directe et thread-safe de `_handle(GetForegroundWindow())`.
  - Rétablissement du nombre de pas par défaut `steps=20` (au lieu de 12) pour un glisser fluide et compatible avec les contrôles sensibles.
- **Mutex Win32 Nommé de Concurrence Inter-Agents (`Local\nexus-computer-input`) (`core/engine.py`)** :
  - Implémentation du gestionnaire de contexte `input_lock` autour de toutes les simulations d'entrées matérielles (`_send`, `_send_inputs`, `drag`).
  - Empêche toute collision ou entrelacement de frappes et de clics physiques entre agents (Claude, Codex, Antigravity) et protège la saisie en direct de Julien.
- **Validation Renforcée des Fenêtres Cibles (`core/engine.py`)** :
  - `click()`, `mouse_move()` et `type_text()` vérifient rigoureusement la fenêtre cible et interdisent tout vol de focus sans accord explicite (`foreground=True`).
  - Détection et levée d'erreur explicite `STALE_ELEMENT` lors de la réutilisation d'index d'éléments obsolètes ou d'une fenêtre fermée.
- **Suite de Tests Élargie (69 tests unitaires)** :
  - Nouveaux tests dédiés pour `input_lock`, les signatures polymorphiques de `drag()`, et le refus de pilotage sur fenêtre inactive.

## [2.3.1] - 2026-10-10

### Modifié
- **Consolidation Définitive du Moteur Unique (`core/engine.py`)** :
  - Élimination complète de la dette technique du double moteur : `adapters/antigravity/server.py` basculé à 100% sur `core/engine.py` et `core/spotlight.py`.
  - Reconversion des anciens modules `client/computer_client.py` et `client/spotlight_launcher.py` en shims ultra-légers de rétrocompatibilité sans duplication de logique.
  - Introduction de la classe universelle `WindowBounds` (héritant de `tuple` avec accès dictionnaire et attributs `.width`/`.height`) garantissant la compatibilité polymorphique across Claude, Codex et Antigravity.
  - Implémentation de la boucle adaptative de compression WebP (< 195 Ko) avec réduction progressive de la qualité et redimensionnement dynamique au facteur $0,8$, validant mathématiquement le standard Anti-Crash 400.
  - Support de métadonnées exhaustives pour Antigravity (`width`, `height`, `captured_size`, `scale_factor`, `capture_mode`).
  - Signature polymorphique universelle pour `drag()` acceptant tant le format Claude `(start, end, steps)` que le format historique Antigravity `(from_x, from_y, to_x, to_y)`.
- **Adaptateur Codex / OpenAI (`adapters/codex/server.py`)** :
  - Harmonisation des retours structurés JSON sous schéma officiel `nexus-computer/1`.
  - Renforcement du contrôle `STALE_ELEMENT` avec validation croisée de l'état de session UIA.
  - Bornage de sécurité pour la répétition de touches (`repeat = min(max(1, repeat), 50)`).

## [2.3.0] - 2026-10-10

### Ajouté
- **Garde Asynchrone du Premier Plan (*ForegroundGuard*) (`engine.py`, `server.py`)** :
  - Crochet Win32 `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` surveillant le premier plan en asynchrone : restitution du focus à la fenêtre active de Julien en 10 à 50 ms (au lieu de 600 ms).
  - Respect absolu de la saisie utilisateur (`GetLastInputInfo`) : si Julien clique ou tape au clavier pendant une action, le serveur cède immédiatement la main sans contrarier l'utilisateur.
  - Restauration de la profondeur d'empilement (*Z-Order Restoration*) : la fenêtre cible est replacée sous la fenêtre active d'origine via `SetWindowPos(SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)`.
- **Badges Harmoniques Set-of-Marks au Nombre d'Or ($\phi \approx 1,618$) (`engine.py`)** :
  - Transparence $\alpha = 255/\phi \approx 158$ laissant transparaître le texte sous le badge.
  - Chiffres cernés d'un contour sombre (`stroke_width=1`) pour une lisibilité parfaite sur fond clair ou sombre.
  - Algorithme d'agencement priorisant les plus petits éléments pour éviter tout chevauchement de numéros sur des boutons contigus.
  - Suppression automatique des contours rouges sur les grands conteneurs (> $1/\phi^2 \approx 38\%$ de la surface).
- **Architecture Tripartite Modulaire à 3 Adaptateurs Dédiés (`adapters/claude/`, `adapters/codex/`, `adapters/antigravity/`)** :
  - `adapters/claude/` : Adaptateur sur-mesure pour Anthropic Claude (Claude Code et Claude Desktop) avec sorties markdown compactes et badges harmoniques au nombre d'or.
  - `adapters/codex/` : Adaptateur sur-mesure pour OpenAI Codex et ChatGPT Desktop avec conformité stricte JSON, détection des éléments obsolètes `STALE_ELEMENT` et concision de tokens.
  - `adapters/antigravity/` : Adaptateur sur-mesure pour Google Antigravity et Gemini Multimodal, intégrant la règle Anti-Crash 400 (< 200 Ko WebP), les boîtes spatiales normalisées `gemini_box_2d [ymin, xmin, ymax, xmax]` (0-1000) et la supervision Spotlight `Alt + Space`.
  - Moteur unifié `core/engine.py` et `core/spotlight.py` partagé éliminant toute duplication ou dérive entre moteurs.
  - Point d'entrée racine `server.py` acceptant `--adapter claude|codex|antigravity` avec repli automatique universel pour une rétrocompatibilité totale.
- **Suite de Tests Élargie (65 tests unitaires et adaptateurs + 22 vérifications réelles en arrière-plan)** :
  - 45 tests unitaires complets dans `tests/test_engine.py`.
  - 3 tests d'intégration d'adaptateurs dans `tests/test_adapters.py`.
  - Test en direct sans souris ni clavier `tests/live_background.py` (22/22 vérifications réussies).
  - Script d'application de test dédiée avec ouverture au fond de la pile `tests/target_app.ps1 -Behind`.

### Modifié
- **Élimination de la Latence Artificielle UI Automation (`waitTime=0`) (`engine.py`)** :
  - Suppression de l'attente par défaut de 0,5 s imposée par le paquet `uiautomation` sur `Invoke`, `Toggle`, `Select`, `Expand`, `Collapse`, `Scroll` et `SetValue`, ramenant le temps d'exécution au niveau matériel réel.
- **Descriptions MCP Allégées (`server.py`)** :
  - Synthèse des consignes communes évitant la saturation de tokens dans les invites système de Codex, Claude et Antigravity.

### Corrigé
- **Préservation des Retours à la Ligne Multilignes (*RichEdit Fix by Codex*) (`engine.py`)** :
  - Correction de la suppression aveugle de fin de ligne : seule la marque de paragraphe synthétique `\r` propre aux contrôles Win32 RichEdit est éliminée, préservant fidèlement les sauts de ligne intentionnels dans les champs de saisie multilignes standards.
- **Filtrage des Doublons Agrandir/Restaurer (`engine.py`)** :
  - Exclusion des éléments hors de la vue contrôle de UI Automation (`IsControlElement=False`), résolvant la superposition des boutons de titre masqués.

## [2.2.0] - 2026-10-10

### Ajouté
- **Capture en Arrière-Plan Hors-Écran (*Background Offscreen GDI*) (`client/computer_client.py`)** :
  - Intégration de l'API Win32 `PrintWindow(PW_RENDERFULLCONTENT)` avec prototypes 64-bit fiabilisés dans `capture_window_image()`. Permet de capturer le rendu exact d'une fenêtre cible en mémoire même lorsqu'elle est masquée ou recouverte, sans jamais la mettre au premier plan ni risquer de capturer l'écran de travail de Julien.
- **Patterns UI Automation Étendus en Arrière-Plan (`client/computer_client.py`)** :
  - `TogglePattern` : bascule et vérification immédiate de l'état des cases à cocher et switchs sans curseur physique.
  - `SelectionItemPattern` : sélection directe des onglets, lignes de listes et boutons radio en arrière-plan.
  - `ExpandCollapsePattern` : ouverture et fermeture programmatique des menus déroulants et arbres.
  - `ScrollPattern` : défilement vertical et horizontal de conteneurs (`computer_scroll(element_index=...)`) directement en mémoire sans actionner la molette physique de la souris.
- **Restauration Automatique du Premier Plan (*Auto-Restore Foreground*) (`client/computer_client.py`)** :
  - Fonction `restore_foreground()` rétablissant instantanément le focus sur la fenêtre active de l'utilisateur si une application tierce (ex. WinForms, modales) s'active d'elle-même lors d'une action UIA.
- **Garde-Fou Matériel de Sécurité (*Foreground Protection Guard*) (`client/computer_client.py`, `client/mcp_server.py`)** :
  - Paramètre `foreground: bool = False` ajouté à `computer_click`, `computer_type_text`, `computer_press_key`, `computer_scroll`, `computer_mouse_move` et `computer_drag` : refus formel d'envoyer des événements physiques avec la souris ou le clavier si la fenêtre cible n'est pas active, garantissant à 100% que l'utilisateur n'est jamais interrompu pendant son travail sans accord explicite.
- **Générateur Autonome de Démo Studio & Animations Visuelles (`generate_demo.py`)** :
  - Pipeline de capture et encodage multi-formats produisant `assets/demo.webp` (79 Ko), `assets/demo.mp4` (73 Ko) et `assets/demo.gif` (117 Ko) avec HUD télémétrique démontrant l'exécution 100% silencieuse sans vol de focus.
- **Support Multi-Clients MCP (Claude Code, Claude Desktop, OpenAI Codex, Antigravity)** :
  - Guides d'intégration clés en main et configuration FastMCP pour tous les agents majeurs.

### Corrigé
- **Retour des Données de Capture GDI Hors-Écran (`client/computer_client.py`)** :
  - Correction d'un bug d'indentation où le bloc de sérialisation et d'annotation WebP était imbriqué dans `if img is None:`, causant le renvoi de `None` lors des captures GDI hors-écran.
- **Énumération Exhaustive des Fenêtres de Bureau (`client/computer_client.py`)** :
  - Utilisation de `user32.EnumWindows` avec repli `user32.EnumDesktopWindows`, résolvant la non-détection des fenêtres appartenant à d'autres threads ou runtimes (.NET/WinForms).
- **Initialisation COM dans le Thread d'Invocation (`client/computer_client.py`)** :
  - Encadrement de `InvokePattern.Invoke()` par `CoInitialize`/`CoUninitialize`, éliminant les erreurs `_ctypes.COMError: Paramètre incorrect` lors des invocations asynchrones.

## [2.1.0] - 2026-10-10

### Corrigé
- **Exécution Silencieuse en Arrière-Plan (*Background-First UIA*) (`client/computer_client.py`)** :
  - Priorisation de l'activation directe (`InvokePattern`) et de l'affectation de valeur (`ValuePattern`) sans appel à `focus_window()`, permettant à l'agent d'agir sur des fenêtres en arrière-plan sans voler le focus ni interrompre la frappe de Julien.
- **Détection de Recouvrement de Fenêtre (*Occlusion Check*) (`client/computer_client.py`)** :
  - Contrôle systématique via `WindowFromPoint` et `GetAncestor(GA_ROOT)` avant tout clic physique pour refuser l'action si une fenêtre intempestive recouvre le point visé.
- **Découplage Asynchrone de `InvokePattern` & Prévention du Double-Clic (`client/computer_client.py`)** :
  - Remplacement de `ThreadPoolExecutor` bloquant par un thread daemon non-bloquant pour `InvokePattern.Invoke()` et suppression du fallback physique intempestif sur les boîtes modales, éliminant tout blocage de 3 s et tout clic dupliqué.
- **Normalisation des Retours Chariot Windows (`client/computer_client.py`)** :
  - Remplacement préalable de `\r\n` par `\n` dans `type_text()`, empêchant l'envoi en double de la touche Entrée lors de la soumission de formulaires.
- **Vérification Stricte du Premier Plan Avant Saisie (`client/computer_client.py`)** :
  - Contrôle effectif de `GetForegroundWindow() == target_hwnd` après activation, empêchant toute fuite de frappe dans la mauvaise fenêtre en cas de verrou Win32.
- **Isolation Matérielle des Tests Unitaires (`tests/test_computer.py`)** :
  - Mock de `_send_inputs` et `SetCursorPos` pendant la suite pytest, éliminant les raccourcis parasites (`Ctrl+,`) et les téléportations de souris sur le bureau utilisateur.
- **Calibrage Géométrique DWM & Fenêtres Maximisées (`client/computer_client.py`)** :
  - Intégration de `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` dans `get_window_rect()` éliminant le décalage de 9 pixels des bordures invisibles Win32 sur les fenêtres maximisées.
  - Alignement géométrique parfait entre la capture d'écran, les coordonnées de détection Gemini `box_2d [0-1000]` et les clics relatifs `(x, y)`.
- **Profondeur UI Automation & Applications Electron (`client/computer_client.py`, `client/mcp_server.py`)** :
  - Augmentation de la profondeur d'exploration UIA jusqu'au niveau 30 (au lieu de 6) avec budget de temps strict à constante harmonique (`1.618 s`) et élagage spatial (*spatial pruning*) des contrôles hors écran.
  - Détection exhaustive des éléments interactifs dans les applications Chromium/Electron (Antigravity, VS Code, ChatGPT, Slack) sans aucun ralentissement.
- **Support Universel des Caractères, Emojis & Retours Ligne (`client/computer_client.py`)** :
  - Encodage en paires de substitution UTF-16 (*surrogate pairs*) dans `type_text()` pour l'injection matérielle des emojis et caractères hors BMP via `KEYEVENTF_UNICODE`.
  - Remplacement direct des sauts de ligne `\n` par un appui touche matériel `VK_RETURN` garantissant la soumission attendue dans les formulaires et terminaux.
  - Prise en charge fidèle de `clear_first=False` lors de l'utilisation de `ValuePattern` UIA pour concaténer au texte existant.
- **Raccourcis Clavier & Ponctuation (`client/computer_client.py`)** :
  - Résolution des caractères de ponctuation et symboles (`ctrl+,`, `ctrl+.`, `ctrl+-`, etc.) via l'API Win32 `VkKeyScanW`, éliminant les collisions erronées avec `VK_SNAPSHOT` (Impr. écran) ou `VK_DELETE` (Suppr).
  - Prise en charge du drapeau `KEYEVENTF_EXTENDEDKEY` pour les touches de navigation (Flèches, Inser, Suppr, Début, Fin, PgPréc, PgSuiv).
- **Routage des Clics, Clic Droit & Focus Automatique (`client/computer_client.py`)** :
  - Basculement automatique sur le clic matériel au centre du contrôle pour les clics droits (`button="right"`) et doubles-clics (`click_count=2`), sans écrasement par `InvokePattern`.
  - Activation et mise au premier plan automatique de la fenêtre cible lorsque `hwnd` est spécifié et non actif.
  - Prise en charge multi-écrans sans troncature à zéro et enregistrement des captures d'écran dans le cache local `~/.nexusagy/screenshots/` par défaut pour préserver la fenêtre de contexte textuel et éliminer le bruit base64.

### Ajouté
- **Exposition MCP Complète des Outils Avancés (`client/mcp_server.py`)** :
  - Ajout du paramètre `annotate_screenshot: bool = False` dans `computer_get_window_state` et `computer_take_screenshot`.
  - Nouvel outil MCP autonome `computer_mouse_move(x, y, smooth=True)` portant la suite `nexus-computer` à 13 outils (45 outils au total).
- **Retransmission Visuelle Set-of-Marks (`annotate_screenshot=True`)** : Tracé Stanford-style des rectangles englobants et badges numérotés `[#N]` directement sur les captures WebP (< 200 Ko).
- **Déplacement Fluide de Souris (`mouse_move(x, y, smooth=True)`)** : Trajectoire paramétrique ease-in-out pour survol naturel des éléments sans téléportation abrupte.
- **Rétention Circulaire du Cache de Captures (`cleanup_screenshot_cache`)** : Purge automatique configurable des captures locales (`max_files=50`, `max_age_hours=24.0`) évitant toute accumulation inutile sur disque.

## [2.0.0] - 2026-10-09

### Ajouté
- Version initiale de NexusAGY Computer Engine & Spotlight Companion.
- Extraction d'arbre UI Automation avec Set-of-Marks.
- Simulation d'entrées matérielles SendInput (clavier, souris, défilement, glisser-déposer).
- Compagnon Spotlight Alt + Espace.
