# Antigravity Computer Use — SOTA Windows OS Automation & Spotlight Companion 🖥️⚡

[![Windows 11 Native](https://img.shields.io/badge/Windows-10%20%2F%2011%20Native-0078D4?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Model Context Protocol](https://img.shields.io/badge/MCP-FastMCP-FF6F00?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io/)
[![Google Antigravity Native](https://img.shields.io/badge/Agent-Google%20Antigravity-4285F4?logo=google&logoColor=white)](https://github.com/pironjulien/antigravity-computer-use)
[![UI Automation 3.0](https://img.shields.io/badge/Engine-Windows%20UI%20Automation%203.0-34A853)](https://learn.microsoft.com/windows/win32/winauto/entry-uiauto-win32)
[![Ultra-Low Latency Focus Guard](https://img.shields.io/badge/Focus%20Guard-10--50%20ms%20WinEventHook-2ea44f)](https://github.com/pironjulien/antigravity-computer-use)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Author](https://img.shields.io/badge/Author-Julien%20Piron-10a37f)](https://julienpiron.fr)

> **Moteur autonome de Computer Use Windows et compagnon Spotlight global (`Alt + Espace`) développé exclusivement pour Google Antigravity et les modèles multimodaux Gemini 2.5.**
>
> 🚀 **Pilotez vos applications Windows en arrière-plan sans vol de focus, sans mouvement intempestif de curseur, avec préservation stricte du Z-order et restauration de focus ultra-rapide (10–50 ms WinEventHook).**

---

## 🎬 Démonstration : Exécution 100% en Arrière-Plan

![Antigravity Computer Use Studio Demo](assets/demo.webp)

*L'application cible est pilotée silencieusement en arrière-plan via les patterns UI Automation 3.0 (`TogglePattern`, `ValuePattern`, `InvokePattern`, `WindowPattern`) et tampons offscreen GDI, tandis que le focus et la souris de l'utilisateur restent parfaitement libres au premier plan.*

---

## ⚡ En quoi Antigravity Computer Use transforme l'automatisation OS

Les approches conventionnelles d'automatisation OS reposent sur la capture d'écran plein écran, l'estimation approximative de coordonnées par des modèles vision, le déplacement de la souris physique et la mise au premier plan forcée des fenêtres. Cela détruit le flux de travail de l'utilisateur et rend impossible toute concurrence d'agents.

`antigravity-computer-use` adopte un paradigme **déterministe et orienté arrière-plan** :

| Fonctionnalité | Automatisation Conventionnelle | **Antigravity Computer Use (`nexus-computer`)** |
| :--- | :--- | :--- |
| **Exécution en arrière-plan** | ❌ Fenêtre obligatoirement visible au premier plan | ✅ **100% Natif en arrière-plan** (sans vol de focus) |
| **Vol de focus utilisateur** | ⚠️ Vole le focus clavier et premier plan | ⚡ **Zéro vol de focus** (Garde `WinEventHook` 10–50 ms avec restauration automatique) |
| **Détournement du curseur souris** | ⚠️ Curseur physique baladé sur l'écran | 🟢 **Zéro mouvement de souris** (Invocation déterministe COM UI Automation) |
| **Ciblage des contrôles** | 👁️ Estimation approximative de coordonnées pixels | 🎯 **COM UI Automation 3.0 + Set-of-Marks `[#1..#N]` + Gemini `box_2d` `[ymin, xmin, ymax, xmax]`** |
| **Fermeture propre de fenêtres** | ❌ Tuer le processus de force (`taskkill`) | 🛡️ **`computer_close_window` déterministe** (`WindowPattern.Close()` puis repli `WM_CLOSE`) |
| **Fenêtres masquées ou recouvertes** | ❌ Échoue si la fenêtre est recouverte | 📸 **Tampon GDI Offscreen** (`PrintWindow` `PW_RENDERFULLCONTENT`) |
| **Sécurité protocolaire des images** | ⚠️ PNGs lourds (> 1 Mo) risquant l'erreur Cloud API 400 | 🛡️ **WebP compressé < 200 Ko** (Garde Anti-Crash 400 garanti) |
| **Clavier et jeux de caractères** | ❌ Fragile sur claviers non-US | 🌍 **SendInput Unicode Universel + Substituts UTF-16 (AZERTY, accents, émojis)** |
| **Compagnon de bureau** | ❌ Aucun | ⚡ **Spotlight flottant global (`Alt + Espace`)** avec détection *Work with Apps* |

---

## 🏛️ Architecture Déterministe

```mermaid
flowchart TD
    AGY["Google Antigravity\n(CLI agy / Antigravity IDE)"] -->|Model Context Protocol (FastMCP)| MCPServer["Serveur MCP Antigravity\n(client/mcp_server.py)"]
    
    subgraph EngineCore ["Moteur Central Windows (client/computer_client.py)"]
        Router{"Stratégie d'Exécution"}
        
        Router -->|Clic / Bascule / Sélection| UIA_Action["COM UI Automation 3.0 Patterns\n(TogglePattern / ValuePattern / InvokePattern / WindowPattern)"]
        Router -->|Inspection d'État & Grounding| UIA_Tree["Parcours d'Arbre UIA Récursif\n(Set-of-Marks [#1..#N] & Gemini box_2d)"]
        Router -->|Capture d'Écran Sécurisée| GDI["Tampon Win32 GDI Offscreen\nPrintWindow(PW_RENDERFULLCONTENT)"]
        Router -->|Action Matérielle Requise| FocusGuard["ForegroundGuard (10-50ms WinEventHook)\n+ Restauration Immédiate du Z-Order"]
    end
    
    MCPServer --> EngineCore
    
    UIA_Action -->|Dispatch COM Direct| TargetApp["Application Windows Cible\n(VS Code, Chrome, Terminal, Office, Win32/WPF/WinUI)"]
    GDI -->|Copie Mémoire Directe| TargetApp
    
    style EngineCore fill:#161b22,stroke:#4285f4,stroke-width:2px
    style TargetApp fill:#0d1117,stroke:#34a853,stroke-width:2px
```

---

## 🔌 Intégration Native dans Google Antigravity

Le serveur MCP `antigravity-computer-use` s'intègre nativement à Google Antigravity via votre configuration `mcp_config.json` :

```json
{
  "mcpServers": {
    "nexus-computer": {
      "command": "python",
      "args": [
        "C:/Dev/antigravity-computer-use/client/mcp_server.py",
        "--scope",
        "computer"
      ]
    }
  }
}
```

---

## 🛠️ Répertoire des Outils MCP

| Outil MCP | Arrière-Plan Sécurisé | Description |
| :--- | :---: | :--- |
| `computer_list_windows` | ✅ Oui | Énumère toutes les fenêtres interactives avec HWND, titres, géométries et statut de premier plan. |
| `computer_list_apps` | ✅ Oui | Regroupe les fenêtres par processus exécutable (`chrome`, `code`, `pwsh`...). |
| `computer_get_window_state` | ✅ Oui | Extrait l'arbre UI Automation avec Set-of-Marks `[#1..#N]` et coordonnées Gemini `box_2d` `[ymin, xmin, ymax, xmax]`. |
| `computer_focus_window` | ⚠️ Garde Focus | Active la fenêtre cible en douceur sans détruire l'agencement du bureau. |
| `computer_close_window` | ✅ Oui | Ferme proprement la fenêtre via `WindowPattern.Close()` UIA avec repli Win32 `WM_CLOSE`. |
| `computer_click` | ✅ Oui | Clic déterministe d'arrière-plan via UIA (`Invoke`, `Toggle`, `Select`) sans mouvement de curseur physique. |
| `computer_type_text` | ✅ Oui | Écriture directe via `ValuePattern` en arrière-plan, avec repli sécurisé sur frappe Unicode. |
| `computer_press_key` | ⚠️ Garde Focus | Injection de touches et raccourcis (`Ctrl+Shift+P`, `Win+R`) avec protection ForegroundGuard. |
| `computer_scroll` | ✅ Oui | Défilement vertical ou horizontal direct du conteneur UIA sans molette physique. |
| `computer_mouse_move` | ⚠️ Garde Focus | Trajectoire fluide avec lissage de Bézier en cas de manipulation matérielle explicite. |
| `computer_drag` | ⚠️ Garde Focus | Glisser-déposer multi-étapes entre deux paires de coordonnées. |
| `computer_take_screenshot` | ✅ Oui | Capture d'écran offscreen sans vol de focus, compressée en WebP < 200 Ko (Anti-Crash 400). |
| `computer_spotlight_status` | ✅ Oui | Vérifie si le compagnon HUD flottant `Alt + Espace` est actif. |
| `computer_spotlight_toggle` | ✅ Oui | Affiche ou masque le compagnon de bureau flottant. |

---

## 🚀 Démarrage Rapide & Tests

### 1. Cloner le Dépôt
```bash
git clone https://github.com/pironjulien/antigravity-computer-use.git
cd antigravity-computer-use
```

### 2. Exécuter la Suite de Tests Déterministes (26 Tests Unitaires)
```bash
pytest tests/test_computer.py tests/test_spotlight.py -v
```

### 3. Lancer le Compagnon Spotlight (`Alt + Espace`)
```powershell
pwsh -NoProfile -File client/spotlight_launcher.ps1
```
*Appuyez sur `Alt + Espace` n'importe où sous Windows pour ouvrir le HUD d'Antigravity.*

---

## 👨‍💻 Auteur & Licence

Développé en symbiose par **Julien Piron** ([julienpiron.fr](https://julienpiron.fr) • [julienpiron.com](https://julienpiron.com) • X : [@julienpironfr](https://x.com/julienpironfr)).

Publié sous licence **MIT**. Consulter [LICENSE](LICENSE) pour plus de détails.
