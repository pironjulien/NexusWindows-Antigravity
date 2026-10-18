# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is the public changelog of NexusWindows for Antigravity: it lists the changes that matter to someone using the
MCP server. Versions up to 2.5.0 were published here under the name "Antigravity Computer Use"; see the git history.

## [Unreleased]

### Added

- Every MCP tool has a readable `title` in its annotations, next to its four hints.
- The server starts and lists its tools outside Windows (as MCP directories such as Glama check it, in a Linux
  container); there, each tool call answers that Windows is required. Windows-only dependencies (`comtypes`,
  `uiautomation`) are installed on Windows only.
- GitHub Actions: `test.ps1` on Windows and the startup test on Linux, with a Tests badge; `glama.json`.
- README: Privacy section.

### Changed

- Shared guard-rail policy updated (same file as the Claude, Codex and Android editions): calling ("appeler",
  "call") now needs `confirm: true` too.
- `SECURITY.md`: private vulnerability reporting.

## [2.8.2] - 2026-10-18

### Changed
- The guard-rail lists (protected surfaces, password managers, confirmation patterns, payment and formatting
  contexts, action and non-action roles) are read from a policy file shared with NexusWindows for Claude
  (`client/garde-fous.json`, read by `client/garde_fous.py`) instead of being hard-coded. Behaviour unchanged,
  checked value by value against 2.8.1. If the policy cannot be read, the server refuses to start.
- Repository renamed to `antigravity-windows-computer-use` and README rewritten as NexusWindows for Antigravity.

## [2.8.1] - 2026-10-18

### Added
- Password managers (KeePass, KeePassXC, Bitwarden, 1Password, Dashlane, NordPass, RoboForm, LastPass, matched by
  process prefix) are hard-blocked: never looked at, read through UI Automation, captured or driven. A full-screen
  capture is refused while one of them is shown.
- Making a repository public needs confirmation ("Make public", "Change to public", "Rendre public"...).
- An explicit order from the user counts as confirmation (`confirm: true` directly); only the agent's own initiative
  asks first.

## [2.8.0] - 2026-10-18

### Fixed
- Enter, Space and `submit` no longer get around confirmation: a key is judged on what it would trigger (default
  button of the window, focused button, send button next to the field; Ctrl+Enter: any action button of the window;
  Alt+letter: the button or menu of that access key). Shift+Enter and Alt+Enter stay free.
- A coordinate click outside any UI Automation control is checked against the short text read under the point
  before the real mouse is used.

### Added
- More irreversible actions under confirmation: uninstall, format a drive, reset, factory reset, cancel a
  subscription, delete or close an account, erase data.
- Generic verbs judged by the window title: validate/confirm/OK in a payment or money-transfer window, start/OK in a
  format dialog.
- MCP tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`).

### Changed
- MCP SDK 1.30 → 2.3.0; `comtypes` declared as a dependency.
- The UI Automation read also returns the access key and the keyboard focus, in the same round trip.

## [2.7.0] - 2026-10-17

### Changed
- Autonomy first: banking and finance applications, password fields (filled, masked value never read back),
  Chrome/Edge (with a note that a browser bridge is more reliable for the web) and any existing path in
  `computer_open_path` are allowed. The sign-in screen, lock screen and UAC prompt stay refused.
- Confirmation limited to actions that reach a third party or cost money (pay, buy, order, transfer money, send,
  publish, delete permanently, empty the trash), in one list (`CONFIRM_PATTERNS`).
- `NEXUS_AGY_CONFIRM=off` in the MCP server environment turns confirmation off (default: on).
- Windows activation protocols (`ms-settings:`, `shell:`) open through `computer_open_path`; web addresses are
  refused with a pointer to a browser tool.

## Earlier changes since 2.5.0 (2026-10-14 to 2026-10-17)

### Added
- Five listed MCP tools (`computer_list_windows`, `computer_look`, `computer_act`, `computer_open_path`,
  `computer_close_window`); the older tool names stay callable as unlisted aliases.
- Designed for Gemini: one-line `next` in every reply, compact look (one line per element), WebP image of the window
  when an effect was not read back, refusal of a batch resent unchanged without a new look.
- Background techniques per UI family: direct Win32 messages, UI Automation read in one cross-process round trip,
  posted keys in Win32, WinForms and WPF; real input only as a fallback with `foreground=True`.
- Read-back after every action (`verified`), postconditions (`expect`), `check`, `uncheck`, `select` and `menu`
  steps.
- The user's physical input detected through Raw Input: pause before real input, stop if the user takes over.
- Shared foreground token and emergency stop (Ctrl+Alt+Shift+Esc) with the other desktop agents of the PC.
- Guards in the code: named window required, ambiguous labels refused with the candidates, foreground read back
  before every `SendInput`, clipboard saved and restored.

### Removed
- The Chrome browser bridge, moved to its own project, NexusBrowser
  ([chrome-computer-use](https://github.com/pironjulien/chrome-computer-use)).
- The floating companion window and the former multi-adapter layout of 2.5.0.
