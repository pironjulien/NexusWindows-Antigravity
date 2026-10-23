# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is the public changelog of NexusWindows for Antigravity: it lists the changes that matter to someone using the
MCP server. Versions up to 2.5.0 were published here under the name "Antigravity Computer Use"; see the git history.

## [Unreleased]

## [2.11.0] - 2026-10-23 — Background input recipes, common journal, stop on unknown outcome

### Added
- Common journal shared by the three NexusWindows tools (Claude, Codex, Antigravity): every action call (opening,
  closing, scrolling, dragging, refusals, stops, confirmations) writes one line per batch step to
  `%LOCALAPPDATA%\NexusJournal\windows\antigravity\` (or `NEXUS_JOURNAL_HOME`), `~` when the effect was not read
  back. It never contains screen text.
- Coordinate clicks and the mouse wheel in the background in Win32 and WinForms: messages posted to the deepest child
  under the point (foreground, cursor and clipboard untouched). Sent once, never replayed with the real mouse.
  Coordinate clicks are also posted in covered Chromium/Electron windows.
- Ctrl/Shift shortcuts in the background in Win32 and WinForms: keys posted with a simulated keyboard state on the
  target's thread only, restored once the target has processed them (Ctrl+S never becomes S); Alt is refused.
- Right-click and double-click in Win32 and WinForms posted at the element's centre: a WinForms context menu opens
  without touching the foreground, and its command is then picked by label.
- Single-line fields in Chromium/Electron set in the background through UI Automation Value (input events fired);
  never for multi-line fields or rich editors, which UI Automation cannot tell apart.
- Chromium/Electron without real activation: `<select>` picked by typing its label, appending to rich editors and
  multi-line fields, keys and Ctrl shortcuts. Focus is taken and proved just before sending; never with a
  validating Enter or a line break.
- Covered Chromium/Electron windows publish their accessibility changes before each read: fields and the options of
  an open list are no longer missing.
- Mouse wheel in the background in Chrome, Edge and Electron through the window's own DevTools port. Nothing is sent
  unless the port belongs to the window's exact process, the page is proved to be the one shown in that window and
  exactly one render surface matches its viewport; one input event only, an unacknowledged one is an unknown outcome,
  never replayed. New dependency: `websocket-client`.
- Mouse wheel at a point in WPF, UWP and WinUI (which ignore posted wheel messages) by semantic scrolling
  (ScrollPattern) of the smallest scrollable container under the point; ambiguity refuses, a real end (0/100 %) sends
  nothing, and the position read back decides whether it is verified.

### Fixed
- `computer_act` stops a batch as soon as a step stays unverified, before sending the next action: a
  validation can no longer follow a click whose effect is unknown. No automatic replay; the result is
  `unverified`, `success: None`, and says the rest was not sent. A true `expect`, an already-satisfied state or a
  verified wait still lets the batch go on.
- A step whose control was already in the wanted state no longer keeps the `already` mark when its final
  postcondition is unreadable or false: it reports `~` or `✗` and the batch stops.
- Partial send (one message posted, then a refusal) is an unknown outcome: never a physical fallback or a second
  technique on top of it.
- WinForms push buttons: `BN_CLICKED` is posted first (a synchronous UI Automation Invoke blocked on a modal dialog
  and the fallback opened it twice); after an unverified `BN_CLICKED`, no second technique.
- List items outside Win32/WinForms are selected by UI Automation Select only (Invoke then Select selected twice in
  Electron); a Chromium item still read as unselected afterwards is an unknown outcome, never a physical click on top.
- Posted double-clicks and right-clicks are verified only by structural evidence (title, application windows, size);
  a selection made by the first click no longer passes for a verified double-click. Window size is proved by its
  rectangle, never by comparing two screenshots.
- Posted clicks in windows that are not DPI-aware (or system-DPI-aware) are converted to logical pixels: at 125 %, a
  double-click on a WinForms list landed one row too low.
- A posted double-click on a covered WinForms control is refused before sending; the real mouse takes over only when
  `foreground=true` is allowed.
- Physical wheel is proved by the scroll position read back from the targeted container, never by the window title
  or the tree; without a readable container the outcome is unverified.
- DevTools wheel recognises tabbed Edge titles ("page - Profile 1 – Microsoft Edge").
- `computer_open_path` resolves a bare program name (`notepad.exe`, `mspaint`) like Start > Run (PATH including Store
  aliases, then App Paths) instead of answering "path not found".
- Text targets: an editable ComboBox and its same-named child Edit (the "File name:" box of Open/Save dialogs) are no
  longer ambiguous; the text goes to the Edit.
- `computer_close_window` reports a closed window as verified (`✓`) when it is destroyed, or was visible and is now
  hidden; the wait is 2 s for UWP apps. A lost COM reply stays `~`, and `WM_CLOSE` is never replayed.
- The foreground is given back by the window that holds it, never taken from a window the user has just chosen.
- Emergency stop: the remaining time is now capped at the 120 s hold (floating-point rounding could report
  120.00000000000003 s).

### Changed
- "Agent at work" indicator: the breathing halo is gone; only the logo spins, with its drop shadow.
- Checked on the common bench of the three NexusWindows tools (Claude, Codex, Antigravity): canvas click, wheel and
  Ctrl+K in Win32/WinForms now pass, and double actions are gone.
- Development tools and CI actions updated: ruff 0.17.1, pyright 1.1.414, `actions/checkout` v7.0.1,
  `astral-sh/setup-uv` v10.3.0 (pinned by hash).

## [2.10.0] - 2026-10-20 — "Agent at work" indicator

### Added
- While an action runs (`computer_act`, opening, closing, focusing and the action aliases; never the reads), a logo
  spins on itself in the bottom-right corner of the driven window's screen with a breathing blue halo, and goes away
  1.6 s after the last action. Always on top, borderless, click-through, never activated, absent from the taskbar,
  excluded from screen captures. `NEXUS_WINDOWS_INDICATOR=0` turns it off.

## [2.9.0] - 2026-10-20 — Exact-action consent, visual fallback, hardened supply chain

### Added

- **Consent bound to the exact action** for outward gestures (paying, sending, publishing, transferring, calling):
  besides `confirm: true`, a single-use `accord` token (10 minutes) returned by the first refusal, which describes
  the exact action. It binds the tool, the gesture, the target, the actual contents of the window's editable fields
  (read again at execution, passwords excluded) and the window; any change voids it. Also covers validation keys
  (Enter, Ctrl+Enter, Space, Alt shortcuts), coordinate clicks and `type_text(submit=True)`. Local destructive
  actions (permanent deletion, formatting, uninstalling, resetting) keep `confirm: true` alone.
- **Visual fallback**: `target` accepts coordinates (`"@150,200"`, `"150, 200"`, `"coords:150,200"`) and Gemini
  boxes (`"[ymin, xmin, ymax, xmax]"`, `"box_2d:[...]"`); a step whose label is missing from the UI Automation
  tree falls back to its coordinates; `computer_look` says when a window exposes no UI Automation element.
- Blind paste guard: a batch may not chain a paste (Ctrl+V) and a validation; the pasted text is read back first.
- OpenSSF Scorecard workflow and badge; Dependabot for GitHub Actions and uv (7-day cooldown); GitHub Actions
  pinned by commit SHA without persisted credentials (zizmor clean).
- Every MCP tool has a readable `title` in its annotations, next to its four hints.
- The server starts and lists its tools outside Windows (as MCP directories such as Glama check it, in a Linux
  container); there, each tool call answers that Windows is required. Windows-only dependencies (`comtypes`,
  `uiautomation`) are installed on Windows only.
- GitHub Actions: `test.ps1` on Windows and the startup test on Linux, with a Tests badge; `glama.json`.
- README: Privacy section.
- README: demo (animated WebP, GIF fallback) recorded with this server's own `computer_act` on neutral test
  windows: one batch of five steps in a window behind another, the user's window untouched.

### Changed

- Repository renamed to `pironjulien/NexusWindows-Antigravity`; GitHub redirects the old address.
- Shared guard-rail policy updated (nexus-shared 6d82bbb): erasing, resetting or formatting the whole device now
  needs confirmation too; "erase everything" counts only on a reset screen.
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
