"""Tests de l'accord exact (jeton à usage unique) dans NexusAGY (NexusWindows for Antigravity).

Conforme à l'accord d'architecture Claude-Antigravity du 19/10/2026 :
- Geste SORTANT (envoyer, payer, publier, transférer, appeler...) : exige confirm=true ET accord=<jeton>
  lié à l'action exacte (outil, geste, cible, destinataires, contenu des champs éditables de la fenêtre, contexte).
- Destruction locale (supprimer définitivement, formater, désinstaller...) : confirm=true seul suffit.
- NEXUS_AGY_CONFIRM=off désactive confirmation et accord.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import computer_client  # noqa: E402

TARGET = 5555


@pytest.fixture(autouse=True)
def clean_accords(monkeypatch):
    """Réinitialise le registre d'accords et réactive la confirmation pour chaque test."""
    monkeypatch.delenv("NEXUS_AGY_CONFIRM", raising=False)
    acc = computer_client.get_accords()
    with acc._lock:
        acc._pending.clear()


def test_outward_click_refused_without_confirm_or_accord(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {1: {"type": "Button", "name": "Envoyer"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "_click_element", clicked)

    res = computer_client.act([{"action": "click", "target": "#1"}], hwnd=TARGET, then="none")
    assert res["success"] is False
    assert res["steps"][0]["error_type"] == "ConfirmationRequiredError"
    err = res["steps"][0]["error"]
    assert "action sortante" in err and 'accord="' in err
    clicked.assert_not_called()


def test_outward_click_refused_with_confirm_alone(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {1: {"type": "Button", "name": "Payer 50 €"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "_click_element", clicked)

    res = computer_client.act([{"action": "click", "target": "#1", "confirm": True}], hwnd=TARGET, then="none")
    assert res["success"] is False
    assert "confirm=true alone is not enough" in res["steps"][0]["error"]
    clicked.assert_not_called()


def test_outward_click_success_with_valid_accord_then_token_consumed(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {1: {"type": "Button", "name": "Envoyer"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "_window_title_raw", lambda h: "Messagerie")
    monkeypatch.setattr(computer_client, "_window_process_name", lambda h: "chat.exe")
    monkeypatch.setattr(computer_client, "field_contents", lambda h: ["Message: Bonjour"])
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "_click_element", clicked)

    # 1. Premier appel sans accord -> renvoie le jeton
    res1 = computer_client.act([{"action": "click", "target": "#1"}], hwnd=TARGET, then="none")
    assert res1["success"] is False
    token = res1["steps"][0]["error"].rsplit('accord="', 1)[1].split('"', 1)[0]
    assert len(token) == 8

    # 2. Deuxième appel avec confirm=True et accord=token -> succès
    res2 = computer_client.act(
        [{"action": "click", "target": "#1", "confirm": True, "accord": token}],
        hwnd=TARGET,
        then="none",
    )
    assert res2["success"] is True
    clicked.assert_called_once()

    # 3. Troisième appel avec le même jeton (déjà consommé) -> refusé
    clicked.reset_mock()
    res3 = computer_client.act(
        [{"action": "click", "target": "#1", "confirm": True, "accord": token}],
        hwnd=TARGET,
        then="none",
    )
    assert res3["success"] is False
    assert "accord unknown or already used" in res3["steps"][0]["error"]
    clicked.assert_not_called()


def test_outward_click_refused_if_field_content_changed(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {1: {"type": "Button", "name": "Envoyer"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "_window_title_raw", lambda h: "Messagerie")
    monkeypatch.setattr(computer_client, "_window_process_name", lambda h: "chat.exe")

    fields = ["Message: Virement 10 €"]
    monkeypatch.setattr(computer_client, "field_contents", lambda h: fields)
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "_click_element", clicked)

    # Accord proposé pour 10 €
    res1 = computer_client.act([{"action": "click", "target": "#1"}], hwnd=TARGET, then="none")
    token = res1["steps"][0]["error"].rsplit('accord="', 1)[1].split('"', 1)[0]

    # Le contenu du champ change subrepticement vers 1000 €
    fields[0] = "Message: Virement 1000 €"

    # Tentative avec l'accord de 10 € -> refusée car contenu altéré
    res2 = computer_client.act(
        [{"action": "click", "target": "#1", "confirm": True, "accord": token}],
        hwnd=TARGET,
        then="none",
    )
    assert res2["success"] is False
    assert "the action changed since the accord (content)" in res2["steps"][0]["error"]
    clicked.assert_not_called()


def test_outward_click_refused_if_expired(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {1: {"type": "Button", "name": "Envoyer"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)

    current_time = [1000.0]
    acc = computer_client.get_accords()
    monkeypatch.setattr(acc, "_clock", lambda: current_time[0])

    res1 = computer_client.act([{"action": "click", "target": "#1"}], hwnd=TARGET, then="none")
    token = res1["steps"][0]["error"].rsplit('accord="', 1)[1].split('"', 1)[0]

    # Avance le temps au-delà du TTL (600 s)
    current_time[0] += 601.0

    res2 = computer_client.act(
        [{"action": "click", "target": "#1", "confirm": True, "accord": token}],
        hwnd=TARGET,
        then="none",
    )
    assert res2["success"] is False
    assert "accord expired" in res2["steps"][0]["error"]


def test_batch_level_accord_parameter(monkeypatch):
    """Le paramètre accord au niveau de computer_act s'applique aux étapes du lot."""
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {1: {"type": "Button", "name": "Publier"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "_click_element", clicked)

    res1 = computer_client.act([{"action": "click", "target": "#1"}], hwnd=TARGET, then="none")
    token = res1["steps"][0]["error"].rsplit('accord="', 1)[1].split('"', 1)[0]

    res2 = computer_client.act(
        [{"action": "click", "target": "#1", "confirm": True}],
        hwnd=TARGET,
        then="none",
        accord=token,
    )
    assert res2["success"] is True
    clicked.assert_called_once()


def test_local_destruction_needs_confirm_alone(monkeypatch):
    """Les destructions locales (Désinstaller, Formater, Supprimer définitivement...)
    n'exigent que confirm=True, aucun accord requis."""
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "_click_element", clicked)

    for i, label in enumerate(["Supprimer définitivement", "Désinstaller", "Formater", "Réinitialiser ce PC"], start=1):
        monkeypatch.setattr(computer_client, "_element_info", {i: {"type": "Button", "name": label}})
        # Sans confirm=True -> refusé avec message classique Julien
        res_no = computer_client.act([{"action": "click", "target": f"#{i}"}], hwnd=TARGET, then="none")
        assert res_no["success"] is False
        assert "confirm=true" in res_no["steps"][0]["error"]
        assert 'accord="' not in res_no["steps"][0]["error"]  # pas d'accord pour une destruction locale

        # Avec confirm=True seul -> accepté
        res_yes = computer_client.act(
            [{"action": "click", "target": f"#{i}", "confirm": True}],
            hwnd=TARGET,
            then="none",
        )
        assert res_yes["success"] is True


def test_confirm_off_bypasses_accord_and_confirm(monkeypatch):
    """NEXUS_AGY_CONFIRM=off désactive toute confirmation et tout accord."""
    monkeypatch.setenv("NEXUS_AGY_CONFIRM", "off")
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {1: {"type": "Button", "name": "Envoyer"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "_click_element", clicked)

    res = computer_client.act([{"action": "click", "target": "#1"}], hwnd=TARGET, then="none")
    assert res["success"] is True
    clicked.assert_called_once()


def test_type_text_submit_outward_needs_accord(monkeypatch):
    """type_text avec submit=True sur un champ adjacent à un bouton Envoyer exige l'accord."""
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {1: {"type": "Edit", "name": "Message"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "_window_title_raw", lambda h: "Messagerie")
    monkeypatch.setattr(computer_client, "_window_process_name", lambda h: "chat.exe")
    monkeypatch.setattr(computer_client, "field_contents", lambda h: ["Message: Salut"])

    # Mock require_key_confirmation to trigger outward requirement if no accord
    pressed = MagicMock(return_value={"success": True, "method": "sendinput_enter", "sent": True})
    monkeypatch.setattr(computer_client, "press_key", pressed)

    # 1. require_key_confirmation lève sans accord
    def fake_require_key(hwnd, keys, confirm, field=None, accord="", approved=None):
        acc = computer_client.get_accords()
        act_desc = computer_client.garde_fous.action(
            "windows", f"touche « {keys} »", "Envoyer", content="Message: Salut"
        )
        fp = computer_client.garde_fous.fingerprint(act_desc)
        if approved is not None and fp in approved:
            return
        ans = acc.check(act_desc, confirm, accord)
        if ans:
            raise computer_client.ConfirmationRequiredError(ans)
        if approved is not None:
            approved.add(fp)

    monkeypatch.setattr(computer_client, "require_key_confirmation", fake_require_key)
    monkeypatch.setattr(
        computer_client,
        "_text_plan",
        lambda *args: ("Edit", [("uia", lambda: {"verified": True, "technique": "uia", "tried": []})], None, None),
    )
    monkeypatch.setattr(
        computer_client,
        "_run_chain",
        lambda *args: {"verified": True, "technique": "uia", "tried": []},
    )

    with pytest.raises(computer_client.ConfirmationRequiredError) as exc:
        computer_client.type_text("Salut", hwnd=TARGET, element_index=1, submit=True)
    token = str(exc.value).rsplit('accord="', 1)[1].split('"', 1)[0]

    # Avec confirm=True et accord=token -> passe sans double consommation
    res = computer_client.type_text("Salut", hwnd=TARGET, element_index=1, submit=True, confirm=True, accord=token)
    assert res["success"] is True
    assert res["submit"] is True
    pressed.assert_called_once()
