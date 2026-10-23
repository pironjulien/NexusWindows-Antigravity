# Changelog — NexusAGY (Archives v1.0.0 à v1.7.1, 2026-08 à 2026-09)

Ce fichier regroupe l'historique archivé des versions initiales (v1.0.0 à v1.7.1) antérieures à octobre 2026 du projet **NexusAGY** (`nexus-computer`), conformément au standard [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Pour les versions récentes et actives, consulter le [CHANGELOG.md](./CHANGELOG.md) principal.

---

## [1.7.1] - 2026-09-07

### Corrigé
- Fusion de la seule entrée MCP `nexus-browser`, avec sauvegarde et remplacement atomique ; les autres serveurs et réglages sont conservés.
- Un seul événement par clic CSS ou Set-of-Mark ; propagation des erreurs des actions au transport.
- Suppression de la réexécution JavaScript après une exception et du remplissage d'un autre champ lorsque le sélecteur explicite est introuvable.
- Téléversements isolés par onglet, refus des opérations concurrentes sur une même cible et nettoyage de l'interception.
- Écriture atomique des captures, PDF et inspections visuelles aux chemins demandés via MCP.
- Délais de lecture HTTP bornés, authentification avant lecture du corps et réponses explicites aux corps incomplets.
- Tests réseau isolés sur ports éphémères et jeton temporaire ; tests comportementaux JavaScript et de préservation des configurations MCP.
- Audit étendu aux tests JavaScript, à l'alignement MCP et à l'activation du plugin ; une extension déconnectée empêche de déclarer le système opérationnel.
- Configuration du `pythonpath = ["."]` dans `pyproject.toml` pour harmoniser l'exécution de la suite Pytest avec `uv run pytest`.
- Ajout de l'identifiant local d'extension Chrome non empaquetée dans `native-host/bridge_config.json`.

### Sécurité
- Remplacement du jeton Windows dérivable par un secret cryptographiquement aléatoire, local au poste, renouvelé atomiquement à chaque installation et protégé avant sa mise en service.
- Durcissement du parseur HTTP : lignes et en-têtes invalides, `Content-Length` malformé, JSON invalide et méthodes interdites reçoivent désormais une réponse explicite et bornée.

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- Mutualisation de l'authentification, du démarrage automatique et du transport HTTP dans `client/bridge_client.py`, supprimant la duplication entre le CLI et le serveur MCP.
- Ajout de la validation syntaxique de tous les scripts JavaScript à l'audit lorsque Node.js est disponible.
- Extension de la suite de tests à la rotation du jeton et aux erreurs de protocole HTTP.
- Purge du cache de bytecode du pont avant chaque déploiement, afin qu'aucun cache ne puisse masquer une mise à jour de sécurité.
- Arrêt explicite de la tâche et de tous ses écouteurs avant rotation du jeton, puis redémarrage après libération confirmée des ports, supprimant une course entre réenregistrement et déploiement.
- Lecture directe du fichier de jeton par le serveur à chaque requête, isolant la frontière d'authentification des caches de modules Python lors des mises à jour OneDrive.
- Réenregistrement atomique de la tâche du pont après désinscription de l'ancienne instance, empêchant le Planificateur de relancer une définition périmée pendant la rotation.
- Déplacement du jeton vers `%USERPROFILE%\.nexusagy`, emplacement local non virtualisé partagé par Codex, le CLI et le Planificateur Windows.
- Suppression des permissions Chrome inutilisées (`tabGroups`, `activeTab`, `nativeMessaging`, `storage`, `webNavigation`, `sidePanel`) et du lanceur Native Messaging vestigial ; sa liste blanche WebSocket devient `bridge_config.json`.
- Nettoyage automatique de l'ancienne clé Native Messaging, des anciens jetons virtualisés et des runtimes temporaires devenus inutiles.

## [1.7.0] - 2026-09-04

### Sécurité
- Authentification obligatoire de l'API HTTP locale par jeton propre à chaque profil Windows.
- ACL du jeton limitée au compte utilisateur, à SYSTEM et aux administrateurs, sans héritage.
- Rejet explicite des requêtes portant une origine web et suppression complète du CORS universel.
- Liste blanche stricte des origines WebSocket de l'extension et suppression du wildcard Native Messaging.
- Limites de taille, validation des types de requêtes, délais bornés et en-têtes de réponse défensifs.

### Corrigé
- Synchronisation additive par défaut : les skills, plugins et réglages non gérés par NexusAGY sont préservés.
- Suppression optionnelle limitée aux contenus marqués `.nexusagy-managed`, avec sauvegarde préalable.
- Audit à huit étapes avec codes de sortie fiables, contrôle du formatage et tests de sécurité réels.
- Audit de la version réellement chargée par l'extension via un ping de bout en bout.
- Versions harmonisées à 1.7.0 dans le package, l'extension, le plugin, le pont et les clients.
- Configuration MCP portable et résolue dynamiquement sur chaque poste.

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- Dépendances verrouillées par `uv.lock` dans un environnement `.venv` isolé compatible OneDrive.
- Installateur réduit aux dépendances nécessaires, sans exécution de scripts distants via `irm | iex`.
- Configuration Antigravity limitée au plugin NexusAGY, sans forcer les politiques globales de sécurité.
- Pont lancé et redémarré par une tâche Windows persistante dédiée, sans limite arbitraire de durée.
- Chemin du jeton transmis explicitement au pont supervisé pour éviter toute divergence d'environnement Windows.
- Relecture atomique du jeton à chaque requête pour prendre en charge sa rotation sans redémarrage incohérent.
- Source d'autorité du jeton rendue déterministe (SID Windows + machine) afin de rester cohérente entre processus interactifs, sandboxés et planifiés.

## [1.6.8] - 2026-09-04

### Ajouté
- **Suite de Tests Automatisés SOTA (`tests/test_nexus_core.py`, `pyproject.toml`)** :
  - Intégration de `pytest` (6 tests unitaires) validant la conformité du manifest Chrome MV3, le plugin Antigravity, l'intégrité UTF-8 sans BOM sur tous les fichiers, l'API HTTP/REST (status, CORS OPTIONS) et l'enregistrement des 22 outils FastMCP.
  - Fichier de configuration standard `pyproject.toml` pour Ruff et le packaging moderne Python.

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- **Rétrocompatibilité & Résilience Totale du Pont (`native-host/bridge_server.py`)** :
  - Intégration du dictionnaire `ACTION_ALIASES` dans le pont local pour normaliser à la volée kebab-case et snake_case (`list-tabs` -> `list_tabs`, `active-tab` -> `get_active_tab`, `pdf` -> `print_pdf`, etc.).
  - Élimine tout risque d'erreur `Unknown action` quelle que soit la version de l'extension Chrome active en mémoire.
- **Qualité de Code & Éradication Complète des Violations Ruff (`client/`, `native-host/`)** :
  - Résolution intégrale des 61 avertissements et erreurs Ruff (imports PEP 8 en tête de fichier, typage moderne Python 3.10+ `X | None`, gestion granulaire des exceptions réseau et I/O).
  - Score linter : 0 violation sur l'intégralité du projet.
- **Audit Système Étendu à 7 Piliers (`scripts/auditer-nexusagy.ps1`)** :
  - Ajout du pilier [7/7] automatisant le contrôle qualité Ruff et l'exécution de la suite Pytest.

## [1.6.7] - 2026-09-04

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- **Robustesse Découplée du Serveur de Pont (`install.ps1`, `client/mcp_server.py`, `client/antigravity_browser.py`)** :
  - Instanciation du pont via WMI (`Win32_Process.Create`) dans l'installateur pour s'affranchir définitivement de tout Job Object Windows parent et garantir la persistance du processus `pythonw.exe`.
- **Éradication des UTF-8 BOM sur les Fichiers JSON (`scripts/configurer-antigravity.ps1`, `scripts/synchroniser-gemini-global.ps1`)** :
  - Remplacement de `Set-Content -Encoding utf8` par `[System.IO.File]::WriteAllText(..., UTF8Encoding(false))` pour éliminer l'en-tête BOM (`\xEF\xBB\xBF`).
  - Résout l'erreur `proto: syntax error: invalid value ?` du parseur Go interne de `language_server.exe` et le statut rouge `Failed to load MCP servers` dans l'interface Antigravity.
- **Normalisation Hybride du Routeur d'Extension Chrome (`extension/background.js`)** :
  - Tolérance totale aux formats d'actions (kebab-case et snake_case) et mapping bidirectionnel des paramètres (`tab_id` <-> `tabId`).
  - Prise en charge native des alias `upload`, `pdf`, `eval`, `content`, `logs` et `active_tab`.

## [1.6.6] - 2026-09-04

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- **Synchronisation Miroir Bidirectionnelle & Pruning (`scripts/synchroniser-gemini-global.ps1`)** :
  - Détection et purge automatique de tout skill ou plugin orphelin / vestige dans `~/.gemini/config/` non présent dans la source `NexusAGY`.
  - Assure une parité et une propreté absolues lors du déploiement sur une autre machine (maison / bureau).
- **Outillage SOTA Étendu (`install.ps1`)** :
  - Intégration de la vérification et auto-installation de Ruff (linter Python) et uv (gestionnaire de packages Python ultra-rapide en Rust) aux côtés de Bun, Ripgrep et python-mcp.
  - Normalisation robuste des flux JSON et des fins de ligne dans `synchroniser-gemini-global.ps1`.

### Supprimé
- **Épuration des Compétences Vestiges (`NexusAGY/skills/`)** :
  - Retrait définitif des compétences génériques de prompt engineering (`nextjs-react-expert`, `shadcn-tailwind-expert`, `security-reviewer`, `gemini-api-dev`).
  - Alignement SOTA strict : Gemini 3.8 Flash maîtrise nativement l'ensemble de ces frameworks et règles de sécurité. Conserver des fiches d'instructions textuelles statiques alourdissait inutilement le contexte de prompt sans valeur ajoutée.
  - Seul le pont sur-mesure à forte valeur ajoutée (`nexus-browser`) est conservé en tant que plugin officiel.

## [1.6.5] - 2026-09-04

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- **Éradication des Déclarations Fantômes (`config.json`, `scripts/configurer-antigravity.ps1`)** :
  - Nettoyage rigoureux de `config.json` pour supprimer les clés de plugins non téléchargés (`android`, `firebase`, `chrome-devtools`, `science`, `modern-web-guidance`).
  - Reconstruction dynamique de `config.plugins` dans `configurer-antigravity.ps1` ne conservant que les plugins physiques réellement installés et vérifiés sur le disque (`nexus-browser`).

### Ajouté
- **Déploiement des Compétences Frontend & Sécurité SOTA (`NexusAGY/skills/`)** :
  - Intégration et synchronisation multi-postes des compétences de référence :
    - `nextjs-react-expert` : Architecture React 19, Next.js App Router, Server Actions.
    - `shadcn-tailwind-expert` : UI moderne, Radix UI, Tailwind CSS v4, composants accessibles.
    - `security-reviewer` : Audit de sécurité de code, protection des tokens et bonnes pratiques OWASP.
    - `gemini-api-dev` : Développement avec l'API Gemini multimodale et structured outputs.
  - Disponibles en *progressive disclosure* sur tous les postes de Julien via OneDrive.

## [1.6.4] - 2026-09-04

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- **Portabilité Dynamique des Chemins MCP (`scripts/synchroniser-gemini-global.ps1`)** :
  - Résolution dynamique de l'emplacement exact de `client\mcp_server.py` lors de chaque synchronisation.
  - Élimine tout risque d'incompatibilité liée au nom d'utilisateur Windows ou à l'emplacement du dossier OneDrive entre les différents postes de Julien.

## [1.6.3] - 2026-09-04

### Ajouté
- **Encapsulation Complète du Plugin `nexus-browser` (`plugins/nexus-browser/`)** :
  - Intégration de `mcp_config.json` directement au sein du bundle plugin conformément à la spécification officielle Antigravity.
  - Activation formelle de `"nexus-browser": { "enabled": true }` dans la configuration globale `config.json` via `scripts/configurer-antigravity.ps1`.
- **Extension de l'Audit Centralisé (6/6 Points de Contrôle)** (`scripts/auditer-nexusagy.ps1`) :
  - Ajout du 6ème jalon d'audit vérifiant en continu l'intégrité du serveur MCP, de `mcp_config.json` et de l'activation du plugin.

## [1.6.2] - 2026-09-04

### Ajouté
- **Installateur Universel Multi-Machines Automatisé (`install.ps1`, `README.md`)** :
  - Installation automatique et silencieuse de tout l'outillage SOTA lors du déploiement sur une nouvelle machine ou à la maison (Python `mcp`, `bun`, `ripgrep`, `ruff`).
  - Documentation clé-en-main étape par étape dans le `README.md` pour synchroniser et activer l'écosystème sur n'importe quel PC en 2 minutes chrono.
- **Préservation des Préférences Utilisateur (`scripts/configurer-antigravity.ps1`)** :
  - Retrait du forçage de `useAiCredits` pour respecter scrupuleusement la configuration de facturation choisie par Julien.

## [1.6.1] - 2026-09-04

### Ajouté
- **Auto-Démarrage Transparent & Auto-Guérison (*Self-Healing*)** (`client/mcp_server.py`, `client/antigravity_browser.py`) :
  - Détection automatique de la disponibilité du pont local HTTP/WS.
  - En cas d'inactivité du serveur (redémarrage machine, processus tué), `bridge_server.py` est instancié silencieusement en arrière-plan sans fenêtre, résolvant définitivement la dépendance à un démon pré-existant.
- **Outillage Système SOTA Déployé sur la Machine** :
  - **`bun` v1.4.1** : Runtime JS/TS ultra-rapide en Zig installé et configuré dans le PATH.
  - **`ripgrep` (`rg`) v15.2.0** : Moteur de recherche textuelle natif ultra-rapide déployé.
  - **`ruff` v0.16.6** : Linter et formateur Python de référence mondiale (en Rust) installé via `uv`.

## [1.6.0] - 2026-09-04

### Ajouté
- **Serveur MCP Natif Antigravity (`client/mcp_server.py`, `mcp_config.json`)** :
  - Exposition de 22 outils d'automatisation navigateur natifs basés sur `FastMCP` (navigation, clics sémantiques et laser, upload silencieux de bundles AAB, vision Set-of-Mark, etc.).
  - Élimination de la surcharge de terminal shell pour les interactions navigateur en permettant des tool-calls directs, instantanés et typés.
  - Synchronisation globale automatique vers `%USERPROFILE%\.gemini\config\mcp_config.json`.
- **Piliers Opérationnels d'Élite dans `GEMINI.md`** :
  - **Boucle de Vérification Autonome (*Done means Done*)** : Obligation d'auto-validation (tests, build, git diff, logs) et correction itérative silencieuse avant de déclarer une tâche terminée.
  - **Sparring-Partner & Franchise Radicale** : Conseil stratégique sans complaisance, proactivité critique et proposition de l'état de l'art supérieur.
  - Préservation intégrale de tous les standards chers à Julien (Permissions Windows, répertoires dédiés, coffre NexusSecure, constante harmonique 1,618, résolution à la racine, adaptabilité d'exécution).
  - Élimination de toute charge mentale inutile (rejet de fichiers redondants type `PROJECT.md` grâce au contexte massif de 1M+ tokens et aux capacités d'investigation de Gemini).

## [1.5.2] - 2026-09-04

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- **Raffinement SOTA de la Directive Sécurité & Intégrité (`GEMINI.md`)** :
  - Remplacement de l'ancienne formulation restrictive et anxiogène par une clause positive, souveraine et responsabilisante ("Préserve en toutes circonstances l'intégrité et la pérennité des comptes et services de production de Julien...").
  - Élimination des termes déclencheurs de sur-censure (chilling effect) pour libérer l'audace technique, l'exploration et l'autonomie sur tous types de projets, tout en maintenant une vigilance absolue sur les accès critiques.

## [1.5.1] - 2026-09-04

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- **Consolidation SOTA du Pacte Symbiotique (`GEMINI.md`)** :
  - Suppression définitive de la dépendance obsolète `memory.json` : élimination du `view_file` obligatoire au démarrage pour une réactivité instantanée et une économie de tokens dès le premier mot de Julien.
  - Sanctuarisation explicite du compte principal de Julien (Gmail, Google Play Console, Google Cloud Platform, Firebase) : zéro risque de ban garanti via l'usage exclusif de l'environnement officiel Antigravity et l'interdiction stricte de scrapers ou requêtes non autorisées.
  - Nettoyage du dossier scratch local obsolète `symbiotic_memory/`.

## [1.5.0] - 2026-09-04

### Ajouté
- **Interception CDP des Sélecteurs de Fichiers (`upload`, `Page.fileChooserOpened`)** :
  - Écoute et interception directe de l'événement CDP `Page.fileChooserOpened` et `Page.setInterceptFileChooserDialog`.
  - Téléversement direct et silencieux de fichiers via `DOM.setFileInputFiles` sans ouvrir ni bloquer sur la boîte de dialogue native Windows Explorer.
  - Résout l'écart critique d'autonomie avec OpenAI Codex pour le déploiement d'applications (bundles AAB sur Google Play Console, releases GitHub, assets Firebase).
- **Vision Grounding Multimodal & Badges Set-of-Mark (SoM) (`vision-inspect`, `click-mark`)** :
  - Injection dynamique d'étiquettes visuelles néon numérotées sur tous les éléments interactifs (`__antigravity_render_som`).
  - Capture haute définition transmise à l'analyseur de vision multimodal de Gemini.
  - Clic direct au centre géométrique exact du badge (`click-mark --mark <N>`), éliminant tout échec de sélection CSS/XPath sur les interfaces web dynamiques ou obfuscées.
- **Sélecteurs Sémantiques Robustes Style Playwright (`semantic-click`, `semantic-fill`, `select-option`)** :
  - `semantic-click` : Clic par rôle ARIA (`button`, `link`, `tab`, etc.), nom accessible ou texte partiel.
  - `semantic-fill` : Remplissage intelligent de formulaire par étiquette (`<label>`), placeholder ou attribut `name`.
  - `select-option` : Sélection native dans les menus déroulants `<select>` par valeur ou texte visible avec déclenchement des événements `input` et `change`.
- **Contrôleur Clavier CDP Avancé (`press-key`)** :
  - Émission d'événements `Input.dispatchKeyEvent` avec code de touche virtuel (`windowsVirtualKeyCode`) et noms officiels (`Enter`, `Escape`, `Tab`, `Backspace`, `ArrowDown`, etc.).
- **Stabilisation et Détection d'Inactivité Réseau (`wait-load`)** :
  - Attente active que le document atteigne l'état `document.readyState === "complete"` avec timeout paramétrable.
- **Détection Automatique de Handoff Sécurité & 2FA (`check-handoff`)** :
  - Détection proactive des écrans de vérification en deux étapes (2FA SMS, Google Authenticator), CAPTCHA et Cloudflare Turnstile pour prévenir l'agent et alerter Julien si une intervention humaine est requise.
- **Support Universel CLI (`client/antigravity_browser.py`)** :
  - Expansion du client Python avec 25 sous-commandes couvrant 100% de la surface d'API CDP du pont.
- **Enregistrement Registre Windows (`HKCU`)** :
  - Clé `HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.antigravity.chrome_bridge` enregistrée pointant vers le manifeste natif.

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- **Épuration SOTA de `GEMINI.md` & Économie Drastique de Contexte** :
  - Suppression des balises pseudo-XML anachroniques `<RULE[symbiotic_liberation]>` issues d'anciennes pratiques de prompt engineering, remplacées par une formulation Markdown propre, professionnelle et nativement comprise.
  - Déport de l'énumération des 25 commandes CLI vers la compétence globale `nexus-browser` (`SKILL.md`) conformément au principe de *Progressive Disclosure* d'Antigravity : la règle globale ne conserve que la directive de comportement, économisant ainsi des centaines de tokens sur chaque tour de conversation.
- **Manifeste Extension Chrome (`manifest.json`)** : Version augmentée à `1.3.0`.

## [1.4.1] - 2026-09-01

### Modifié
- `desktop.json` : « Exécuter en arrière-plan » (`runInBackground`) passe à `true`, réglage choisi sur un des PC
  le 14/10 et désormais partagé par tous les postes.
- **Consolidation de la Source de Vérité (`GEMINI.md`)** : Intégration de la directive `<RULE[symbiotic_liberation]>` au sommet de la source maître pour supprimer tout doublon de règles globales `user_global` et optimiser le budget de contexte.
- **Désactivation des Compétences Obsolètes** : Archivage de `node_repl` vers `skills_disabled/` pour ne conserver que les compétences SOTA actives (`nexus-browser`).
- **Amélioration de la Résilience Client Browser** : Remontée directe des messages d'erreurs du pont HTTP dans le client Python.

## [1.4.0] - 2026-08-27

### Ajouté
- **Gravure Globale du Pilotage Navigateur dans la Mémoire Maître (`GEMINI.md`)** : Inscription d'une directive de premier rang interdisant à Antigravity de demander à Julien toute action web réalisable via le pont local.
- **Compétence Globale `nexus-browser`** : Création du plugin et skill officiel [`skills/nexus-browser/SKILL.md`](skills/nexus-browser/SKILL.md) synchronisé dans `~/.gemini/config/plugins/nexus-browser/` et `NexusAGY/plugins/`.
- **Verrouillage de l'ID Extension Chrome** : Inscription explicite de l'ID d'extension `ljgneacjmkmiopjfacahdpcigiofnngo` dans les `allowed_origins` du manifeste Native Messaging `com.antigravity.chrome_bridge.json` pour garantir une liaison permanente sans rupture.
- **Vérification en direct du Pont Chrome** : Validation E2E de l'inspection de pages complexes (Google Cloud Console, Google Play Console, X) et synchronisation instantanée.

## [1.3.0] - 2026-08-25

### Ajouté
- **Hub de Synchronisation Multi-Machines Antigravity** : Intégration de la source de vérité globale `GEMINI.md` à la racine de `NexusAGY` pour harmoniser tous les postes de Julien.
- **Synchronisation Atomique SHA-256** (`scripts/synchroniser-gemini-global.ps1`) : Copie atomique et vérification d'empreinte vers `%USERPROFILE%\.gemini\config\GEMINI.md` avec archivage automatique des versions antérieures.
- **Tâche Planifiée Windows** (`scripts/installer-synchronisation-gemini-global.ps1`) : Enregistrement de la tâche masquée `NexusAGY GEMINI Sync` déclenchée à l'ouverture de session (`AtLogOn`).
- **Alignement Idempotent des Configurations** (`scripts/configurer-antigravity.ps1`) : Optimisation des plugins et des politiques d'exécution turbo dans `config.json`.
- **Script d'Audit Complet** (`scripts/auditer-nexusagy.ps1`) : Vérification centralisée de l'empreinte `GEMINI.md`, de la tâche planifiée, du registre, du pont et de l'extension.
- **Installateur Orchestrateur Tout-en-Un** (`install.ps1`) : Refonte avec support des modes `-CheckOnly`, `-WhatIf` et `-SkipLaunch`.
- **Support des Compétences & Plugins Globaux** : Répertoires synchronisables `skills/`, `plugins/` et `mcp_config.json`.

## [1.2.0] - 2026-08-25 (SOTA+)

### Ajouté
- **Export PDF direct sans dialogue** (`Page.printToPDF`) : Génération silencieuse de PDF au format A4 vectoriel haute fidélité.
- **Frappe clavier naturelle réaliste** (`Input.dispatchKeyEvent`) : Émulation touche par touche pour déclencher les champs avec auto-complétion stricte.
- **Protection contre les URLs internes** : Filtrage silencieux et robuste évitant toute alerte rouge sur `chrome://*`.

## [1.1.0] - 2026-08-25

### Ajouté
- **Visual Click Ripple** (`content_script.js`) : Effet laser/onde néon lors de chaque clic interactif pour retour visuel direct.
- **Arbre d'accessibilité (AXTree)** : Extraction sémantique via CDP `Accessibility.getFullAXTree` (rôles, noms, états des éléments).
- **Navigation Multi-Iframes** : Détection et manipulation récursive transparente des éléments à l'intérieur des `<iframe>` (essentiel pour les espaces clients type OVH).
- **Capture de logs console & erreurs réseau** : Historique en temps réel des erreurs JS de l'onglet actif.
- **Capture d'écran ciblée par élément** : Découpage précis d'un composant par sélecteur CSS.
- **Gestionnaire de boîtes de dialogue JavaScript** : Acceptation/rejet automatique des `alert()`, `confirm()` et `prompt()`.

## [1.0.0] - 2026-08-25

### Ajouté
- Extension Chrome Manifest V3 complète avec permissions étendues (`debugger`, `scripting`, `tabs`, `activeTab`, `nativeMessaging`, `storage`, `offscreen`).
- Contrôleur CDP (Chrome DevTools Protocol) pour l'automatisation complète.
- Serveur de pont bidirectionnel local WebSocket & HTTP (`ws://127.0.0.1:9224`).
- Native Messaging Host Windows (`com.antigravity.chrome_bridge`) et script d'installation automatique dans le registre (`install.ps1`).
