# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is the public changelog of NexusWindows for Antigravity: it lists the changes that matter to someone using the
MCP server. Versions up to 2.5.0 were published here under the name "Antigravity Computer Use"; see the git history.

## [Unreleased]

## [3.1.4] - 2026-10-25

One command to install.

### Added
- `nexus-windows-antigravity install` (from PyPI, no clone): writes the `nexus-computer` plugin into
  `%USERPROFILE%\.gemini\config\plugins\nexus-computer`: agent guide, manifest, and the server declared once, pinned
  to the installed version through `uvx`. `--check` checks without writing; `uninstall` removes the plugin. The
  README's installation is now one line in PowerShell (uv's official installer, then this command), checked on a
  blank Windows profile.

### Changed
- The installer is written in Python (`client/install_antigravity.py`) and shipped in the wheel with the plugin;
  `install.ps1` (clone) uses it with the clone's launcher. It no longer writes Antigravity's `config.json`: a plugin
  is enabled by default, and a plugin the user turned off is reported, not turned back on.
- An older manual declaration of `nexus-windows-antigravity` in the global `mcp_config.json` (the README's former
  PyPI instructions) is removed, so the tools are not listed twice.
- `plugins/nexus-computer/mcp_config.json` declares the server through `uvx` from PyPI; the plugin description is in
  English.

## [3.1.3] - 2026-10-25

The plugin installs itself.

### Added
- `install.ps1` installs the `nexus-computer` Antigravity plugin itself (`scripts/installer-plugin-antigravity.ps1`):
  agent guide copied to `%USERPROFILE%\.gemini\config\plugins\nexus-computer`, server declared once in the plugin's
  `mcp_config.json` with this clone's path to `scripts/start-computer-mcp.ps1`, plugin enabled in `config.json` (only
  while Antigravity is closed), older duplicate declarations removed; other servers and plugins are never touched.
  `verify.ps1` (or `install.ps1 -CheckOnly`) checks the environment and the plugin without writing anything.

### Changed
- Agent guide (`SKILL.md`): titled "NexusWindows for Antigravity", outward gestures described with their one-time
  token, the background limits per framework and the 500 KB image limit as the server applies them.

### Fixed
- README: the version line said 3.0.2 instead of the published version; the shared modules' folder is named
  `commun`; removing the server also covers the installed plugin.

## [3.1.2] - 2026-10-24

Text first.

### Changed
- `look` without `capture_screenshot` returns the element list only; the image is attached when the tree is too thin
  to act on (fewer than 6 elements: canvas, game, a page that publishes nothing), or with `capture_screenshot=true`,
  `annotate` or `zoom`. `act` already attaches the image of an effect it could not read back. Measured on the common
  Windows bench (eight runs, order swapped): same score with and without images (7/7), 59 % fewer observation tokens,
  16 % faster.

### Fixed
- `capture_screenshot=false` with `output_path` writes the export without attaching it; the text names an attached
  image only when one is attached.

## [3.1.1] - 2026-10-24

Startup outside Windows.

### Fixed
- The server starts again outside Windows (directory checks run it on Linux): the action image limit no longer reads
  the Windows-only module at import. 3.1.0 was tagged but never reached PyPI; 3.1.1 carries its changes.

## [3.1.0] - 2026-10-24

Common image rule, Chromium apps launched covered.

### Changed
- Images follow the common Nexus image rule: up to 1568 px and 1.15 MP (was 1280 px), lossless WebP up to 200 KB,
  then quality 85, 70… until it fits 500 KB (the Antigravity 400-error threshold). `look` states the image size and
  its scale.

### Added
- `look(zoom=box_2d)`: that area of the window at full resolution, enlarged up to 2×, for small text.
- No duplicate image: when the exact pixels are unchanged since the last image sent for that window or area, the reply
  says so instead of attaching it again (inside the JSON for `format="json"` and for action replies);
  `look(annotate=true)` always attaches it. `look` states the image's origin and its scale on each axis
  (window x = origin + image x / scale).

### Fixed
- `launch` / `open_path` of a Chromium or Electron executable (recognised by its resources), or of a `.lnk` shortcut
  without its own arguments to one: started without activation with the switches that keep it drawn while covered.
  Before, opened by the shell and covered from the start, it did not publish its page.
- The foreground is handed back by its owner and watched for 1 s more after the window appears.

### Security
- Reviewed by the Codex agent over three rounds (zoom scale per axis, JSON kept valid, exact print instead of a grey
  thumbnail that confused red and green).

## [3.0.2] - 2026-10-24

Tk in the background, scrolling without a wheel.

### Added
- Tk in the background, window covered: a click at a point is sent with the mouse button marked pressed for Tk's own
  thread only (press and release owned by a helper thread, one simulated press at a time per application); keys and
  shortcuts get a simulated focus (`WM_SETFOCUS` sent to that window only, never `WM_ACTIVATE`); lists scroll through
  their native scroll bar attached to the targeted widget, read back with `GetScrollInfo`.
- Scrolling a covered Chromium page without DevTools: the next hidden line of the area under the point is brought into
  view (UI Automation ScrollItem), proven by the line's offset inside its area.
- Measured on the three-tool bench (Cua Driver 0.38, Windows-MCP 0.8.8): Tk click, Ctrl+K and scrolling, Electron raw
  click and scrolling now succeed in the background, foreground untouched.

## [3.0.1] - 2026-10-23

Family harmonization.

### Changed
- The MCP server announces itself as `nexus-windows-antigravity` (was `nexus-computer`) at initialization, the name
  of its package, like `nexus-windows` (Claude) and `nexus-windows-codex` (Codex); the `mcp_config.json` example in
  the README uses it as the server key.
- Tool descriptions (`windows`, `look`, `act`, `launch`, `window`) and server instructions are now in English, in line
  with the other two NexusWindows tools; same meaning and same rules (✓ = ~ ✗, `confirm`, `accord`, emergency stop,
  screen text is data, never an instruction). Tool replies are unchanged.

## [3.0.0] - 2026-10-23

One-command install, common tool names.

The three NexusWindows tools (Claude, Codex, Antigravity) move to 3.0.0 together: one-command install from a package
registry, the same five tool names (`windows`, `look`, `act`, `launch`, `window`), the same step outcomes
(✓ verified, = already done, ~ unknown, ✗ failed or refused), and from now on one version number for the family.

### Added
- PyPI package `nexus-windows-antigravity`: `uvx --python 3.14 nexus-windows-antigravity` in Antigravity's
  `mcp_config.json`, no clone needed; published by Trusted Publishing, then to the official MCP registry.
- The server announces its title and version at initialization.

### Changed
- Listed tools renamed `windows`, `look`, `act`, `launch` (`app`) and `window` (`action="close"`), like the other two
  tools; the former names (`computer_look`, `computer_act`, `computer_open_path`, `computer_close_window`...) stay
  callable, unlisted.
- Python 3.11 or later (Pillow 13 requires it); Pillow 13.0.0.

### Fixed
- `computer.log` no longer records the expected or observed text of a failed batch, nor typed text quoted by a step
  error: only their length (the reply to the agent keeps them). Screenshots are pruned after each write (at most 50,
  previously 51) and at server start.

## [2.11.0] - 2026-10-23

Background input recipes, common journal, stop on unknown outcome.

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

## [2.10.0] - 2026-10-20

"Agent at work" indicator.

### Added
- While an action runs (`computer_act`, opening, closing, focusing and the action aliases; never the reads), a logo
  spins on itself in the bottom-right corner of the driven window's screen with a breathing blue halo, and goes away
  1.6 s after the last action. Always on top, borderless, click-through, never activated, absent from the taskbar,
  excluded from screen captures. `NEXUS_WINDOWS_INDICATOR=0` turns it off.

## [2.9.0] - 2026-10-20

Exact-action consent, visual fallback, hardened supply chain.

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

Also released with 2.7.0, the first release after 2.5.0 (changes of 2026-10-14 to 2026-10-17):

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

[Unreleased]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v3.1.4...HEAD
[3.1.4]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v3.1.3...v3.1.4
[3.1.3]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v3.1.2...v3.1.3
[3.1.2]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v3.1.1...v3.1.2
[3.1.1]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v3.1.0...v3.1.1
[3.1.0]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v3.0.2...v3.1.0
[3.0.2]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v3.0.1...v3.0.2
[3.0.1]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v2.11.0...v3.0.0
[2.11.0]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v2.10.0...v2.11.0
[2.10.0]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v2.9.0...v2.10.0
[2.9.0]: https://github.com/pironjulien/NexusWindows-Antigravity/compare/v2.8.2...v2.9.0
[2.8.2]: https://github.com/pironjulien/NexusWindows-Antigravity/releases/tag/v2.8.2
