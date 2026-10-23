"""Défauts relevés par Antigravity à la passe 2 du banc commun (22/10/2026)."""

import json
import sys
from pathlib import Path

import pytest

CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT_DIR))

import computer_client  # noqa: E402


def test_bare_program_names_resolve_like_run_dialog():
    resolved = computer_client._resolve_program("notepad.exe")
    assert Path(resolved).is_absolute() and Path(resolved).exists()
    assert computer_client._resolve_program("notepad").lower().endswith("notepad.exe")


def test_documents_and_protocols_are_left_alone():
    for path in ("rapport.txt", "ms-settings:display", r"C:\nulle\part.exe", ""):
        assert computer_client._resolve_program(path) == path


def test_unknown_program_stays_unresolved():
    assert computer_client._resolve_program("programme-inexistant-1618.exe") == "programme-inexistant-1618.exe"


def test_text_goes_to_the_edit_of_an_editable_combo():
    names = {1: "Nom du fichier :", 2: "Nom du fichier :"}
    roles = {1: "ComboBox", 2: "Edit"}
    key, _ = computer_client.choose_label(
        names,
        "Nom du fichier :",
        str,
        role_of=lambda k: roles.get(k, ""),
        roles=computer_client.ACTION_ROLES["set"],
        acting=True,
        combo_of={2: 1}.get,  # l'Edit 2 est l'enfant direct de la ComboBox 1
    )
    assert key == 2


def test_two_edits_stay_ambiguous():
    names = {1: "Nom", 2: "Nom", 3: "Nom"}
    roles = {1: "ComboBox", 2: "Edit", 3: "Edit"}
    with pytest.raises(computer_client.AmbiguousTargetError):
        computer_client.choose_label(
            names,
            "Nom",
            str,
            role_of=lambda k: roles.get(k, ""),
            roles=computer_client.ACTION_ROLES["set"],
            acting=True,
        )


def test_edit_and_unrelated_combo_stay_ambiguous():
    # Relecture de Codex : un Edit et une ComboBox homonymes mais indépendants (pas parent/enfant).
    names = {1: "Pays", 2: "Pays"}
    roles = {1: "Edit", 2: "ComboBox"}
    with pytest.raises(computer_client.AmbiguousTargetError):
        computer_client.choose_label(
            names,
            "Pays",
            str,
            role_of=lambda k: roles.get(k, ""),
            roles=computer_client.ACTION_ROLES["set"],
            acting=True,
            combo_of=lambda k: None,
        )


class _User32:
    def __init__(self, visible: bool, alive_after: bool = True) -> None:
        self.visible = visible
        self.alive_after = alive_after
        self.posted: list[int] = []

    def IsWindow(self, hwnd):  # noqa: N802 - nom de l'API Win32
        return not self.posted or self.alive_after

    def IsWindowVisible(self, hwnd):  # noqa: N802
        return self.visible

    def PostMessageW(self, hwnd, msg, wparam, lparam):  # noqa: N802
        self.posted.append(msg)


def _close(monkeypatch, fake):
    monkeypatch.setattr(computer_client, "user32", fake)
    monkeypatch.setattr(computer_client, "uia", None)
    monkeypatch.setattr(computer_client, "resolve_window", lambda h: 77)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "ensure_default_desktop", lambda: None)
    monkeypatch.setattr(computer_client.time, "sleep", lambda s: None)
    clock = iter(range(0, 1000))
    monkeypatch.setattr(computer_client.time, "monotonic", lambda: next(clock) * 0.5)
    return computer_client.close_window(77)


def test_destroyed_window_is_closed(monkeypatch):
    out = _close(monkeypatch, _User32(visible=True, alive_after=False))
    assert out["verified"] is True and out["closed"] is True


def test_already_hidden_window_is_not_proof(monkeypatch):
    out = _close(monkeypatch, _User32(visible=False))
    assert out["success"] is None and out.get("verified") is None and "déjà masquée" in out["message"]


def test_common_journal_lines_from_mcp_answers(tmp_path):
    import journal_commun

    lot = {"status": "unverified", "data": {"steps": [
        {"action": "set", "mark": "✓", "result": {"technique": "win32_em_replacesel"}},
        {"action": "drag", "mark": "~", "result": {"technique": "physical_sendinput", "physical": True}},
    ]}}  # fmt: skip
    lignes = journal_commun.lignes("act", "Notepad.exe", "Win32", lot, 50)
    assert [(x["action"], x["issue"], x["premier_plan"]) for x in lignes] == [("set", "✓", False), ("drag", "~", True)]
    assert lignes[0]["appel"] == lignes[1]["appel"] and lignes[0]["app"] == "notepad.exe"
    assert (
        journal_commun.lignes("close", None, None, {"status": "refused", "refused": "repeat"}, 1)[0]["issue"] == "refus"
    )
    arret = {"status": "error", "emergency_stop": True, "error_type": "EmergencyStopError"}
    assert journal_commun.lignes("act", None, None, arret, 1)[0]["issue"] == "arrêt"
    # verified None : effet non relu, jamais ✓ (relecture d'Antigravity)
    assert journal_commun.issue({"success": True, "verified": None}) == "~"
    erreur = journal_commun.lignes("act", None, None, {"status": "error", "error": "« Mot de passe » introuvable"}, 1)[
        0
    ]
    assert erreur["issue"] == "✗" and "Mot de passe" not in json.dumps(erreur, ensure_ascii=False)
    journal_commun.ecrire(lignes)
    fichier = next((tmp_path / "journal-commun" / "windows" / "antigravity").glob("*.jsonl"))
    assert len(fichier.read_text(encoding="utf-8").splitlines()) == 2


def test_step_errors_are_classified_like_calls():
    import journal_commun

    lot = {"status": "failed", "data": {"steps": [
        {"action": "click", "status": "error", "mark": "✗", "error_type": "EmergencyStopError"},
        {"action": "key", "status": "error", "mark": "✗", "error_type": "ConfirmationRequiredError"},
        {"action": "type", "status": "error", "mark": "✗", "error_type": "UserInterruptError"},
    ]}}  # fmt: skip
    assert [x["issue"] for x in journal_commun.lignes("act", None, None, lot, 1)] == ["arrêt", "refus", "différé"]
