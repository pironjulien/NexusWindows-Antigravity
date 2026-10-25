"""État du produit pour l'appli Nexus (contrat « mises à jour hors conteneur », 26/10/2026) : au démarrage du serveur,
`~/.nexus/status/windows-antigravity.json` = {product, version, latest, state, checked_at, message}.

Le serveur ne se met pas à jour lui-même : le plugin le déclare en `uvx … nexus-windows-antigravity@latest`, donc
chaque démarrage d'Antigravity lance la dernière version publiée. Ici, seulement l'état : version en cours, et
dernière version lue sur PyPI au plus une fois par jour (une requête GET, rien d'autre n'est envoyé), dans un fil à
part pour ne jamais retarder le démarrage. `NEXUS_UPDATE_CHECK=off` : aucune requête, `latest` vide. Jamais
d'exception vers le serveur."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PRODUCT = "windows-antigravity"
PYPI_JSON = "https://pypi.org/pypi/nexus-windows-antigravity/json"
CHECK_EVERY = timedelta(days=1)
TIMEOUT_S = 5.0


def status_path() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home()) / ".nexus" / "status" / f"{PRODUCT}.json"


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return ()


def fetch_latest(timeout_s: float = TIMEOUT_S) -> str:
    from urllib.request import Request, urlopen

    request = Request(PYPI_JSON, headers={"Accept": "application/json", "User-Agent": f"{PRODUCT}-status"})
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - adresse fixe en https
        return str(json.loads(response.read(2_000_000))["info"]["version"])


def message_for(version: str, latest: str) -> str:
    if not latest:
        return "Running; latest version not checked."
    if _key(latest) > _key(version):
        return f"Version {latest} is available: it starts with the next Antigravity start."
    return "Up to date."


def record(version: str, fetch=fetch_latest, now=_now) -> dict[str, Any]:
    """Écrit l'état ; relit PyPI si la dernière lecture date de plus d'un jour. Rend l'état écrit."""
    path = status_path()
    previous = _read(path)
    latest = str(previous.get("latest") or "")
    checked = previous.get("checked_at") or ""
    try:
        last_check = datetime.fromisoformat(str(checked).replace("Z", "+00:00"))
    except ValueError:
        last_check = None
    state, message = "idle", ""
    if os.environ.get("NEXUS_UPDATE_CHECK", "").lower() == "off":
        latest, checked = "", ""
    elif last_check is None or now() - last_check >= CHECK_EVERY:
        _write(path, {**previous, "product": PRODUCT, "version": version, "state": "checking"})
        try:
            latest = fetch()
            checked = now().isoformat().replace("+00:00", "Z")
            # Juste après une sortie, le JSON de PyPI (en cache) peut encore donner la version d'avant : la dernière
            # version publiée n'est jamais plus ancienne que celle qui tourne (relevé le 26/10 : 3.1.7 lu par la 3.2.0).
            if _key(latest) < _key(version):
                latest = version
        except Exception as error:  # noqa: BLE001 - réseau absent, PyPI indisponible : l'état le dit
            state, message = "failed", f"Latest version not checked ({type(error).__name__})."
    data = {
        "product": PRODUCT,
        "version": version,
        "latest": latest,
        "state": state,
        "checked_at": checked,
        "message": message or message_for(version, latest),
    }
    _write(path, data)
    return data


def record_in_background(version: str) -> threading.Thread:
    def run() -> None:
        try:
            record(version)
        except Exception:  # noqa: BLE001 - l'état ne doit jamais gêner le serveur
            pass

    thread = threading.Thread(target=run, name="nexus-status", daemon=True)
    thread.start()
    return thread
