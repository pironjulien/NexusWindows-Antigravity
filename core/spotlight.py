#!/usr/bin/env python3
"""NexusAGY Desktop Spotlight Launcher & System Tray Companion Manager.

Provides background supervision, process control, and MCP integration for the Windows Spotlight bar.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIRECTORY = REPOSITORY_ROOT / "client"
SPOTLIGHT_SCRIPT_PATH = CLIENT_DIRECTORY / "spotlight_launcher.ps1"


def _find_pwsh() -> str:
    from shutil import which

    for candidate in ("pwsh.exe", "powershell.exe"):
        found = which(candidate)
        if found:
            return found
    return "powershell.exe"


def is_spotlight_running() -> bool:
    """Checks whether the Antigravity Spotlight companion is currently running."""
    if sys.platform != "win32":
        return False
    pwsh = _find_pwsh()
    try:
        output = subprocess.check_output(
            [
                pwsh,
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*spotlight_launcher.ps1*' } | Select-Object -ExpandProperty ProcessId",
            ],
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=4.0,
        )
        return bool(output.strip())
    except (subprocess.SubprocessError, OSError):
        return False


def start_spotlight_background(show_immediately: bool = False) -> bool:
    """Launches the Antigravity Spotlight companion in the background."""
    if not SPOTLIGHT_SCRIPT_PATH.exists():
        return False

    if is_spotlight_running():
        return True

    pwsh = _find_pwsh()
    cmd = [pwsh, "-NoProfile", "-WindowStyle", "Hidden", "-File", str(SPOTLIGHT_SCRIPT_PATH)]
    if show_immediately:
        cmd.append("-ShowImmediately")

    try:
        subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def stop_spotlight() -> bool:
    """Terminates any active Antigravity Spotlight companion instances."""
    if sys.platform != "win32":
        return False
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*spotlight_launcher.ps1*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }",
            ],
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=5.0,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def check_syntax() -> bool:
    """Validates the PowerShell script syntax and .NET assembly dependencies."""
    if not SPOTLIGHT_SCRIPT_PATH.exists():
        return False
    try:
        res = subprocess.run(
            ["pwsh.exe", "-NoProfile", "-File", str(SPOTLIGHT_SCRIPT_PATH), "-CheckOnly"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10.0,
        )
        return res.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="NexusAGY Desktop Spotlight Companion Manager")
    parser.add_argument("--status", action="store_true", help="Check if Spotlight is running")
    parser.add_argument("--start", action="store_true", help="Start Spotlight companion in background")
    parser.add_argument("--stop", action="store_true", help="Stop Spotlight companion")
    parser.add_argument("--check", action="store_true", help="Validate Spotlight syntax and assemblies")

    args = parser.parse_args()

    if args.check:
        ok = check_syntax()
        print(f"Spotlight Dependencies Check: {'OK' if ok else 'FAIL'}")
        return 0 if ok else 1

    if args.status:
        running = is_spotlight_running()
        print(f"Spotlight Running: {running}")
        return 0 if running else 1

    if args.start:
        ok = start_spotlight_background()
        print(f"Spotlight Started: {ok}")
        return 0 if ok else 1

    if args.stop:
        ok = stop_spotlight()
        print(f"Spotlight Stopped: {ok}")
        return 0 if ok else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
