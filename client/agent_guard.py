"""Garde-fous conçus pour Gemini : une consigne courte `next` après chaque action, et le refus d'un lot renvoyé
à l'identique sans avoir regardé.

Constat du 16/10 (journal ~/.nexusagy/computer.log) : Gemini a renvoyé six fois le même lot parce que chaque retour
disait « UNVERIFIED » sans dire quoi faire. Il lit peu les longues descriptions et préfère réessayer que vérifier :
chaque réponse porte donc une marque (✓ = ~ ✗) et une consigne d'une ligne, et un renvoi aveugle est refusé.

Module pur (aucun appel Windows) : testé hors ligne.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

REPEAT_WINDOW_S = 10.0  # un même lot renvoyé dans cet intervalle sans observation est refusé

MARK_OK, MARK_ALREADY, MARK_UNKNOWN, MARK_FAIL = "✓", "=", "~", "✗"

NEXT_OK = "✓ fait, passe à la suite."
NEXT_ALREADY = "= déjà fait : NE PAS recommencer, passe à la suite."
NEXT_UNKNOWN = (
    "~ effet non vu : regarde l'image jointe (ou computer_look) avant toute nouvelle tentative ; "
    "ne renvoie pas le même lot."
)
NEXT_REPEAT = (
    "✗ refusé, RIEN n'a été fait : même lot renvoyé sans avoir regardé. Regarde d'abord (computer_look), puis envoie "
    "un lot corrigé ; repeat=true seulement pour forcer en connaissance de cause."
)


def mark(verified: Any, success: Any = None, already: bool | None = False) -> str:
    """Marque d'une action : ✓ effet relu, = déjà dans l'état voulu, ~ effet non relu, ✗ échec."""
    if already:
        return MARK_ALREADY
    if verified is True and success is not False:
        return MARK_OK
    if verified is False or success is False:
        return MARK_FAIL
    return MARK_UNKNOWN


def _alternative(error_type: str, message: str) -> str:
    low = message.lower()
    if error_type == "ConfirmationRequiredError" or "confirm=true" in low:
        if "accord=" in low or "action sortante" in low:
            return (
                "action sortante : montre la description à Julien mot pour mot ; "
                'après son oui, renvoie avec confirm=true et accord="<jeton>"'
            )
        return (
            "irréversible : ordre explicite de Julien → confirm=true sur l'étape ; ton initiative → demande-lui d'abord"
        )
    if error_type == "AmbiguousTargetError" or ("désigne" in low and "rien n'a été fait" in low):
        return "choisis parmi les candidats listés : « #N » ou libellé exact unique"
    if "nexus-browser" in low:
        return "page web : utilise nexus-browser (pont Chrome)"
    if "impossible à piloter" in low:
        return "surface Windows protégée (session, verrouillage, UAC) : seul Julien peut y agir"
    if "lecture seule" in low:
        return "champ en lecture seule : rien à y saisir, vise un autre champ"
    if "fenêtre non précisée" in low:
        return "nomme la fenêtre (hwnd : numéro de computer_list_windows, titre ou processus)"
    if error_type == "ForegroundLostError":
        return (
            "la fenêtre n'est pas passée devant : réessaie en arrière-plan (cible par libellé), sinon demande à Julien"
        )
    if error_type == "NeedsForegroundError" or "foreground=true" in low:
        return "essaie une cible par libellé (target), sinon foreground=true (vraie souris/clavier en repli)"
    if error_type == "UserInterruptError":
        return "Julien a repris la main : ne relance pas, attends-le"
    if error_type == "EmergencyStopError" or "arrêt d'urgence" in low:
        return "arrêt d'urgence de Julien : ne fais plus rien, attends ses instructions"
    if error_type == "TimeoutError" or "tient la souris" in low or "en train de taper" in low:
        return "réessaie dans quelques secondes (ou en arrière-plan, sans foreground)"
    if "introuvable" in low or "aucun élément en cache" in low or "n'est plus accessible" in low:
        return "regarde la fenêtre (computer_look) et vise un libellé visible"
    if error_type == "PermissionError":
        return "fenêtre protégée : demande à Julien"
    return "regarde la fenêtre (computer_look) avant d'envoyer un autre lot"


def _clip(text: str, limit: int = 200) -> str:
    """Texte sur une ligne, coupé à un mot entier."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def next_for_error(error: BaseException | str, error_type: str = "", what: str = "") -> str:
    message = str(error)
    kind = error_type or (type(error).__name__ if isinstance(error, BaseException) else "")
    cause = _clip(what or getattr(error, "what", "") or message)
    return f"✗ échec : {cause} ; {_alternative(kind, message)}."


def next_for_result(data: Any) -> str:
    """Consigne d'une action unitaire d'après son résultat (verified, success, already, message)."""
    if not isinstance(data, dict):
        return NEXT_OK
    if data.get("already"):
        return NEXT_ALREADY
    verified = data.get("verified")
    success = data.get("success")
    if verified is True and success is not False:
        return NEXT_OK
    if verified is False or success is False:
        cause = data.get("verified_by") or data.get("message") or "effet relu absent"
        return f"✗ échec : {cause} ; regarde l'image jointe, puis corrige la cible ou la valeur (pas le même lot)."
    if data.get("pending"):
        return (
            "~ commande partie, fenêtre occupée (boîte de dialogue ?) : regarde (computer_look) avant toute autre "
            "action ; ne renvoie pas le même lot."
        )
    return NEXT_UNKNOWN


FAILED_STEP_STATUSES = ("error", "failed", "timeout")
STATUS_SUCCESS, STATUS_FAILED, STATUS_UNVERIFIED = "success", "failed", "unverified"
REPORT_STATUSES = (STATUS_SUCCESS, STATUS_FAILED, STATUS_UNVERIFIED)  # action partie : compte rendu complet


def status_for(data: Any) -> str:
    """Statut global d'une action : celui de la PIRE étape (banc du 16/10 : un lot rendait « success » avec une
    étape en erreur). Erreur, échec ou temps dépassé → failed ; effet non vu → unverified ; sinon success."""
    if not isinstance(data, dict):
        return STATUS_SUCCESS
    if "steps" in data:
        steps = [s for s in data.get("steps") or [] if isinstance(s, dict)]
        if (
            data.get("success") is False
            or data.get("error")
            or any(s.get("status") in FAILED_STEP_STATUSES or s.get("mark") == MARK_FAIL for s in steps)
        ):
            return STATUS_FAILED
        if data.get("success") is None or any(
            s.get("status") == "unverified" or s.get("mark") == MARK_UNKNOWN for s in steps
        ):
            return STATUS_UNVERIFIED
        return STATUS_SUCCESS
    current = data.get("mark") or mark(data.get("verified"), data.get("success"), bool(data.get("already")))
    return {MARK_FAIL: STATUS_FAILED, MARK_UNKNOWN: STATUS_UNVERIFIED}.get(current, STATUS_SUCCESS)


def mark_for_status(status: str, data: dict[str, Any]) -> str:
    """Marque d'un lot d'après son statut global (= si toutes les étapes étaient déjà faites)."""
    if status == STATUS_FAILED:
        return MARK_FAIL
    if status == STATUS_UNVERIFIED:
        return MARK_UNKNOWN
    steps = data.get("steps") or []
    return MARK_ALREADY if steps and all(s.get("mark") == MARK_ALREADY for s in steps) else MARK_OK


def next_for_act(data: dict[str, Any]) -> str:
    """Consigne d'un lot computer_act : première étape en échec, sinon effet non vu, sinon tout fait."""
    steps = data.get("steps") or []
    for step in steps:
        if step.get("status") == "error":
            return f"étape {step.get('step')} : " + next_for_error(
                step.get("error", ""), step.get("error_type", ""), step.get("what", "")
            )
        if step.get("status") in ("failed", "timeout"):
            result = step.get("result") or {}
            observed = (result.get("expect") or {}).get("observed")
            cause = result.get("verified_by") or step.get("message") or "effet relu absent"
            if observed:
                cause += f" (observé : {json.dumps(observed, ensure_ascii=False)[:120]})"
            return (
                f"✗ échec à l'étape {step.get('step')} : {cause} ; regarde l'image jointe, corrige cette étape et "
                "renvoie seulement la suite (les étapes ✓ sont faites)."
            )
    unknown = [s.get("step") for s in steps if s.get("mark") == MARK_UNKNOWN or s.get("status") == "unverified"]
    if unknown:
        return (
            f"~ effet non vu aux étapes {unknown} : lot arrêté, la suite n'a pas été envoyée ; "
            "regarde l'image jointe ou computer_look avant toute nouvelle tentative ; "
            "ne renvoie pas le même lot (les étapes ✓ et = sont faites)."
        )
    if steps and all(s.get("mark") == MARK_ALREADY for s in steps):
        return NEXT_ALREADY
    notes = [f"étape {s.get('step')} : {s['target_note']}" for s in steps if s.get("target_note")]
    if notes:
        return f"{NEXT_OK} À vérifier : {' ; '.join(notes)}."
    return NEXT_OK


def signature(kind: str, payload: Any) -> str:
    """Empreinte stable d'un appel (ordre des clés et espaces ignorés)."""
    text = json.dumps({"kind": kind, "payload": payload}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


class RepeatGuard:
    """Refuse un lot (ou une action) identique au précédent sur la même fenêtre, renvoyé dans les REPEAT_WINDOW_S
    secondes sans observation (computer_look, computer_get_window_state) entre les deux."""

    def __init__(self, window_s: float = REPEAT_WINDOW_S) -> None:
        self.window_s = window_s
        self._sent: dict[tuple[int, str], float] = {}
        self._observed: dict[int, float] = {}
        self._lock = threading.Lock()

    def observed(self, window: int, now: float | None = None) -> None:
        with self._lock:
            self._observed[int(window or 0)] = time.monotonic() if now is None else now

    def check(self, kind: str, window: int, payload: Any, repeat: bool = False, now: float | None = None):
        """None si l'appel peut partir (il est alors noté), sinon le message de refus."""
        now = time.monotonic() if now is None else now
        key = (int(window or 0), signature(kind, payload))
        with self._lock:
            for old_key, sent_at in list(self._sent.items()):
                if now - sent_at > self.window_s:
                    del self._sent[old_key]
            sent_at = self._sent.get(key)
            if not repeat and sent_at is not None:
                looked_at = self._observed.get(key[0], -1.0)
                if looked_at < sent_at:
                    return NEXT_REPEAT
            self._sent[key] = now
        return None

    def reset(self) -> None:
        with self._lock:
            self._sent.clear()
            self._observed.clear()


GUARD = RepeatGuard()
