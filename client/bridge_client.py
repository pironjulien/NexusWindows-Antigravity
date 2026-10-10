"""Shared authenticated transport for NexusAGY browser clients."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
NATIVE_HOST_DIRECTORY = REPOSITORY_ROOT / "native-host"
BRIDGE_SERVER_PATH = NATIVE_HOST_DIRECTORY / "bridge_server.py"
API_URL = "http://127.0.0.1:9225/api/command"
STATUS_URL = "http://127.0.0.1:9225/api/status"

sys.path.insert(0, str(NATIVE_HOST_DIRECTORY))

try:
    from bridge_security import TOKEN_HEADER, load_or_create_token  # noqa: E402
except ImportError:
    TOKEN_HEADER = "X-Nexus-Token"

    def load_or_create_token() -> str:
        return ""


def authentication_headers() -> dict[str, str]:
    """Return fresh credentials so token rotation takes effect immediately."""
    return {TOKEN_HEADER: load_or_create_token()}


def bridge_is_running() -> bool:
    """Probe the authenticated bridge status endpoint."""
    try:
        request = urllib.request.Request(STATUS_URL, headers=authentication_headers())
        with urllib.request.urlopen(request, timeout=1.0) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def ensure_bridge_running() -> bool:
    """Ask the single Windows supervisor to start the bridge."""
    if bridge_is_running():
        return True
    if not BRIDGE_SERVER_PATH.exists():
        return False

    if sys.platform != "win32":
        return False
    try:
        subprocess.run(
            ["schtasks.exe", "/Run", "/TN", "NexusAGY Browser Bridge"],
            check=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    for _ in range(30):
        time.sleep(0.1)
        if bridge_is_running():
            return True
    return False


def call_bridge(action: str, params: dict[str, Any] | None = None, timeout: float = 20.0, *, retry: bool = True) -> Any:
    """Execute one browser action and return its decoded result."""
    payload = {"action": action, "params": params or {}, "timeout": timeout}
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **authentication_headers()},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout + 2) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            try:
                payload = json.loads(error.read().decode("utf-8"))
                message = payload.get("error", f"HTTP {error.code}: {error.reason}")
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                message = f"HTTP {error.code}: {error.reason}"
        finally:
            error.close()
        raise RuntimeError(message) from error
    except (urllib.error.URLError, TimeoutError) as error:
        if retry and ensure_bridge_running():
            return call_bridge(action, params, timeout, retry=False)
        raise ConnectionError(
            f"Impossible de joindre le pont NexusAGY sur {API_URL}. Le démarrage automatique a échoué."
        ) from error

    if not data.get("success"):
        raise RuntimeError(data.get("error", "Erreur inconnue du pont NexusAGY"))
    return data.get("data")
