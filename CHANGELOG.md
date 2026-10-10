# Changelog

Toutes les modifications notables apportées au projet **Antigravity Computer Use** seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/), et ce projet adhère au versioning sémantique.

## [2.1.0] - 2026-10-10

### Corrigé
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
  - Exécution sécurisée de `InvokePattern.Invoke()` avec timeout (1,0 s) pour éliminer tout blocage potentiel sur les boîtes de dialogue modales.
  - Activation et mise au premier plan automatique de la fenêtre cible lorsque `hwnd` est spécifié et non actif.
  - Prise en charge multi-écrans sans troncature à zéro et enregistrement des captures d'écran dans le cache local `~/.nexusagy/screenshots/` par défaut pour préserver la fenêtre de contexte textuel et éliminer le bruit base64.

### Ajouté
- **Retransmission Visuelle Set-of-Marks (`annotate_screenshot=True`)** : Tracé Stanford-style des rectangles englobants et badges numérotés `[#N]` directement sur les captures WebP (< 200 Ko).
- **Déplacement Fluide de Souris (`mouse_move(x, y, smooth=True)`)** : Trajectoire paramétrique ease-in-out pour survol naturel des éléments sans téléportation abrupte.
- **Rétention Circulaire du Cache de Captures (`cleanup_screenshot_cache`)** : Purge automatique configurable des captures locales (`max_files=50`, `max_age_hours=24.0`) évitant toute accumulation inutile sur disque.

## [2.0.0] - 2026-10-09

### Ajouté
- Version initiale de NexusAGY Computer Engine & Spotlight Companion.
- Extraction d'arbre UI Automation avec Set-of-Marks.
- Simulation d'entrées matérielles SendInput (clavier, souris, défilement, glisser-déposer).
- Compagnon Spotlight Alt + Espace.
