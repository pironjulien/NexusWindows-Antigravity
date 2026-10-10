# Background-First Windows Computer Use for AI Agents 🖥️⚡

[![Windows 11 Native](https://img.shields.io/badge/Windows-10%20%2F%2011%20Native-0078D4?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Model Context Protocol](https://img.shields.io/badge/MCP-FastMCP-FF6F00?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io/)
[![UI Automation 3.0](https://img.shields.io/badge/Engine-UI%20Automation%203.0-4285F4)](https://learn.microsoft.com/windows/win32/winauto/entry-uiauto-win32)
[![Zero Focus Theft](https://img.shields.io/badge/Focus%20Theft-0%20ms%20(Background--First)-2ea44f)](https://github.com/pironjulien/antigravity-computer-use)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Author](https://img.shields.io/badge/Author-Julien%20Piron-10a37f)](https://julienpiron.fr)

> **SOTA Background-First Windows OS Automation Engine & Global Desktop Spotlight Companion (`Alt + Space`) for AI Agents (Anthropic Claude Code, OpenAI Codex, Claude Desktop, and Google Antigravity).**
>
> 🚀 **Operate desktop apps in the background with zero cursor movement and 0 ms focus theft.**

---

## 🎬 Live Demo: 100% Background Execution

![Antigravity Computer Use Studio Demo](assets/demo.webp)

*The target window is operated silently in the background via UI Automation patterns (`TogglePattern`, `ValuePattern`, `InvokePattern`) and offscreen GDI buffers while the user's foreground focus and physical mouse cursor remain 100% uninterrupted.*

---

## 🥊 Forensic Comparison: Antigravity vs Claude vs Codex

Why does every current major desktop AI agent hijack your mouse and steal your screen, while Antigravity operates silently in the background?

| Capability | Anthropic Claude Desktop (`@anthropic/computer-use`) | OpenAI Codex / ChatGPT Desktop (`@oai/sky`) | **Antigravity Computer Use (`nexus-computer`)** |
| :--- | :--- | :--- | :--- |
| **Windows Background Execution** | ❌ **Disabled on Windows** (`if (process.platform !== "darwin") return !1;`) | ❌ **No Desktop Background** (Web only via headless `iab`; GUI apps hijack foreground) | ✅ **100% Native Background-First** |
| **User Focus Theft** | ⚠️ **100% Focus Stolen** (Requires target on top) | ⚠️ **100% Focus Stolen** (Hardcoded `SetForegroundWindow` on every click) | ⚡ **0 ms Focus Theft** (Background UIA patterns preserve active work) |
| **Mouse Cursor Hijacking** | ⚠️ **Physical Cursor Moved** (Steals user's mouse) | ⚠️ **Physical Cursor Moved** (`SendInput` at screen coordinates) | 🟢 **Zero Mouse Movement** (Deterministic element invocation) |
| **Control Targeting Method** | 👁️ Visual coordinate guessing | 👁️ Visual coordinate guessing | 🎯 **Deterministic UI Automation 3.0 + Set-of-Marks `[#1..#N]`** |
| **Occluded / Hidden Window Capture** | ❌ Fails if occluded by other windows | ❌ Fails if occluded by other windows | 📸 **Offscreen GDI Buffer** (`PrintWindow` `PW_RENDERFULLCONTENT`) |
| **Visual Protocol Safety** | ⚠️ Heavy uncompressed PNGs (> 1 MB, API 400 errors) | ⚠️ Base64 PNG screen dumps | 🛡️ **Retinal WebP < 200 KB** (Anti-Crash 400 Guard) |
| **Keyboard & International Layouts** | ❌ Often broken on non-US QWERTY | ⚠️ Key code emulation | 🌍 **Universal Unicode SendInput + UTF-16 Surrogates (AZERTY, accents, emojis)** |
| **Desktop Companion** | ❌ None | ❌ None | ⚡ **Global Floating Spotlight (`Alt + Space`)** with *Work with Apps* detection |

---

## 🏛️ How It Works: The Background-First Architecture

```mermaid
flowchart TD
    Agent["AI Agent\n(Claude Code / Codex / Antigravity)"] -->|Model Context Protocol| MCP["FastMCP Server\n(client/mcp_server.py)"]
    
    subgraph Engine ["Antigravity Computer Engine (client/computer_client.py)"]
        Router{"Action Type?"}
        
        Router -->|Click / Toggle / Select| UIA_Action["UI Automation Patterns\n(TogglePattern / ValuePattern / InvokePattern)"]
        Router -->|Inspect State| UIA_Tree["Deep UIA 3.0 Tree Walker\n(Set-of-Marks [#1..#N])"]
        Router -->|Capture Image| GDI["Offscreen Win32 GDI\nPrintWindow(PW_RENDERFULLCONTENT)"]
        Router -->|Hardware Fallback (if requested)| Input["Safety Guard + Auto-Restore\n(RestoreForeground to user's active window)"]
    end
    
    MCP --> Engine
    UIA_Action -->|Direct COM Dispatch| TargetApp["Background Desktop App\n(VS Code, Chrome, Terminal, Office)"]
    GDI -->|Direct Bitmap Copy| TargetApp
    
    style Engine fill:#161b22,stroke:#58a6ff,stroke-width:2px
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
   - Rather than taking whole-desktop screenshots (which capture whatever is currently on top of the screen), `capture_window_image(hwnd)` queries the window's private visual render buffer directly using `PrintWindow(PW_RENDERFULLCONTENT)`. Even if the application is completely covered or in the background, the agent sees a clean, unoccluded view of the window.

3. **Foreground Protection Guard & Hardware Auto-Restore**:
   - If an agent explicitly requests hardware interaction (`foreground=True`), `restore_foreground()` immediately snapshots the user's active foreground window and restores focus to it within milliseconds, ensuring zero interrupted keystrokes.

---

## 🔌 One-Click Integration for AI Agents

`antigravity-computer-use` exposes a native **Model Context Protocol (MCP)** server compatible with all MCP-enabled environments.

### 1. Claude Code CLI
Add to your project or global Claude Code configuration:
```bash
claude mcp add nexus-computer python C:/Dev/antigravity-computer-use/client/mcp_server.py -- --server computer
```

### 2. Claude Desktop
Add to `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "nexus-computer": {
      "command": "python",
      "args": [
        "C:/Dev/antigravity-computer-use/client/mcp_server.py",
        "--server",
        "computer"
      ]
    }
  }
}
```

### 3. OpenAI Codex / ChatGPT Desktop
Add to `%USERPROFILE%\.codex\config.toml`:
```toml
[mcp_servers.nexus-computer]
command = "python"
args = [
  "C:/Dev/antigravity-computer-use/client/mcp_server.py",
  "--server",
  "computer"
]
```

### 4. Google Antigravity / Custom AI Agents
Run the FastMCP server over standard stdio:
```bash
python client/mcp_server.py --server computer
```

---

## 🛠️ MCP Tool Reference

| MCP Tool | Background Safe | Description |
| :--- | :---: | :--- |
| `computer_list_windows` | ✅ Yes | Enumerates top-level interactive desktop windows with HWNDs, titles, and processes. |
| `computer_list_apps` | ✅ Yes | Groups windows by application executable (`code`, `chrome`, `pwsh`...). |
| `computer_get_window_state` | ✅ Yes | Extracts the full UI Automation tree with numbered Set-of-Marks badges `[#1..#N]`. |
| `computer_take_screenshot` | ✅ Yes | Captures offscreen retinal WebP image guaranteed under 200 KB. |
| `computer_click` | ✅ Yes | Clicks an element via UIA patterns (`Toggle`, `Invoke`, `Select`) with `foreground=False`. |
| `computer_type_text` | ✅ Yes | Sets text via `ValuePattern` without stealing focus, or hardware typing fallback. |
| `computer_press_key` | ⚠️ Focus Guard | Dispatches hardware hotkeys (`Ctrl+Shift+P`, `Win+R`, etc.) with foreground protection. |
| `computer_scroll` | ✅ Yes | Scrolls UIA container vertically or horizontally without physical mouse wheel movement. |
| `computer_mouse_move` | ⚠️ Focus Guard | Smooth Bézier easing trajectory for cursor movement when explicitly requested. |
| `computer_drag` | ⚠️ Focus Guard | Multi-step drag-and-drop between coordinate pairs. |
| `computer_focus_window` | ⚠️ Focus Guard | Brings window to foreground and restores geometry without altering desktop layout. |
| `computer_spotlight_status` | ✅ Yes | Checks whether the floating `Alt + Space` desktop companion is active. |
| `computer_spotlight_toggle` | ✅ Yes | Shows or hides the floating desktop companion. |

---

## 🚀 Quickstart & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/pironjulien/antigravity-computer-use.git
cd antigravity-computer-use
```

### 2. Install Python Dependencies
```bash
pip install -e .
```

### 3. Launch the Floating Spotlight Companion (`Alt + Space`)
```powershell
pwsh -NoProfile -File client/spotlight_launcher.ps1
```
*Press `Alt + Space` anywhere in Windows to summon the floating HUD.*

### 4. Run the Test Suite
```bash
pytest tests/ -v
```

### 5. Generate Studio Demo Animations
```bash
python generate_demo.py
```
*Compiles `assets/demo.webp`, `assets/demo.gif`, and `assets/demo.mp4` (< 120 KB each).*

---

## 👨‍💻 Author & License

Developed with symbiotic dedication by **Julien Piron** ([julienpiron.fr](https://julienpiron.fr) • X: [@julienpironfr](https://x.com/julienpironfr)).

Published under the **MIT License**. See [LICENSE](LICENSE) for details.
