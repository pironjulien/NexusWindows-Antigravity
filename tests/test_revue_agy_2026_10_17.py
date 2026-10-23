"""Revue d'Antigravity du 17/10/2026 (NexusHarness/shared/reponse-agy-2026-10-17.md, partie 1) : un test par point
corrigé, écrit pour échouer sur l'ancien code (1.1 : tests/test_sync.py). Hors ligne : aucune vraie fenêtre de Julien
n'est touchée, aucune vraie entrée n'est envoyée, aucun document n'est ouvert (os.startfile simulé)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "client"))

import computer_client  # noqa: E402

TARGET = 222


# =============================================================================
# 1.2 (autonomie 2.7.0) : plus aucune application en lecture seule, banques comprises (coffres : blocage dur en 2.8.0)
# =============================================================================
def _protected(monkeypatch, proc, title):
    monkeypatch.setattr(computer_client.user32, "IsWindow", lambda h: 1)
    monkeypatch.setattr(computer_client, "get_process_image_path", lambda pid: ("", proc))
    monkeypatch.setattr(computer_client, "_window_text", lambda h: title)
    return computer_client.is_protected_system_window(TARGET)


@pytest.mark.parametrize(
    ("proc", "title"),
    [
        ("Notepad.exe", "banque_releves.txt - Bloc-notes"),
        ("Code.exe", "test_bank_api.py - NexusBank - Visual Studio Code"),
        ("explorer.exe", "revolut-connector"),
        ("WindowsTerminal.exe", "pwsh - C:\\Dev\\paypal-export"),
        ("SumatraPDF.exe", "Relevé Boursorama mars.pdf - SumatraPDF"),
    ],
)
def test_1_2_editors_explorers_and_viewers_named_like_a_bank_stay_usable(monkeypatch, proc, title):
    assert _protected(monkeypatch, proc, title) == (False, "")


@pytest.mark.parametrize(
    ("proc", "title", "words"),
    [
        ("Revolut.exe", "Accueil", "bancaire"),
        ("Ledger Live.exe", "Portefeuille", "bancaire"),
        ("app.exe", "Crédit Agricole - Mes comptes", "bancaire"),  # processus inconnu : le titre compte encore
        ("", "Revolut", "bancaire"),  # processus illisible : le titre compte encore
    ],
)
def test_1_2_bank_apps_are_now_usable(monkeypatch, proc, title, words):
    assert _protected(monkeypatch, proc, title) == (False, ""), words


# =============================================================================
# 1.3 : open_path ne désigne que la fenêtre de l'application associée (ou portant le nom)
# =============================================================================
@pytest.fixture
def opening(tmp_path, monkeypatch):
    """Ouverture simulée : `state["after"]` = fenêtres visibles après os.startfile, application associée notepad."""
    doc = tmp_path / "rapport_trimestriel_2026.txt"
    doc.write_text("x", encoding="utf-8")
    state = {"before": [{"hwnd": 1, "title": "Antigravity", "process_name": "Antigravity.exe"}], "after": []}
    state["current"] = state["before"]
    monkeypatch.setattr(computer_client, "OPEN_WAIT_S", 0.4, raising=False)
    monkeypatch.setattr(computer_client, "_assoc_executable", lambda path: "notepad.exe")
    monkeypatch.setattr(computer_client, "list_windows", lambda visible_only=True: list(state["current"]))
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)

    def run():
        with patch("os.startfile", side_effect=lambda p: state.update(current=state["after"])):
            return computer_client.open_path(str(doc))

    state["run"] = run
    return state


def test_1_3_a_stray_notification_is_never_taken_for_the_document(opening):
    toast = {"hwnd": 50, "title": "Nouveau message - Discord", "process_name": "Discord.exe"}
    opening["after"] = [*opening["before"], toast]
    res = opening["run"]()
    assert res["success"] is None and res["verified"] is None
    assert "hwnd" not in res and "non vérifiée" in res["message"]


def test_1_3_new_window_of_the_associated_app_is_the_document(opening):
    toast = {"hwnd": 50, "title": "Nouveau message - Discord", "process_name": "Discord.exe"}
    pad = {"hwnd": 60, "title": "Sans titre - Bloc-notes", "process_name": "Notepad.exe"}
    opening["after"] = [*opening["before"], toast, pad]
    res = opening["run"]()
    assert res["success"] is True and res["hwnd"] == 60


def test_1_3_tab_added_to_an_open_window_with_a_truncated_name(opening):
    pad = {"hwnd": 70, "title": "notes.txt - Bloc-notes", "process_name": "Notepad.exe"}
    opening["before"].append(pad)
    tabbed = dict(pad, title="rapport_trimes… - Bloc-notes")  # onglet ajouté : aucune fenêtre nouvelle
    opening["after"] = [opening["before"][0], tabbed]
    res = opening["run"]()
    assert res["success"] is True and res["hwnd"] == 70 and "onglet" in res["verified_by"]


def test_1_3_existing_window_of_another_app_bearing_the_name_is_not_taken(opening):
    other = {"hwnd": 80, "title": "rapport_trimestriel_2026.txt - Visual Studio Code", "process_name": "Code.exe"}
    opening["before"].append(other)
    opening["after"] = list(opening["before"])
    res = opening["run"]()
    assert res["success"] is None and "hwnd" not in res


def test_1_3_truncated_title_needs_the_start_of_the_name():
    assert computer_client._title_names_file("rapport_trimes… - Bloc-notes", "rapport_trimestriel_2026.txt")
    assert computer_client._title_names_file(
        "Rapport_trimestriel_2026.txt - Bloc-notes", "rapport_trimestriel_2026.txt"
    )
    assert not computer_client._title_names_file("rapport_annuel… - Bloc-notes", "rapport_trimestriel_2026.txt")
    assert not computer_client._title_names_file("ra… - Bloc-notes", "rapport_trimestriel_2026.txt")


def test_1_3_associated_executable_is_read_from_windows(tmp_path):
    folder = tmp_path / "dossier"
    folder.mkdir()
    assert computer_client._assoc_executable(str(folder)) == "explorer.exe"
    unknown = tmp_path / "x.extension-inconnue-nexusagy"
    unknown.write_text("x", encoding="utf-8")
    assert computer_client._assoc_executable(str(unknown)) == ""  # jamais « Ouvrir avec »


# =============================================================================
# 1.4 (point faux, gardé) : la fenêtre ouverte reste derrière, mais une étape foreground=True la ramène elle-même
# =============================================================================
def test_1_4_physical_step_brings_the_opened_window_back_itself(monkeypatch):
    front = {"hwnd": 111}  # premier plan rendu à Julien par open_path
    focused: list = []

    def focus(hwnd: int = 0, **kwargs):
        focused.append(hwnd)
        front["hwnd"] = hwnd
        return {"success": True}

    monkeypatch.setattr(computer_client.user32, "GetForegroundWindow", lambda: front["hwnd"])
    monkeypatch.setattr(computer_client.user32, "GetCursorPos", lambda p: 1)
    monkeypatch.setattr(computer_client.user32, "SetCursorPos", lambda x, y: 1)
    monkeypatch.setattr(computer_client, "_take_foreground_token", lambda purpose: MagicMock())
    monkeypatch.setattr(computer_client, "wait_for_user_idle", lambda **kwargs: True)
    monkeypatch.setattr(computer_client, "focus_window", focus)
    monkeypatch.setattr(computer_client, "restore_foreground", lambda hwnd: True)
    with computer_client.FocusGuard(TARGET, purpose="test"):
        assert focused == [TARGET] and front["hwnd"] == TARGET
        computer_client._require_front()  # aucune ForegroundLostError : la cible est devant


# =============================================================================
# 1.5 : jamais le bouton inverse par correspondance partielle
# =============================================================================
@pytest.fixture
def cache(monkeypatch):
    def fill(*items):
        controls = {i: MagicMock() for i in range(1, len(items) + 1)}
        infos = {i: {"type": role, "name": name} for i, (role, name) in enumerate(items, start=1)}
        monkeypatch.setattr(computer_client, "_element_cache", controls)
        monkeypatch.setattr(computer_client, "_element_info", infos)
        monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)

    monkeypatch.setattr(computer_client, "get_window_state", lambda **kwargs: {})
    return fill


@pytest.mark.parametrize(
    ("wanted", "inverse"),
    [
        ("Supprimer", "Ne pas supprimer"),
        ("Enregistrer", "Ne pas enregistrer"),
        ("Envoyer", "Envoyer plus tard ? Non"),
        ("Save", "Don't save"),
        ("Install", "Skip install"),
        ("Continuer", "Continuer sans enregistrer"),
    ],
)
def test_1_5_partial_match_never_picks_the_inverse_button(cache, wanted, inverse):
    cache(("Button", inverse), ("Button", "Annuler"))
    with pytest.raises(ValueError):
        computer_client._resolve_step_target({"action": "click", "target": wanted}, TARGET)


def test_1_5_unique_partial_on_an_action_element_is_refused_with_the_candidate(cache):
    cache(("Button", "Supprimer la sélection"), ("Button", "Fermer"))
    with pytest.raises(ValueError, match=r"\[1\] « Supprimer la sélection » Button.*viser \[N\] ou le nom exact"):
        computer_client._resolve_step_target({"action": "click", "target": "Supprimer"}, TARGET)
    assert computer_client._resolve_step_target({"action": "click", "target": "#1"}, TARGET)[0] == 1


@pytest.mark.parametrize("role", ["MenuItem", "Hyperlink", "SplitButton"])
def test_1_5_partial_is_refused_for_every_action_role(cache, role):
    cache((role, "Exporter en PDF"), ("Edit", "Titre"))
    with pytest.raises(ValueError, match="viser \\[N\\] ou le nom exact"):
        computer_client._resolve_step_target({"action": "click", "target": "Exporter"}, TARGET)


def test_1_5_partial_still_works_for_fields(cache):
    cache(("Edit", "Nom de famille"), ("ComboBox", "Pays de naissance"), ("Button", "Valider"))
    step = {"action": "set", "target": "Nom"}
    assert computer_client._resolve_step_target(step, TARGET)[0] == 1 and "partiel" in step["_target_note"]
    assert computer_client._resolve_step_target({"action": "select", "target": "Pays"}, TARGET)[0] == 2


def test_1_5_menus_refuse_partial_but_find_exact_with_ellipsis_or_shortcut(monkeypatch):
    def node(name):
        n = MagicMock(control_type="MenuItem", props={}, element=MagicMock())
        n.name = name
        return n

    items = [node("Ne pas enregistrer"), node("Enregistrer sous..."), node("Imprimer\tCtrl+P")]
    monkeypatch.setattr(computer_client, "_window_tree", lambda *a, **k: MagicMock(status="ok", nodes=items))
    monkeypatch.setattr(computer_client, "_wrap_element", lambda element, info: element)
    assert computer_client._find_menu_item([TARGET], "Enregistrer sous") is items[1].element
    assert computer_client._find_menu_item([TARGET], "Imprimer") is items[2].element
    # « Enregistrer » : jamais « Ne pas enregistrer » ; « Enregistrer sous... » partiel → refus qui le propose.
    with pytest.raises(ValueError, match="seul candidat partiel : « Enregistrer sous... »"):
        computer_client._find_menu_item([TARGET], "Enregistrer")
    items.pop(1)
    assert computer_client._find_menu_item([TARGET], "Enregistrer") is None


# =============================================================================
# 1.6 : confirmation seulement pour les éléments d'action et les verbes d'action
# =============================================================================
@pytest.mark.parametrize(
    ("label", "role"),
    [
        ("Boîte d'envoi", "TreeItem"),
        ("Boîte d'envoi", "Button"),  # nom de dossier, même sur un bouton : pas un verbe
        ("Éléments envoyés", "ListItem"),
        ("Effacer le filtre", "Button"),
        ("Effacer la recherche", "Hyperlink"),
        ("Transferts", "TreeItem"),
        ("Supprimés", "TreeItem"),
        ("Supprimer", "ListItem"),  # élément de liste : sélectionner n'est pas supprimer
        ("Envoyer", "TabItem"),
        ("Effacer tout", "Button"),
        ("Tout effacer", "MenuItem"),
        ("Supprimer", "Button"),
    ],
)
def test_1_6_folders_lists_and_filters_need_no_confirm(monkeypatch, label, role):
    monkeypatch.delenv("NEXUS_AGY_CONFIRM", raising=False)
    computer_client.require_confirmation(label, False, "clic", role)


@pytest.mark.parametrize(
    ("label", "role"),
    [
        ("Envoyer", "Button"),
        ("Envoie", "Button"),
        ("Payer 49 €", "Hyperlink"),
        ("Supprimer définitivement", "SplitButton"),
        ("Vider la corbeille", "MenuItem"),
        ("Publier", "Button"),
        ("Envoyer", ""),  # rôle inconnu : prudence
    ],
)
def test_1_6_action_verbs_on_action_elements_still_need_confirm(monkeypatch, label, role):
    monkeypatch.delenv("NEXUS_AGY_CONFIRM", raising=False)
    with pytest.raises(computer_client.ConfirmationRequiredError):
        computer_client.require_confirmation(label, False, "clic", role)


def test_1_6_click_on_outbox_folder_goes_through(monkeypatch):
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {4: {"type": "TreeItem", "name": "Boîte d'envoi"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "_click_element", clicked)
    res = computer_client.act([{"action": "click", "target": "#4"}], hwnd=TARGET, then="none")
    assert res["success"] is True
    clicked.assert_called_once()


# =============================================================================
# 2.7.0 : liste de confirmation en UNE constante, réglage NEXUS_AGY_CONFIRM=off
# =============================================================================
def test_confirmation_is_on_by_default(monkeypatch):
    monkeypatch.delenv("NEXUS_AGY_CONFIRM", raising=False)
    assert computer_client.confirmation_enabled() is True
    monkeypatch.setenv("NEXUS_AGY_CONFIRM", "on")
    assert computer_client.confirmation_enabled() is True


@pytest.mark.parametrize("value", ["off", "OFF", " off ", "0", "false", "non"])
def test_confirm_off_disables_every_confirmation(monkeypatch, value):
    monkeypatch.setenv("NEXUS_AGY_CONFIRM", value)
    assert computer_client.confirmation_enabled() is False
    for label in ("Envoyer", "Payer 49 €", "Supprimer définitivement", "Publier", "Passer la commande"):
        computer_client.require_confirmation(label, False, "clic", "Button")


def test_confirm_off_lets_act_click_send_without_confirm(monkeypatch):
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setenv("NEXUS_AGY_CONFIRM", "off")
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {4: {"type": "Button", "name": "Envoyer"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "_click_element", clicked)
    res = computer_client.act([{"action": "click", "target": "#4"}], hwnd=TARGET, then="none")
    assert res["success"] is True
    clicked.assert_called_once()


def test_emptying_the_confirm_list_disables_confirmation(monkeypatch):
    monkeypatch.delenv("NEXUS_AGY_CONFIRM", raising=False)
    monkeypatch.setattr(computer_client, "CONFIRM_PATTERNS", ())
    assert computer_client.irreversible_word("Payer 49 €") == ""
    computer_client.require_confirmation("Envoyer", False, "clic", "Button")


def test_confirm_list_is_third_party_money_or_irreversible():
    words = " ".join(computer_client.CONFIRM_PATTERNS)
    for gone in ("clear all",):
        assert gone not in words, gone
    assert "subscribe" in words
    assert "abonn" in words
    assert computer_client.irreversible_word("Supprimer") == ""
    assert computer_client.irreversible_word("Supprimer définitivement") == "supprimer definitivement"


def test_confirm_off_is_documented():
    # GEMINI.md réservé par Julien aux règles souveraines (a4baed2, e0a4a4b, 20d4aa7) : la doc vit dans ces deux fichiers.
    for rel in ("README.md", "plugins/nexus-computer/skills/nexus-computer/SKILL.md"):
        assert "NEXUS_AGY_CONFIRM=off" in (REPO_ROOT / rel).read_text(encoding="utf-8"), rel


def test_open_path_accepts_windows_activation_protocols_and_redirects_only_web_urls():
    """Revue d'Antigravity (tour 3) : ms-settings: et shell: sont des protocoles Windows, pas des pages web."""
    assert computer_client._path_problem("ms-settings:windowsupdate") == ""
    assert computer_client._path_problem("shell:RecycleBinFolder") == ""
    assert "nexus-browser" in computer_client._path_problem("https://example.com")
    assert "nexus-browser" in computer_client._path_problem("ftp://example.com/f")
    assert computer_client._path_problem("C:\\chemin\\absent\\fichier.txt") == "chemin introuvable"
