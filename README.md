# NexusWindows for Antigravity

[![Release](https://img.shields.io/github/v/release/pironjulien/antigravity-windows-computer-use)](https://github.com/pironjulien/antigravity-windows-computer-use/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-server-7ee2a8)](https://modelcontextprotocol.io)
[![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4)](#install)

[![NexusWindows: Windows computer use for AI agents, in the background. Works with Claude, Codex and Antigravity.](docs/assets/banner.webp)](https://julienpiron.fr/nexuswindows/)

**Windows computer use for Antigravity, in the background.** An MCP server (`nexus-computer`) that lets Google
Antigravity (Gemini) see and operate Windows desktop applications while the user keeps their mouse, keyboard and
foreground window. Built for a fast model: one look, then one batch of steps with label targets, and every reply
says what to do next.

Version 2.8.2 · Windows 10/11 · Python 3.10+ · MIT licence

Part of the Nexus family: [NexusWindows](https://julienpiron.fr/nexuswindows/)
([Claude](https://github.com/pironjulien/claude-windows-computer-use) ·
[Codex](https://github.com/pironjulien/codex-windows-computer-use) ·
[Antigravity](https://github.com/pironjulien/antigravity-windows-computer-use)),
[NexusBrowser](https://julienpiron.fr/nexusbrowser/) ([repo](https://github.com/pironjulien/chrome-computer-use)),
[NexusAndroid](https://julienpiron.fr/nexusandroid/) ([repo](https://github.com/pironjulien/android-computer-use)).
Project page: [julienpiron.fr/nexuswindows](https://julienpiron.fr/nexuswindows/).

## Why

Screenshot-and-click computer use moves the real cursor and brings windows to the front, so the person at the PC has
to stop working while the agent acts. Most Windows applications can be driven without that: native controls accept
window messages and modern frameworks expose UI Automation. This server acts in the background first, reads the
effect back, and only falls back to the real mouse or keyboard when the step allows it (`foreground=True`).

## Tools

Five listed MCP tools; the ten older names (`computer_click`, `computer_type_text`...) stay callable as unlisted
aliases.

| Tool | Purpose |
| --- | --- |
| `computer_list_windows` | Application windows (`by_app=true`: grouped by application) |
| `computer_look` | One line per element `[N] role « name » = « value » states @x,y`, plus an image, without bringing the window forward |
| `computer_act` | Several steps in one call (click, type, check, uncheck, select, menu, keys...), each read back |
| `computer_open_path` | Open a document, folder, program, script or shortcut; the opening is read back |
| `computer_close_window` | Close a window (UI Automation, then `WM_CLOSE`) |

Tool descriptions and replies are in French; tool and parameter names are in English.

## What it does

- **Designed for Gemini**: golden rule *look, then act in one batch with label targets*; every action reply carries
  a one-line `next` (✓ done · = already done, do not redo · ~ effect not seen, look at the attached image · ✗ failure,
  cause and what to try) and, when the effect was not read back, a compact WebP image (≤ 1280 px) of the window. A
  batch identical to one sent in the last 10 s on the same window without a `computer_look` in between is
  **refused** (`repeat=true` forces it).
- **Background first, even with `foreground=True`**: a `box_2d` or (x, y) target is mapped to the element under the
  point in the window's own UI Automation tree (covered windows included) and handled like a label target; a click on
  a text field *retains* it, so `type` without target, `ctrl+a`, `ctrl+v` and erase keys become background writes
  read back; plain keys are posted (`WM_KEYDOWN`/`WM_KEYUP`) in Win32, WinForms and WPF. Real mouse and keyboard only
  as a fallback with `foreground=True`; otherwise an explicit refusal (`needs_foreground`) and nothing is sent.
- **Per UI family**: Win32 → direct messages (`BN_CLICKED`, `BM_SETCHECK`, `EM_REPLACESEL`, `CB_SETCURSEL` /
  `LB_SETCURSEL` with their notifications, menu `WM_COMMAND`); WinForms → UI Automation then messages; WPF, UWP,
  Chromium → UI Automation only. Never UI Automation Invoke on a Win32 button (its proxy activates the window) nor
  Select on a Win32 list (silent).
- **One cross-process read**: the window-scoped UI Automation tree is read in one round trip
  (`IUIAutomationCacheRequest` + `BuildCache`, `AutoSetFocus = False`). A truncated or failed read is reported
  (`uia.status`, `warning`), never a silent empty list.
- **Read-back after every action**: `verified` true/false/None from a real read (field value, check state,
  selection, focused element, window title, image); `success` is never true on "command sent" alone. Steps accept a
  postcondition `expect` (already true: step skipped with `already: true`; false after: step failed).
- **The user's physical input via Raw Input** (injected input ignored): wait for a pause before any real mouse or
  keyboard action, and stop at the next checkpoint if the user touches keyboard or mouse (`interrupted_by_user`).
- **Guards in the code, not only in the instructions**: the window is always named (never the foreground one by
  default, ambiguous titles refused with the candidates); an ambiguous label is refused with the candidates; the
  target window is read back in the foreground right before every `SendInput`; password managers (KeePass,
  KeePassXC, Bitwarden, 1Password, Dashlane, NordPass, RoboForm, LastPass) are never looked at, captured or driven;
  the sign-in screen, lock screen and UAC prompt are refused. An action labelled pay, buy, order, transfer money,
  send, publish, delete permanently, uninstall, format, reset, cancel a subscription, erase data or make a repository
  public needs `confirm: true` on the step, and so does any key, `submit` or coordinate click that would trigger one.
  `NEXUS_AGY_CONFIRM=off` in the MCP server environment turns confirmation off entirely (default: on).
- **Clipboard**: saved in all its formats and restored; the text put there is excluded from Win+V history and cloud
  clipboard. Used only as a last resort for typing (multi-line or more than 300 characters).
- **Shared with the other desktop agents of the PC**: foreground token (`%USERPROFILE%\.nexus\foreground.lock`) and
  emergency stop (Ctrl+Alt+Shift+Esc, `%USERPROFILE%\.nexus\stop`), the same file protocols as
  [NexusWindows for Claude](https://github.com/pironjulien/claude-windows-computer-use#working-alongside-other-agents).

## Architecture

| Path | Role |
| --- | --- |
| `client/mcp_server.py` | MCP server `nexus-computer` (stdio), started by `scripts/start-computer-mcp.ps1` |
| `client/computer_client.py` | Windows engine: windows, UI Automation, Win32 messages, capture, actions and read-back |
| `client/uia_fast.py`, `client/win32_controls.py` | One-round-trip UI Automation reads, native control messages |
| `client/physical_input.py`, `client/agent_guard.py`, `client/emergency_stop.py` | The user's presence (Raw Input), batch guard, shared emergency stop |
| `client/foreground_lock.py`, `client/garde_fous.py`, `client/garde-fous.json` | Shared foreground token and guard-rail policy, common to the author's desktop agents (also used by NexusWindows for Claude). Vendored in the public copy; in the author's setup they live in a sibling `shared` folder |
| `plugins/nexus-computer/` | Antigravity plugin and the agent guide (`SKILL.md`) |
| `tests/` | Unit tests (pytest) and the real desktop validation |

## Install

Requirements: Windows 10 or 11, PowerShell 7, [uv](https://docs.astral.sh/uv/) (installed by `install.ps1` through
winget if missing).

```powershell
git clone https://github.com/pironjulien/antigravity-windows-computer-use.git
cd antigravity-windows-computer-use
pwsh -NoProfile -File install.ps1
```

The Python environment, logs and screenshots live in `%USERPROFILE%\.nexusagy` (outside the clone). Then declare
the server in Antigravity's `mcp_config.json`:

```json
{
  "mcpServers": {
    "nexus-computer": {
      "command": "pwsh",
      "args": ["-NoProfile", "-File", "C:/path/to/antigravity-windows-computer-use/scripts/start-computer-mcp.ps1"]
    }
  }
}
```

The agent guide is `plugins/nexus-computer/skills/nexus-computer/SKILL.md`.

## Checks

```powershell
pwsh -NoProfile -File test.ps1         # offline: ruff, Pyright, pytest
pwsh -NoProfile -File test.ps1 -Full   # plus the real desktop validation on its own Win32, WinForms and WPF windows
```

The real validation shows its test windows without activation and closes them at the end; real mouse and keyboard
checks run only when the PC has been idle for 120 s, otherwise they are reported as skipped.

## Limits

- Windows only. Tool descriptions, replies and code comments are in French.
- Keyboard input is refused in UWP/WinUI and Chromium, and Ctrl/Alt shortcuts in WPF, where it cannot be done in the
  background; for web pages, [NexusBrowser](https://github.com/pironjulien/chrome-computer-use) is more reliable.
- An effect with nothing readable stays `~` (not verified).

## Licence

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 Julien Piron.
