"""Journal commun des trois Nexus Windows (NexusHarness/NexusShared/journal/FORMAT.md) : une ligne par action, sans texte
d'écran (ni texte tapé, ni libellé, ni titre), en plus de computer.log. Écrit au niveau du serveur MCP, là où passe
CHAQUE appel d'action (lots, ouverture, fermeture, défilement, glisser, refus, arrêts : relecture d'Antigravity du
23/10, qui voyait ces actions échapper à _log). Jamais d'exception vers l'outil."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def version() -> str:
    """Version de l'outil : pyproject.toml des sources, sinon celle du paquet installé (uvx), sinon « inconnue »."""
    try:
        text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
        found = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if found:
            return found.group(1)
    except OSError:
        pass
    try:
        from importlib.metadata import version as installed

        return installed("nexus-windows-antigravity")
    except Exception:  # noqa: BLE001 - ni sources ni paquet installé
        return "inconnue"


VERSION = version()
# Cause d'erreur : seulement le début du message, avant le premier guillemet, deux-points, parenthèse ou crochet ; ce
# qui suit peut venir de l'écran (noms, options listées, valeurs). Relecture de Codex du 23/10.
_CUT = re.compile(r"[«\"“'’(\[:{]")
# Techniques par la vraie souris ou le vrai clavier (l'activation SIMULÉE n'est pas un premier plan)
_FOREGROUND = re.compile(r"physical|sendinput|foreground|\breal\b", re.IGNORECASE)
_MARKS = {"✓", "=", "~", "✗"}


def _racine() -> Path:
    base = os.environ.get("NEXUS_JOURNAL_HOME") or os.path.join(
        os.environ.get("LOCALAPPDATA", str(Path.home())), "NexusJournal"
    )
    return Path(base) / "windows" / "antigravity"


def erreur_propre(texte: Any) -> str | None:
    if not texte:
        return None
    debut = _CUT.split(" ".join(str(texte).split()), maxsplit=1)[0].strip(" .,;-")
    return debut[:80] or "error"


def issue(result: dict[str, Any]) -> str:
    """Marque d'un résultat : ✓ seulement si l'effet est RELU (verified True) ; sinon ~, ✗ si échec."""
    mark = result.get("mark")
    if mark in _MARKS:
        return str(mark)
    if result.get("already"):
        return "="
    if result.get("success") is False or result.get("verified") is False:
        return "✗"
    return "✓" if result.get("verified") is True else "~"


def _technique(result: dict[str, Any]) -> str | None:
    value = result.get("technique") or result.get("method")
    return str(value) if value else None


def _premier_plan(result: dict[str, Any], technique: str | None) -> bool:
    return bool(
        result.get("physical") or result.get("foreground_taken") or (technique and _FOREGROUND.search(technique))
    )


def _ligne(appel: str, app: str | None, cadre: str | None, action: str | None, technique: str | None, issue_: str,
           ms: float | None, premier_plan: bool, erreur: Any) -> dict[str, Any]:  # fmt: skip
    return {
        "v": 1,
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "agent": "antigravity",
        "outil": VERSION,
        "appel": appel,
        "app": (app or "").lower() or None,
        "cadre": cadre,
        "action": action,
        "technique": technique,
        "issue": issue_,
        "ms": round(ms) if isinstance(ms, (int, float)) else None,
        "premier_plan": premier_plan,
        "erreur": erreur_propre(erreur),
    }


_ARRET = {"EmergencyStopError"}
_DIFFERE = {"UserInterruptError", "JulienActiveError"}
_REFUS = {"NeedsForegroundError", "ConfirmationRequiredError", "PermissionError"}


def _issue_erreur(out: dict[str, Any]) -> str:
    """Issue d'un appel ou d'une étape en erreur, par ses drapeaux ou le type de l'erreur (relecture de Codex)."""
    kind = str(out.get("error_type") or "")
    if out.get("emergency_stop") or kind in _ARRET:
        return "arrêt"
    if out.get("interrupted_by_user") or kind in _DIFFERE:
        return "différé"
    if out.get("needs_confirmation") or out.get("needs_foreground") or kind in _REFUS:
        return "refus"
    return "✗"


def lignes(kind: str, app: str | None, cadre: str | None, out: dict[str, Any], ms: float) -> list[dict[str, Any]]:
    """Lignes du journal pour la réponse d'un appel d'action (out : {status, data | error…} du serveur MCP)."""
    appel = uuid.uuid4().hex[:12]
    status = out.get("status")
    if status == "refused":
        return [_ligne(appel, app, cadre, kind, None, "refus", ms, False, out.get("refused"))]
    if status == "error":
        issue_ = _issue_erreur(out)
        return [_ligne(appel, app, cadre, kind, None, issue_, ms, False, out.get("error_type") or out.get("error"))]
    data = out.get("data")
    if not isinstance(data, dict):
        return [_ligne(appel, app, cadre, kind, None, "✓" if status == "success" else "~", ms, False, None)]
    steps = data.get("steps")
    if isinstance(steps, list) and steps:
        out_lines = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            brut = step.get("result")
            result: dict[str, Any] = brut if isinstance(brut, dict) else {}
            technique = _technique(result)
            out_lines.append(
                _ligne(
                    appel,
                    app,
                    cadre,
                    step.get("action") or kind,
                    technique,
                    _issue_erreur(step) if step.get("status") == "error" else issue(step),
                    step.get("ms") if isinstance(step.get("ms"), (int, float)) else ms / len(steps),
                    _premier_plan(result, technique),
                    step.get("error_type") or step.get("error"),
                )  # fmt: skip
            )
        return out_lines
    technique = _technique(data)
    return [_ligne(appel, app, cadre, kind, technique, issue(data), ms, _premier_plan(data, technique),
                   data.get("message") if issue(data) in ("✗", "~") else None)]  # fmt: skip


def ecrire(lignes_: list[dict[str, Any]]) -> None:
    try:
        chemin = _racine() / f"{datetime.now(UTC):%Y-%m}.jsonl"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with chemin.open("a", encoding="utf-8") as f:
            for ligne in lignes_:
                f.write(json.dumps(ligne) + "\n")  # échappé : aucune erreur d'encodage (relecture de Codex)
    except Exception:  # noqa: BLE001 - journal : jamais bloquant
        pass
