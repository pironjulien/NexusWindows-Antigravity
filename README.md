# Background-First Windows Computer Use for AI Agents 🖥️⚡

[![Windows 11 Native](https://img.shields.io/badge/Windows-10%20%2F%2011%20Native-0078D4?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Model Context Protocol](https://img.shields.io/badge/MCP-FastMCP-FF6F00?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io/)
[![Native COM UI Automation](https://img.shields.io/badge/Engine-Native%20COM%20UI%20Automation-4285F4)](https://learn.microsoft.com/windows/win32/winauto/entry-uiauto-win32)
[![Ultra-Low Latency Focus Guard](https://img.shields.io/badge/Focus%20Guard-10--50%20ms%20WinEventHook-2ea44f)](https://github.com/pironjulien/antigravity-computer-use)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Author](https://img.shields.io/badge/Author-Julien%20Piron-10a37f)](https://julienpiron.fr)

> **SOTA Background-First Windows OS Automation Engine & Global Desktop Spotlight Companion (`Alt + Space`) for AI Agents (Anthropic Claude Code, OpenAI Codex, Claude Desktop, and Google Antigravity).**
>
> 🚀 **Operate desktop apps in the background with zero cursor movement, asynchronous Z-order preservation, and ultra-low latency focus restoration (10–50 ms Win32 pulse restored via WinEventHook).**

---

## 🎬 Live Demo: 100% Background Execution

![Antigravity Computer Use Studio Demo](assets/demo.webp)

*The target window is operated silently in the background via UI Automation patterns (`TogglePattern`, `ValuePattern`, `InvokePattern`) and offscreen GDI buffers while the user's foreground focus and physical mouse cursor remain uninterrupted.*

---

## ⚡ Technical Comparison: Traditional Automation vs. Background-First Native Dispatch

Traditional OS computer use implementations rely on taking full-screen screenshots, guessing screen coordinates with multimodal vision models, moving the physical mouse, and forcing windows to the foreground. This breaks user workflows and makes multi-agent parallelism impossible.

`antigravity-computer-use` shifts the paradigm to **background-first native dispatch**:

| Capability | Traditional Coordinate-Based Automation | **Background-First Native Dispatch (`nexus-computer`)** |
| :--- | :--- | :--- |
| **Windows Background Execution** | ❌ **Disabled or Partial** (Requires top-level visibility) | ✅ **100% Native Background-First** |
| **User Focus Theft** | ⚠️ **Forced Foregrounding** (Steals active keyboard/window focus) | ⚡ **Zero Focus Theft** (10–50 ms WinEventHook pulse with automatic Z-order restoration) |
| **Mouse Cursor Hijacking** | ⚠️ **Physical Cursor Hijacked** (`SendInput` at coordinates) | 🟢 **Zero Mouse Movement** (Deterministic COM element invocation) |
| **Control Targeting Method** | 👁️ Visual coordinate guessing | 🎯 **Deterministic COM UI Automation + Golden-Ratio Set-of-Marks `[#1..#N]`** |
| **Occluded / Hidden Window Capture** | ❌ Fails if window is occluded or minimized | 📸 **Offscreen GDI Buffer** (`PrintWindow` `PW_RENDERFULLCONTENT`) |
| **Visual Protocol Safety** | ⚠️ Heavy uncompressed PNGs (> 1 MB, risking API 400 errors) | 🛡️ **Retinal WebP < 200 KB** (Anti-Crash 400 Guard) |
| **Keyboard & Layout Handling** | ❌ Often fragile on non-US QWERTY | 🌍 **Universal Unicode SendInput + UTF-16 Surrogates (AZERTY, accents, emojis)** |
| **Specialized Adapters** | ❌ One generic format for all models | 🔌 **3 Dedicated Adapters** (`Claude`, `Codex`, `Antigravity`) |
| **Desktop Companion** | ❌ None | ⚡ **Global Floating Spotlight (`Alt + Space`)** with *Work with Apps* detection |

---

## 🏛️ Architecture: One Core Engine, Three Specialized Adapters

```mermaid
flowchart TD
    Claude["Anthropic Claude\n(Code & Desktop)"] -->|MCP| AdapterClaude["Claude Adapter\n(adapters/claude/server.py)"]
    Codex["OpenAI Codex\n(ChatGPT Desktop & CLI)"] -->|MCP| AdapterCodex["Codex Adapter\n(adapters/codex/server.py)"]
    AGY["Google Antigravity\n(Gemini Multimodal)"] -->|MCP| AdapterAGY["Antigravity Adapter\n(adapters/antigravity/server.py)"]
    
    subgraph CoreEngine ["Unified Core Engine (core/engine.py)"]
        Router{"Dispatch Strategy"}
        
        Router -->|Click / Toggle / Select| UIA_Action["COM UI Automation Patterns\n(TogglePattern / ValuePattern / InvokePattern)"]
        Router -->|Inspect State| UIA_Tree["Deep UIA Tree Walker\n(Golden-Ratio Set-of-Marks [#1..#N])"]
        Router -->|Capture Image| GDI["Offscreen Win32 GDI\nPrintWindow(PW_RENDERFULLCONTENT)"]
        Router -->|Hardware Fallback (if requested)| FocusGuard["ForegroundGuard (10-50ms WinEventHook)\n+ Automatic Z-Order Restoration"]
    end
    
    AdapterClaude --> CoreEngine
    AdapterCodex --> CoreEngine
    AdapterAGY --> CoreEngine
    
    UIA_Action -->|Direct COM Dispatch| TargetApp["Background Desktop App\n(VS Code, Chrome, Terminal, Office)"]
    GDI -->|Direct Memory Copy| TargetApp
    
    style CoreEngine fill:#161b22,stroke:#58a6ff,stroke-width:2px
    style TargetApp fill:#0d1117,stroke:#2ea44f,stroke-width:2px
```

### The Three Pillars of Invisible OS Automation

1. **Deterministic Pattern Dispatch (No Mouse Needed)**:
   - Buttons, hyperlinks, and menu items execute via `InvokePattern`.
   - Checkboxes and toggles switch state and verify status via `TogglePattern`.
   - Text boxes receive text buffers via `ValuePattern`.
   - Dropdowns and trees expand and collapse via `ExpandCollapsePattern`.
   - Scrollable areas scroll vertically and horizontally via `ScrollPattern`.

2. **Offscreen GDI Visual Buffering**:
   - Rather than taking whole-desktop screenshots (which capture whatever is currently on top of the screen), `screenshot(hwnd)` queries the window's private visual render buffer directly using `PrintWindow(PW_RENDERFULLCONTENT)`. Even if the application is covered or in the background, the agent sees a clean, unoccluded view of the window.

3. **ForegroundGuard & Asynchronous Z-Order Restoration**:
   - If an agent explicitly requests hardware interaction (`foreground=True`), `ForegroundGuard` hooks `EVENT_SYSTEM_FOREGROUND` via Win32 `SetWinEventHook` to restore the user's active window within 10–50 ms.
   - Preserves user typing: if the user clicks or types during an operation, the engine yields immediately without fighting user input.

---

## 🔌 One-Click Integration for AI Agents

`antigravity-computer-use` exposes a native **Model Context Protocol (MCP)** server with tailored adapters for each agent ecosystem.

### 1. Anthropic Claude (Claude Code & Desktop)
Add to your Claude configuration (`~/.claude.json` or `%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "nexus-computer": {
      "command": "python",
      "args": [
        "C:/Dev/antigravity-computer-use/server.py",
        "--adapter",
        "claude"
      ]
    }
  }
}
```

### 2. OpenAI Codex & ChatGPT Desktop
Add to `%USERPROFILE%\.codex\config.toml`:
```toml
[mcp_servers.nexus-computer]
command = "python"
args = [
  "C:/Dev/antigravity-computer-use/server.py",
  "--adapter",
  "codex"
]
```

### 3. Google Antigravity & Gemini Multimodal
Add to Antigravity plugin MCP configuration:
```json
{
  "mcpServers": {
    "nexus-computer": {
      "command": "python",
      "args": [
        "C:/Dev/antigravity-computer-use/server.py",
        "--adapter",
        "antigravity"
      ]
    }
  }
}
```

---

## 🛠️ MCP Tool Reference

| MCP Tool | Background Safe | Description |
| :--- | :---: | :--- |
| `computer_list_windows` | ✅ Yes | Enumerates top-level interactive desktop windows with HWNDs, titles, geometries, and foreground status. |
| `computer_list_apps` | ✅ Yes | Groups windows by application executable (`code`, `chrome`, `pwsh`...). |
| `computer_get_window_state` | ✅ Yes | Extracts interactive UI Automation elements with Golden-Ratio Set-of-Marks badges `[#1..#N]`. |
| `computer_screenshot` / `computer_take_screenshot` | ✅ Yes | Captures offscreen image without foreground theft. Antigravity adapter guarantees WebP < 200 KB. |
| `computer_zoom` | ✅ Yes | High-resolution zoom into a specific sub-region to read fine text without re-taking full captures. |
| `computer_click` | ✅ Yes | Deterministic background activation via UIA (`Toggle`, `Invoke`, `Select`) with `foreground=False`. |
| `computer_type_text` | ✅ Yes | Sets text via `ValuePattern` in background, or hardware typing fallback when requested. |
| `computer_press_key` | ⚠️ Focus Guard | Dispatches hardware hotkeys (`Ctrl+Shift+P`, `Win+R`, etc.) with ForegroundGuard protection. |
| `computer_scroll` | ✅ Yes | Scrolls UIA container vertically or horizontally without physical mouse wheel movement. |
| `computer_mouse_move` | ⚠️ Focus Guard | Smooth Bézier easing trajectory for cursor movement when explicitly requested. |
| `computer_drag` | ⚠️ Focus Guard | Multi-step drag-and-drop between coordinate pairs. |
| `computer_focus_window` | ⚠️ Focus Guard | Brings window to foreground and restores geometry without altering desktop layout. |
| `computer_spotlight_status` | ✅ Yes | Checks whether the floating `Alt + Space` desktop companion is active. |
| `computer_spotlight_toggle` | ✅ Yes | Shows or hides the floating desktop companion. |

---

## 🚀 Quickstart & Testing

### 1. Clone the Repository
```bash
git clone https://github.com/pironjulien/antigravity-computer-use.git
cd antigravity-computer-use
```

### 2. Run the Test Suite (65 Unit & Adapter Tests)
```bash
pytest tests/ -v
```

### 3. Launch the Floating Spotlight Companion (`Alt + Space`)
```powershell
pwsh -NoProfile -File client/spotlight_launcher.ps1
```
*Press `Alt + Space` anywhere in Windows to summon the floating HUD.*

---

## 👨‍💻 Author & License

Developed with symbiotic dedication by **Julien Piron** ([julienpiron.fr](https://julienpiron.fr) • X: [@julienpironfr](https://x.com/julienpironfr)).

Published under the **MIT License**. See [LICENSE](LICENSE) for details.
