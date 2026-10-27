# NexusWindows for Antigravity

<!-- mcp-name: io.github.pironjulien/nexus-windows-antigravity -->

<img src="https://raw.githubusercontent.com/pironjulien/NexusWindows-Antigravity/main/plugins/nexus-computer/logo.png" alt="NexusWindows icon" width="96">

[![Release](https://img.shields.io/github/v/release/pironjulien/NexusWindows-Antigravity)](https://github.com/pironjulien/NexusWindows-Antigravity/releases)
[![Tests](https://github.com/pironjulien/NexusWindows-Antigravity/actions/workflows/tests.yml/badge.svg)](https://github.com/pironjulien/NexusWindows-Antigravity/actions/workflows/tests.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/pironjulien/NexusWindows-Antigravity/badge)](https://scorecard.dev/viewer/?uri=github.com/pironjulien/NexusWindows-Antigravity)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/pironjulien/NexusWindows-Antigravity/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/nexus-windows-antigravity)](https://pypi.org/project/nexus-windows-antigravity/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://github.com/pironjulien/NexusWindows-Antigravity/blob/main/pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-server-7ee2a8)](https://modelcontextprotocol.io)
[![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4)](#installation)

[![NexusWindows: Windows computer use for AI agents, in the background. Works with Claude, Codex and Antigravity.](https://raw.githubusercontent.com/pironjulien/NexusWindows-Antigravity/main/docs/assets/banner.webp)](https://julienpiron.fr/nexuswindows/)

![NexusWindows for Antigravity: an AI agent fills and submits a form through act in a window that stays behind another one, five steps read back](https://raw.githubusercontent.com/pironjulien/NexusWindows-Antigravity/main/docs/assets/demo.webp)

**Windows computer use for Antigravity, in the background.** An MCP server (`nexus-windows-antigravity`) that lets Google
Antigravity (Gemini) see and operate Windows desktop applications while the user keeps their mouse, keyboard and
foreground window. Built for a fast model: one look, then one batch of steps with label targets, and every reply
says what to do next.

Version 3.3.0 · Windows 10/11 · Python 3.11+ · MIT licence

Part of the Nexus family: [NexusWindows](https://julienpiron.fr/nexuswindows/)
([Claude](https://github.com/pironjulien/NexusWindows-Claude) ·
[Codex](https://github.com/pironjulien/NexusWindows-Codex) ·
[Antigravity](https://github.com/pironjulien/NexusWindows-Antigravity)),
[NexusBrowser](https://julienpiron.fr/nexusbrowser/) ([repo](https://github.com/pironjulien/NexusBrowser)),
[NexusAndroid](https://julienpiron.fr/nexusandroid/) ([repo](https://github.com/pironjulien/NexusAndroid)).
Project page: [julienpiron.fr/nexuswindows](https://julienpiron.fr/nexuswindows/).

## Why

Screenshot-and-click computer use moves the real cursor and brings windows to the front, so the person at the PC has
to stop working while the agent acts. Most Windows applications can be driven without that: native controls accept
window messages and modern frameworks expose UI Automation. This server acts in the background first, reads the
effect back, and only falls back to the real mouse or keyboard when the step allows it (`foreground=True`).

## NexusWindows family

Three MCP servers, one per agent, built separately because each model needs its tools shaped for it, with the same
promise: the user keeps their mouse, keyboard and foreground window, and every action is read back.

| | Claude | Codex | Antigravity |
|---|---|---|---|
| Install | `uvx --python 3.14 nexus-windows-claude` | `npx -y nexus-windows-codex` | `uvx --python 3.14 nexus-windows-antigravity` |
| Package | [PyPI](https://pypi.org/project/nexus-windows-claude/) | [npm](https://www.npmjs.com/package/nexus-windows-codex) | [PyPI](https://pypi.org/project/nexus-windows-antigravity/) |
| Tools | `windows` `look` `act` `launch` `window`, plus `notifications` and `logs` | `windows` `look` `act` `launch` `window` | `windows` `look` `act` `launch` `window` |
| Repository | [NexusWindows-Claude](https://github.com/pironjulien/NexusWindows-Claude) | [NexusWindows-Codex](https://github.com/pironjulien/NexusWindows-Codex) | [NexusWindows-Antigravity](https://github.com/pironjulien/NexusWindows-Antigravity) |

Every step reports ✓ verified, = already done, ~ unknown (never replayed) or ✗ failed or refused. The three share the
guardrail policy, the foreground token, the emergency stop (Ctrl+Alt+Shift+Esc), a common journal format and a common
bench.

## Installation

Requirements: Windows 10 or 11 and [Google Antigravity](https://antigravity.google/download). Nothing else to
install by hand: the command below installs [uv](https://docs.astral.sh/uv/) with winget (Windows' own package
manager, package `astral-sh.uv`), which brings Python 3.14 and the server from
[PyPI](https://pypi.org/project/nexus-windows-antigravity/). No script is downloaded and run.

1. Open **PowerShell** (Start menu, type `PowerShell`, Enter).
2. Paste this line and press Enter:

   ```powershell
   winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements; $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine'); uvx --python 3.14 nexus-windows-antigravity@latest install
   ```

   (uv already installed: `uvx --python 3.14 nexus-windows-antigravity@latest install` is enough.)

3. Restart Antigravity. The `nexus-computer` plugin appears under **Customizations > Installed**, with its five tools
   and the agent guide. Ask for example: *"In Notepad, behind my window, type a shopping list and save it on the
   desktop."*

What the `install` command does: it writes the `nexus-computer` plugin into
`%USERPROFILE%\.gemini\config\plugins\nexus-computer`, the folder Antigravity loads plugins from: the agent guide
([`SKILL.md`](https://github.com/pironjulien/NexusWindows-Antigravity/blob/main/plugins/nexus-computer/skills/nexus-computer/SKILL.md)),
the plugin manifest, and `mcp_config.json`, which declares the server once at its latest version
(`uvx --python 3.14 nexus-windows-antigravity@latest`): each Antigravity start runs the newest published version. It
removes an older manual declaration of the same server
from the global `mcp_config.json`; other servers, plugins and Antigravity settings are never touched. A plugin is
enabled by default; if you turned it off, it says so and leaves your choice.

- **Update**: automatic, at the next Antigravity start. Installed with 3.1.4 to 3.1.7 (pinned version): run the line
  once more.
- **Check**: `uvx --python 3.14 nexus-windows-antigravity install --check` (writes nothing).
- **Remove**: `uvx --python 3.14 nexus-windows-antigravity uninstall`.

<details>
<summary>Without the plugin: declare the server yourself</summary>

Edit `%USERPROFILE%\.gemini\config\mcp_config.json` (in the Antigravity IDE: agent panel **…** > **MCP Servers** >
**Manage MCP Servers** > **View raw config**):

```json
{
  "mcpServers": {
    "nexus-windows-antigravity": {
      "command": "uvx",
      "args": ["--python", "3.14", "nexus-windows-antigravity"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

The agent then has the tools but not the guide; the plugin is the recommended way.
</details>

<details>
<summary>From a clone (development)</summary>

With [Git](https://git-scm.com/) and [PowerShell 7](https://aka.ms/powershell):

```powershell
git clone https://github.com/pironjulien/NexusWindows-Antigravity.git
cd NexusWindows-Antigravity
pwsh -NoProfile -File install.ps1
```

The Python environment, logs and screenshots then live in `%USERPROFILE%\.nexusagy` (outside the clone), and the
plugin's `mcp_config.json` starts the server from the clone (`scripts/start-computer-mcp.ps1`). `verify.ps1` (or
`install.ps1 -CheckOnly`) checks the environment and the plugin without changing anything.
</details>

## Tools

Five listed MCP tools, named like the other NexusWindows tools (Claude, Codex); the older names (`computer_look`,
`computer_act`, `computer_click`...) stay callable as unlisted aliases.

| Tool | Purpose |
| --- | --- |
| `windows` | Application windows (`by_app=true`: grouped by application) |
| `look` | One line per element `[N] role « name » = « value » states @x,y`, without bringing the window forward; the image only when the tree is too thin, or on request (text first: 59 % fewer tokens, same score) |
| `act` | Several steps in one call (click, type, check, uncheck, select, menu, keys...), each read back: ✓ = ~ ✗ |
| `launch` | Open an application, document, folder, script or shortcut; the opening is read back |
| `window` | `action="close"`: close a window (UI Automation, then `WM_CLOSE`) |

Tool descriptions, server instructions, tool and parameter names are in English; tool replies are in French.

## What it does

- **Designed for Gemini**: golden rule *look, then act in one batch with label targets*; every action reply carries
  a one-line `next` (✓ done · = already done, do not redo · ~ effect not seen, look at the attached image · ✗ failure,
  cause and what to try) and, when the effect was not read back, a WebP image of the window (common Nexus image rule:
  ≤ 2000 px and 2.56 MP, lossless up to 500 KB, never over 500 KB; not attached again when the screen is unchanged;
  `look(zoom=box_2d)` enlarges an area for small text). A
  batch identical to one sent in the last 10 s on the same window without a `look` in between is
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
  A batch stops at the first failed or unverified step, before sending the next action, with no automatic replay.
  A verified postcondition establishes the effect and allows the batch to continue; an unknown effect requires
  observation before preparing the remaining steps.
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
- **Agent at work**: while an action runs (`act`, opening, closing, focusing and the action aliases; never
  the reads), a small logo spins on itself in the bottom-right corner of the driven window's screen, like a game
  loading screen (the logo and its shadow only, no halo), and goes away 1.6 s after the last action. Always on top, borderless,
  click-through, never activated, absent from the taskbar and excluded from screen captures (`busy_indicator.py`).
  `NEXUS_WINDOWS_INDICATOR=0` turns it off.
- **Shared with the other desktop agents of the PC**: foreground token (`%USERPROFILE%\.nexus\foreground.lock`) and
  emergency stop (Ctrl+Alt+Shift+Esc, `%USERPROFILE%\.nexus\stop`), the same file protocols as
  [NexusWindows for Claude](https://github.com/pironjulien/NexusWindows-Claude#working-alongside-other-agents).

## Common bench of the NexusWindows family (October 25, 2026)

The three editions are measured together by the family's common bench: 55 tasks on lab windows (Win32, WinForms,
WPF, Tk, Electron and Edge, plus launching an application behind a maximized window), three rounds each, every lab
window covered by another window, run only while nobody uses the PC (a run stops and is not counted when the user
comes back). The effect is judged by the application itself, never by the tool's report. "Without intrusion" counts an
effect only when the user's foreground window and cursor stayed untouched.

| 165 trials (55 tasks × 3) | Claude 3.2.2 | Antigravity 3.1.7 | Codex 3.1.4 |
|---|---|---|---|
| Exact effect | 120 | 119 | 120 |
| Exact effect without intrusion | 114 | 113 | 113 |
| False success (reported done, the app got nothing) | 0 | 3 | 0 |
| Median / p95 time per task | 695 / 5179 ms | 702 / 3063 ms | 402 / 2909 ms |

The three false successes of this edition (Ctrl+K in Electron) and its missed WinForms context menu are fixed in
3.2.2. In this run the Electron lab published no page once covered, so every Electron task failed for all three
tools; the lab is fixed and Electron will count at the next run. A comparison with
[Cua Driver](https://github.com/trycua/cua) and [Windows-MCP](https://github.com/CursorTouch/Windows-MCP) is in
[NexusWindows for Claude](https://github.com/pironjulien/NexusWindows-Claude#side-by-side-with-cua-driver-and-windows-mcp-october-23-2026).

## Architecture

| Path | Role |
| --- | --- |
| `client/mcp_server.py` | MCP server `nexus-windows-antigravity` (stdio), started by `scripts/start-computer-mcp.ps1` |
| `client/computer_client.py` | Windows engine: windows, UI Automation, Win32 messages, capture, actions and read-back |
| `client/uia_fast.py`, `client/win32_controls.py` | One-round-trip UI Automation reads, native control messages |
| `client/physical_input.py`, `client/agent_guard.py`, `client/emergency_stop.py` | The user's presence (Raw Input), batch guard, shared emergency stop |
| `client/foreground_lock.py`, `client/garde_fous.py`, `client/garde-fous.json` | Shared foreground token and guard-rail policy, common to the author's desktop agents (also used by NexusWindows for Claude). Vendored in the public copy; in the author's setup they live in a sibling `commun` folder |
| `plugins/nexus-computer/` | Antigravity plugin and the agent guide (`SKILL.md`), installed by `nexus-windows-antigravity install` (`client/install_antigravity.py`) |
| `tests/` | Unit tests (pytest) and the real desktop validation |

## Privacy

NexusWindows for Antigravity runs entirely on your PC. It has no account, no telemetry and no analytics. Its only network
request of its own is a version check: at most once a day, a GET of `https://pypi.org/pypi/nexus-windows-antigravity/json`
(nothing about you or your PC is sent); `NEXUS_UPDATE_CHECK=off` in the server environment turns it off.

- **What it reads**: window titles, the accessibility tree and window images of the applications the agent works
  in, only when a tool is called. Password managers are neither read nor driven.
- **Where it goes**: tool results are returned to Antigravity, which may send them to Google under its own privacy
  policy; this server sends nothing anywhere else.
- **What it stores**, under `~/.nexusagy/`: the Python environment (clone install only; `uvx` keeps its own in the
  uv cache), an action log `computer.log` (action, method,
  window, duration, outcome and short details such as a target label, coordinates, key names, a menu path or the
  number of characters typed, never the typed or expected text; rotated at 5 MB, three backups) and screenshots (at
  most 50 after each capture; those older than 24 hours are purged at the next capture and at server start, so a
  stopped server can leave its last screenshots until it starts again). Under `~/.nexus/`: the shared foreground token and emergency-stop state,
  and `status/windows-antigravity.json` (installed version, latest version, time of the last check), read by the
  Nexus app.
  Under `%LOCALAPPDATA%\NexusJournal\windows\antigravity\` (or `NEXUS_JOURNAL_HOME`): a short monthly JSONL journal,
  in the same format as the other NexusWindows tools (app executable name, action, technique, outcome, duration,
  whether the foreground was used, and the first words of an error, cut before any quote, colon or bracket); never
  typed text, screen text, labels, titles or paths. The server never deletes it.
- **Removing it**: `uvx --python 3.14 nexus-windows-antigravity uninstall` (or remove the server from Antigravity's
  MCP settings), then delete `~/.nexusagy/`, `~/.nexus/status/windows-antigravity.json` (and
  `%LOCALAPPDATA%\NexusJournal`).

Questions or concerns: open an issue on this repository.

## Limits

- Windows only. Tool descriptions are in English; tool replies and code comments are in French.
- In the background, keyboard input is refused in UWP/WinUI and Firefox, and Ctrl/Alt shortcuts in WPF; Tk gets keys
  and shortcuts through a simulated focus (`WM_SETFOCUS` to that window only), clicks sent with the mouse button marked
  pressed for its thread, and lists scrolled through their native scroll bar;
  Chromium/Electron receives keys, shortcuts and typing through a simulated activation, checked by read-back (`~` if
  nothing changes). For web pages, [NexusBrowser](https://github.com/pironjulien/NexusBrowser) is more reliable.
- An effect with nothing readable stays `~` (not verified).
- Still refused in the background, with the cause read in each toolkit's source: WPF clicks at a point, wheel and
  shortcuts (WPF drops a click while the real cursor is not over its window); a wheel on a covered Chromium or Tk
  canvas (both route it to the window on top); a click at a point of a covered Electron page that has gone `hidden`.

## Development

```powershell
pwsh -NoProfile -File test.ps1         # offline: ruff, Pyright, pytest
pwsh -NoProfile -File test.ps1 -Full   # plus the real desktop validation on its own Win32, WinForms and WPF windows
```

The real validation shows its test windows without activation and closes them at the end; real mouse and keyboard
checks run only when the PC has been idle for 120 s, otherwise they are reported as skipped.

## Licence

MIT, see [LICENSE](https://github.com/pironjulien/NexusWindows-Antigravity/blob/main/LICENSE). Copyright (c) 2026 Julien Piron.
