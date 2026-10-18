"""Revue de Claude du 17/10/2026 (NexusHarness/shared/revue-agy-2026-10-17.md, partie B) : un test par point, écrit
pour échouer sur l'ancien code. Hors ligne : aucune vraie fenêtre de Julien n'est touchée, aucune vraie entrée n'est
envoyée (SendInput, curseur, premier plan et jeton commun neutralisés), le presse-papiers de Julien est sauvé puis
rendu à l'identique."""

import ctypes
import json
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "client"))

import agent_guard  # noqa: E402
import computer_client  # noqa: E402
import mcp_server  # noqa: E402
import win32_controls  # noqa: E402

TARGET, OTHER = 222, 111  # fenêtre visée (factice) ; fenêtre de Julien au premier plan (factice)


class _Token:
    def release(self) -> None:
        pass


class _NoOpGuard:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def desk(monkeypatch):
    """Bureau factice : fenêtre visée TARGET jamais réelle, premier plan lu par `front["hwnd"]`, SendInput et curseur
    enregistrés (jamais envoyés), jeton commun et pause de Julien neutralisés, FocusGuard RÉEL."""
    front = {"hwnd": OTHER, "calls": 0, "switch_after": None}
    sent: list = []
    cursor: list = []

    def foreground():
        front["calls"] += 1
        if front["switch_after"] is not None and front["calls"] > front["switch_after"]:
            return OTHER
        return front["hwnd"]

    monkeypatch.setattr(computer_client.user32, "GetForegroundWindow", foreground)
    monkeypatch.setattr(computer_client.user32, "SendInput", lambda n, arr, size: sent.append(n) or n)
    monkeypatch.setattr(computer_client.user32, "SetCursorPos", lambda x, y: cursor.append((x, y)) or 1)
    monkeypatch.setattr(computer_client, "_take_foreground_token", lambda purpose: _Token())
    monkeypatch.setattr(computer_client, "wait_for_user_idle", lambda **kwargs: True)
    monkeypatch.setattr(computer_client, "focus_window", lambda **kwargs: {"success": True})
    monkeypatch.setattr(computer_client, "restore_foreground", lambda h: True)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "ensure_default_desktop", lambda: True)
    monkeypatch.setattr(computer_client, "FRONT_WAIT_S", 0.05, raising=False)
    monkeypatch.setattr(computer_client, "_focused_props", lambda: None, raising=False)
    monkeypatch.setattr(computer_client, "_focused_value", lambda: None)
    monkeypatch.setattr(computer_client.win32_controls, "root_of", lambda h: h)
    # Vraie souris/vrai clavier de Julien jamais lus : sinon un geste de Julien pendant le test (Raw Input ou
    # GetLastInputInfo) l'interrompt au hasard (UserInterruptError, test_b8 vu instable le 17/10).
    monkeypatch.setattr(computer_client.physical_input, "user_touched_since", lambda token, include_moves=True: False)
    return {"front": front, "sent": sent, "cursor": cursor}


# =============================================================================
# B1 : premier plan relu juste avant chaque entrée physique
# =============================================================================
def test_b1_nothing_is_typed_when_windows_refuses_the_foreground(desk):
    """SetForegroundWindow refusé (la messagerie de Julien reste devant) : ni frappe ni Entrée, refus clair."""
    with pytest.raises(Exception, match="premier plan"):
        computer_client.type_text("Bonjour", hwnd=TARGET, method="typing", submit=True, foreground=True)
    assert desk["sent"] == []


def test_b1_typing_stops_as_soon_as_another_window_comes_in_front(desk):
    desk["front"]["hwnd"] = TARGET
    desk["front"]["switch_after"] = 6  # la cible est devant, puis une fenêtre de Julien passe devant en pleine frappe
    with pytest.raises(Exception, match="premier plan"):
        computer_client.type_text("abcdefghijklmnop", hwnd=TARGET, method="typing", foreground=True)
    assert 0 < len(desk["sent"]) < 16


def test_b1_key_release_is_always_sent_even_after_foreground_loss(desk):
    """Touche enfoncée puis premier plan perdu : le relâchement part quand même (jamais de touche coincée)."""
    inp = computer_client.INPUT(type=computer_client.INPUT_KEYBOARD)
    inp.union.ki.dwFlags = computer_client.KEYEVENTF_KEYUP
    computer_client._send_inputs([inp])  # aucune garde : un relâchement passe toujours
    assert desk["sent"] == [1]
    down = computer_client.INPUT(type=computer_client.INPUT_KEYBOARD)
    with pytest.raises(Exception, match="fenêtre visée"):
        computer_client._send_inputs([down])  # appui hors garde physique : refusé
    assert desk["sent"] == [1]


# =============================================================================
# B2 : jamais de mauvaise cible sans le dire
# =============================================================================
def test_b2_no_window_means_refusal_never_the_foreground_window():
    with pytest.raises(ValueError, match="Fenêtre non précisée"):
        computer_client.resolve_window(None)
    with pytest.raises(ValueError, match="Fenêtre non précisée"):
        computer_client.resolve_window("  ")


def test_b2_ambiguous_window_title_is_refused_with_candidates(monkeypatch):
    windows = [
        {"hwnd": 10, "title": "Messagerie - Julien", "process_name": "outlook.exe"},
        {"hwnd": 11, "title": "Messagerie - Équipe", "process_name": "outlook.exe"},
        {"hwnd": 12, "title": "Bloc-notes", "process_name": "notepad.exe"},
    ]
    monkeypatch.setattr(computer_client, "list_windows", lambda visible_only=True: windows)
    with pytest.raises(ValueError, match=r"\[10\].*\[11\]"):
        computer_client.resolve_window("Messagerie")
    assert computer_client.resolve_window("bloc-notes") == 12  # titre exact unique
    assert computer_client.resolve_window("notepad") == 12  # processus unique
    with pytest.raises(ValueError, match="2 fenêtres"):
        computer_client.resolve_window("outlook")


@pytest.fixture
def cache(monkeypatch):
    """Cache d'éléments factice de la fenêtre TARGET (aucune relecture réelle)."""

    def fill(*items: tuple[str, str]) -> None:
        controls = {i: MagicMock() for i in range(1, len(items) + 1)}
        infos = {i: {"type": role, "name": name} for i, (role, name) in enumerate(items, start=1)}
        monkeypatch.setattr(computer_client, "_element_cache", controls)
        monkeypatch.setattr(computer_client, "_element_info", infos)
        monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)

    monkeypatch.setattr(computer_client, "get_window_state", lambda **kwargs: {})
    return fill


def test_b2_partial_label_inside_a_word_is_not_a_match(cache):
    cache(("Edit", "Prénom :"), ("Button", "Valider"))
    with pytest.raises(ValueError, match="introuvable"):
        computer_client._resolve_step_target({"action": "set", "target": "Nom"}, TARGET)


def test_b2_two_exact_labels_are_refused_with_the_candidates(cache):
    cache(("Button", "OK"), ("Button", "OK"))
    with pytest.raises(ValueError, match=r"\[1\] « OK » Button.*\[2\] « OK » Button"):
        computer_client._resolve_step_target({"action": "click", "target": "OK"}, TARGET)


def test_b2_unique_partial_label_is_accepted_but_flagged(cache):
    # Revue d'Antigravity 1.5 : partiel unique accepté pour un CHAMP seulement (« Ne pas supprimer » n'est plus
    # jamais choisi pour « Supprimer » : tests/test_revue_agy_2026_10_17.py).
    cache(("Edit", "Nom de famille"), ("Button", "Annuler"))
    step = {"action": "set", "target": "Nom"}
    index, _box = computer_client._resolve_step_target(step, TARGET)
    assert index == 1
    assert "partiel" in step.get("_target_note", "") and "Nom de famille" in step["_target_note"]


def test_b2_exact_label_wins_and_action_role_breaks_a_tie(cache):
    cache(("Button", "Nom"), ("Edit", "Nom"), ("Edit", "Nom de famille"))
    assert computer_client._resolve_step_target({"action": "set", "target": "Nom"}, TARGET)[0] == 2
    with pytest.raises(ValueError, match="désigne 2"):
        computer_client._resolve_step_target({"action": "hover", "target": "Nom"}, TARGET)


def _tree(*nodes):
    return MagicMock(status="ok", nodes=list(nodes))


def test_b2_menu_and_expect_follow_the_same_rule(monkeypatch):
    def node(name, role, **props):
        n = MagicMock(control_type=role, props=props, element=MagicMock())
        n.name = name
        return n

    monkeypatch.setattr(
        computer_client,
        "_window_tree",
        lambda *a, **k: _tree(node("Exporter en PDF", "MenuItem"), node("Exporter en CSV", "MenuItem")),
    )
    with pytest.raises(ValueError, match="Exporter en PDF.*Exporter en CSV"):
        computer_client._find_menu_item([TARGET], "Exporter")
    monkeypatch.setattr(
        computer_client, "_window_tree", lambda *a, **k: _tree(node("Total", "Text"), node("Total", "Edit"))
    )
    monkeypatch.setattr(computer_client, "_window_text", lambda h: "Facture")
    with pytest.raises(ValueError, match="désigne 2"):
        computer_client.check_expect(TARGET, {"element": "Total", "value": "12"})


# =============================================================================
# B3 (autonomie 2.7.0) : mots de passe, banques, Chrome/Edge et tout chemin permis ; confirmation réduite
# =============================================================================
def _uia_field(info_extra):
    pattern = MagicMock()
    pattern.IsReadOnly = False
    ctrl = MagicMock()
    ctrl.GetValuePattern.return_value = pattern
    info = {"type": "Edit", "name": "Code", "hwnd": 0, "framework": "WPF", "props": {"has_value": True}}
    info.update(info_extra)
    return ctrl, pattern, info


def test_b3_password_field_is_filled_in_background_and_never_read_back(monkeypatch):
    ctrl, pattern, info = _uia_field({"props": {"has_value": True, "password": True}})
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "is_electron_window", lambda h: False)
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: ctrl)
    monkeypatch.setattr(computer_client, "_element_info", {1: info})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "_read_state", lambda c, i: {"value": "", "exists": True})
    res = computer_client.type_text("secret", hwnd=TARGET, element_index=1)
    pattern.SetValue.assert_called_once_with("secret")  # contenu remplacé, jamais ajouté à une valeur masquée
    assert res["verified"] is None and res["success"] is None  # valeur masquée : ni faux succès ni faux échec
    assert "current_value" not in res and "mot de passe" in res["note"]
    assert "secret" not in json.dumps(res, ensure_ascii=False)


def test_b3_password_field_with_focus_is_typed_physically(desk, monkeypatch):
    desk["front"]["hwnd"] = TARGET
    monkeypatch.setattr(
        computer_client, "_focused_props", lambda: {"password": True, "name": "Mot de passe"}, raising=False
    )
    res = computer_client.type_text("secret", hwnd=TARGET, method="typing", foreground=True)
    assert len(desk["sent"]) >= 6  # frappe Unicode envoyée (au moins un envoi par caractère)
    assert res["verified"] is None and "mot de passe" in res["note"]


_u32 = ctypes.WinDLL("user32", use_last_error=True)
_u32.CreateWindowExW.argtypes = (
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
)  # fmt: skip
_u32.CreateWindowExW.restype = wintypes.HWND
_u32.DestroyWindow.argtypes = (wintypes.HWND,)


def test_b3_win32_password_edit_is_filled_by_messages():
    """Champ Edit ES_PASSWORD (fenêtre jamais affichée) : EM_REPLACESEL l'écrit, reconnu comme mot de passe."""
    edit = _u32.CreateWindowExW(0, "EDIT", "", 0x80000000 | 0x0020, 0, 0, 100, 20, None, None, None, None)
    assert edit
    try:
        assert win32_controls.is_password_edit(edit)
        assert computer_client.is_password_field({"type": "Edit", "hwnd": edit})
        assert win32_controls.edit_set_text(edit, "secret") == "em_replacesel"
        assert win32_controls.get_text(edit) == "secret"  # même processus : lisible ici, masqué pour les autres
    finally:
        _u32.DestroyWindow(edit)


@pytest.mark.parametrize(
    ("proc", "title"),
    [
        ("chrome.exe", "Gmail - Google Chrome"),
        ("msedge.exe", "Nouvel onglet - Edge"),
        ("BoursoBank.exe", "Mes comptes"),
        ("app.exe", "Crédit Agricole - Mes comptes"),
        ("CredentialUIBroker.exe", "Sécurité Windows"),
        ("SecHealthUI.exe", "Sécurité Windows"),
    ],
)
def test_b3_banks_and_browsers_are_usable(monkeypatch, proc, title):
    monkeypatch.setattr(computer_client.user32, "IsWindow", lambda h: 1)
    monkeypatch.setattr(computer_client, "get_process_image_path", lambda pid: ("", proc))
    monkeypatch.setattr(computer_client, "_window_text", lambda h: title)
    assert computer_client.is_protected_system_window(TARGET) == (False, "")


@pytest.mark.parametrize("proc", ["LogonUI.exe", "LockApp.exe", "consent.exe"])
def test_b3_only_undrivable_windows_surfaces_stay_refused(monkeypatch, proc):
    monkeypatch.setattr(computer_client.user32, "IsWindow", lambda h: 1)
    monkeypatch.setattr(computer_client, "get_process_image_path", lambda pid: ("", proc))
    protected, reason = computer_client.is_protected_system_window(TARGET)
    assert protected is True and "impossible à piloter" in reason


def test_b3_chrome_and_edge_get_a_short_browser_note(monkeypatch):
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "window_browser_note", lambda h: computer_client.browser_note("chrome.exe"))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {4: {"type": "Button", "name": "Rechercher"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "_click_element", clicked)
    res = computer_client.act([{"action": "click", "target": "#4"}], hwnd=TARGET, then="none")
    assert res["success"] is True and res["note"] == "Pour le web, nexus-browser est plus fiable."
    assert computer_client.browser_note("MSEDGE.EXE") and not computer_client.browser_note("notepad.exe")
    text = computer_client.format_look({"hwnd": 1, "title": "Gmail", "elements": [], "note": res["note"]})
    assert "nexus-browser est plus fiable" in text


@pytest.mark.parametrize(
    "label",
    ["Envoyer", "ENVOYER LE MESSAGE", "Payer 49 €", "Acheter maintenant", "Valider la commande", "Passer la commande",
     "Commander", "Virer 100 €", "Virement", "Publier", "Poster", "Supprimer définitivement", "Vider la corbeille",
     "Send", "Buy now", "Checkout", "Publish", "Place order"],
)  # fmt: skip
def test_b3_third_party_or_money_click_needs_confirm(monkeypatch, label):
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.delenv("NEXUS_AGY_CONFIRM", raising=False)
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {4: {"type": "Button", "name": label}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "_click_element", clicked)
    res = computer_client.act([{"action": "click", "target": "#4"}], hwnd=TARGET, then="none")
    assert res["success"] is False and res["steps"][0]["error_type"] == "ConfirmationRequiredError"
    assert "confirm=true" in res["steps"][0]["error"] and "Julien" in res["steps"][0]["error"]
    clicked.assert_not_called()
    res = computer_client.act([{"action": "click", "target": "#4", "confirm": True}], hwnd=TARGET, then="none")
    assert res["success"] is True
    clicked.assert_called_once()


@pytest.mark.parametrize(
    "label",
    ["Valider", "Enregistrer", "Suivant", "Nom", "Éléments envoyés", "PayPal", "Annuler", "Supprimer",
     "Supprimer l’élément", "Delete", "Transférer", "Confirmer", "S'abonner", "Subscribe", "Accepter", "Autoriser",
     "Effacer tout", "Tout effacer", "Clear all", "Réinitialiser les filtres", "Reset", "Format"],
)  # fmt: skip
def test_b3_everything_else_needs_no_confirm(monkeypatch, label):
    monkeypatch.delenv("NEXUS_AGY_CONFIRM", raising=False)
    computer_client.require_confirmation(label, False, "clic", "Button")


@pytest.mark.parametrize("name", ["outil.exe", "lancer.bat", "script.ps1", "raccourci.lnk", "setup.msi", "sans_ext"])
def test_b3_open_path_opens_programs_scripts_and_shortcuts(tmp_path, monkeypatch, name):
    target = tmp_path / name
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(computer_client, "OPEN_WAIT_S", 0.2, raising=False)
    monkeypatch.setattr(computer_client, "list_windows", lambda visible_only=True: [{"hwnd": 1, "title": "Autre"}])
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)
    with patch("os.startfile") as start:
        res = computer_client.open_path(str(target))
        start.assert_called_once_with(str(target))
        assert res["success"] is None and res["verified"] is None  # ouverture toujours relue, jamais supposée
        with pytest.raises(PermissionError, match="nexus-browser"):
            computer_client.open_path("https://exemple.fr")
        with pytest.raises(PermissionError, match="introuvable"):
            computer_client.open_path(str(tmp_path / "absent.exe"))
    start.assert_called_once()


def test_b3_open_path_reads_back_the_program_window_of_an_exe(tmp_path, monkeypatch):
    exe = tmp_path / "MonOutil.exe"
    exe.write_text("x", encoding="utf-8")
    state = {"windows": [{"hwnd": 1, "title": "Autre", "process_name": "Code.exe"}]}
    monkeypatch.setattr(computer_client, "OPEN_WAIT_S", 0.4, raising=False)
    monkeypatch.setattr(computer_client, "list_windows", lambda visible_only=True: list(state["windows"]))
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)
    opened = {"hwnd": 9, "title": "Tableau de bord", "process_name": "MonOutil.exe"}
    with patch("os.startfile", side_effect=lambda p: state["windows"].append(opened)):
        res = computer_client.open_path(str(exe))
    assert res["success"] is True and res["hwnd"] == 9 and res["application"] == "monoutil.exe"


def test_b3_open_path_success_only_when_a_window_is_read_back(tmp_path, monkeypatch):
    doc = tmp_path / "rapport.txt"
    doc.write_text("x", encoding="utf-8")
    monkeypatch.setattr(computer_client, "OPEN_WAIT_S", 0.3, raising=False)
    monkeypatch.setattr(computer_client, "list_windows", lambda visible_only=True: [{"hwnd": 1, "title": "Autre"}])
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)
    with patch("os.startfile") as start:
        res = computer_client.open_path(str(doc))
    start.assert_called_once()
    assert res["success"] is None and res["verified"] is None  # rien vu s'ouvrir : jamais « réussi »


# =============================================================================
# B4 : jamais de faux succès
# =============================================================================
class _Field:
    """Champ UIA dont l'application complète la saisie (« Julien » → « Julien Piron »)."""

    def __init__(self, transform):
        self.value = ""
        self.pattern = MagicMock()
        self.pattern.IsReadOnly = False
        self.pattern.SetValue.side_effect = lambda text: setattr(self, "value", transform(text))
        self.ctrl = MagicMock()
        self.ctrl.GetValuePattern.return_value = self.pattern
        self.info = {"type": "Edit", "name": "Nom", "hwnd": 0, "framework": "WPF", "props": {"has_value": True}}


@pytest.fixture
def field_window(monkeypatch):
    def install(field):
        monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
        monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
        monkeypatch.setattr(computer_client, "is_electron_window", lambda h: False)
        monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: field.ctrl)
        monkeypatch.setattr(computer_client, "_element_info", {1: field.info})
        monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
        monkeypatch.setattr(computer_client, "_read_state", lambda c, i: {"value": field.value, "exists": True})
        monkeypatch.setattr(computer_client, "EFFECT_WAIT_S", 0.05)

    return install


def test_b4_text_read_back_must_be_exactly_the_text(field_window):
    field = _Field(lambda text: text + " Piron")
    field_window(field)
    res = computer_client.type_text("Julien", hwnd=TARGET, element_index=1, clear_first=True)
    assert res["verified"] is not True and res["success"] is not True  # « Julien Piron » ≠ « Julien »
    exact = _Field(lambda text: "  ".join(text.split(" ")))  # espaces doublés : égalité normalisée
    field_window(exact)
    assert computer_client.type_text("Julien Piron", hwnd=TARGET, element_index=1, clear_first=True)["verified"]


def test_b4_presence_postcondition_never_skips_the_step(monkeypatch):
    run = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "_run_act_step", run)
    monkeypatch.setattr(computer_client, "check_expect", lambda h, e: (True, {"exists": True, "match": "partiel"}))
    monkeypatch.setattr(computer_client, "wait_expect", lambda h, e: (True, {"exists": True}))
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    res = computer_client.act(
        [{"action": "click", "target": "Valider", "expect": {"element": "Envoyé", "exists": True}}],
        hwnd=TARGET,
        then="none",
    )
    run.assert_called_once()  # « Éléments envoyés » visible avant : Valider est QUAND MÊME cliqué
    assert res["steps"][0].get("already") is not True
    run.reset_mock()
    monkeypatch.setattr(computer_client, "check_expect", lambda h, e: (True, {"value": "x", "match": "partiel"}))
    computer_client.act(
        [{"action": "set", "target": "Nom", "text": "x", "expect": {"element": "Nom", "value": "x"}}],
        hwnd=TARGET,
        then="none",
    )
    run.assert_called_once()  # libellé trouvé en partie : pas une preuve exacte


def test_b4_ctrl_a_on_uia_field_is_not_claimed_without_selection(monkeypatch):
    field = _Field(lambda text: text)
    monkeypatch.setattr(computer_client, "_designated_field", lambda h: None)
    monkeypatch.setattr(computer_client, "_select_all_text_pattern", lambda ctrl: False, raising=False)
    res = computer_client._background_keys(TARGET, "ctrl+a", ["ctrl", "a"], [(0x11, False), (0x41, False)],
                                           (field.ctrl, field.info))  # fmt: skip
    assert res is not None and res["verified"] is not True and res["success"] is not True


def test_b4_wait_honours_its_condition_and_announces_the_real_duration(monkeypatch):
    monkeypatch.setattr(computer_client, "_text_present", lambda h, t: False, raising=False)
    monkeypatch.setattr(computer_client, "WAIT_MAX_S", 0.3, raising=False)
    started = time.monotonic()
    res = computer_client._run_act_step("wait", {"action": "wait", "text": "Terminé", "seconds": 0.2}, TARGET, False, 0)
    assert res["verified"] is False and res["success"] is False  # texte jamais apparu : ✗
    assert 0.15 <= res["waited_seconds"] <= 1.0
    res = computer_client._run_act_step("wait", {"action": "wait", "seconds": 9}, TARGET, False, 0)
    assert "ramenée" in res.get("note", "") and res["waited_seconds"] < 1.0  # borne annoncée, durée réelle rendue
    assert time.monotonic() - started < 3
    monkeypatch.setattr(computer_client, "_text_present", lambda h, t: True, raising=False)
    res = computer_client._run_act_step("wait", {"action": "wait", "text": "Terminé"}, TARGET, False, 0)
    assert res["verified"] is True and "apparu" in res["verified_by"]


def test_b4_pixels_alone_never_prove_an_effect(monkeypatch):
    a = Image.new("L", (40, 40), 0)
    b = Image.new("L", (40, 40), 0)
    b.paste(255, (5, 5, 30, 30))  # animation, survol : beaucoup de pixels changés
    before = {"title": "t", "windows": (1,), "image": a, "tree": "arbre"}
    monkeypatch.setattr(computer_client, "window_fingerprint", lambda hwnd, with_tree=False: dict(before, image=b))
    monkeypatch.setattr(computer_client, "_tree_digest", lambda hwnd: "arbre")
    verified, how = computer_client._wait_window_effect(TARGET, before, timeout=0.05)
    assert verified is None and "image" in how


# =============================================================================
# B5 : un refus n'est jamais « déjà fait »
# =============================================================================
def test_b5_repeat_refusal_is_marked_failed_not_already(monkeypatch):
    assert not agent_guard.NEXT_REPEAT.startswith("=")
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "act", lambda **kwargs: {"success": True, "steps": [], "next": "✓"})
    lot = [{"action": "click", "target": "OK"}]
    mcp_server.computer_act(steps=lot, hwnd=TARGET)
    refused = json.loads(mcp_server.computer_act(steps=lot, hwnd=TARGET))
    assert refused["status"] == "refused" and refused["mark"] == "✗" and refused["next"].startswith("✗")


# =============================================================================
# B6 : anciens outils en arrière-plan d'abord ; vraie souris seulement visée et autorisée
# =============================================================================
@pytest.mark.parametrize("tool", ["computer_click", "computer_mouse_move", "computer_type_text", "computer_press_key"])
def test_b6_legacy_tools_default_to_background(tool):
    import inspect

    assert inspect.signature(getattr(mcp_server, tool)).parameters["foreground"].default is False


def test_b6_physical_scroll_drag_hover_need_window_and_foreground(monkeypatch):
    monkeypatch.setattr(computer_client, "_is_foreground", lambda h: True)  # fenêtre déjà devant : pas un permis
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "FocusGuard", _NoOpGuard)
    with patch.object(computer_client, "_send_inputs") as send, patch.object(computer_client.user32, "SetCursorPos"):
        with pytest.raises(computer_client.NeedsForegroundError):
            computer_client.scroll(delta_y=-1, hwnd=TARGET, x=5, y=5)
        with pytest.raises(computer_client.NeedsForegroundError):
            computer_client.drag(0, 0, 5, 5, hwnd=TARGET)
        with pytest.raises(computer_client.NeedsForegroundError):
            computer_client.mouse_move(5, 5, hwnd=TARGET)
        with pytest.raises(ValueError, match="Fenêtre non précisée"):
            computer_client.mouse_move(5, 5, coords="screen", foreground=True)
    send.assert_not_called()


# =============================================================================
# B7 : une seule bascule, relue patiemment
# =============================================================================
def test_b7_slow_checkbox_is_toggled_once(monkeypatch):
    state = {"toggle": 0, "flip_at": None, "toggles": 0}

    def toggle(_ctrl):
        state["toggles"] += 1
        state["flip_at"] = time.monotonic() + 0.6  # case lente : l'état change 0,6 s après la bascule
        return "uia"

    def read(_ctrl, _info):
        if state["flip_at"] is not None and time.monotonic() >= state["flip_at"]:
            state["toggle"], state["flip_at"] = 1 - state["toggle"], None
        return {"toggle": state["toggle"]}

    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "_target_element", lambda *a, **k: (3, MagicMock(), {"framework": "WPF"}))
    monkeypatch.setattr(computer_client, "_read_state", read)
    monkeypatch.setattr(computer_client, "_UIA_TOGGLE", toggle)
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)
    res = computer_client.set_checked(hwnd=TARGET, element_index=3, checked=True)
    assert state["toggles"] == 1  # jamais une seconde bascule avant d'avoir relu la première
    assert res["verified"] is True and state["toggle"] == 1


# =============================================================================
# B8 : presse-papiers de Julien rendu à l'identique, hors historique
# =============================================================================
@pytest.fixture
def julien_clipboard():
    """Sauve le vrai presse-papiers de Julien (tous formats) et le rend tel quel à la fin du test."""
    saved = computer_client.clipboard_snapshot()
    if not saved.complete:
        pytest.skip(f"presse-papiers de Julien non sauvable ({saved.reason}) : test non lancé, rien touché")
    try:
        yield
    finally:
        assert computer_client.clipboard_restore(saved)


def test_b8_every_format_is_restored_exactly(julien_clipboard):
    private = computer_client.user32.RegisterClipboardFormatW("NexusAGY.Test.Image")
    data = bytes(range(256)) * 4
    text = "Texte de Julien é".encode("utf-16-le") + b"\0\0"
    assert computer_client._open_clipboard()
    try:
        own = [(computer_client.CF_UNICODETEXT, text), (private, data), *computer_client._privacy_formats()]
        assert computer_client._put_formats(own)  # contenu de test, lui aussi hors historique Win+V
    finally:
        computer_client.user32.CloseClipboard()
    snap = computer_client.clipboard_snapshot()
    assert snap.complete
    assert computer_client.set_clipboard_text("texte de NexusAGY")
    history = computer_client.user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory")
    cloud = computer_client.user32.RegisterClipboardFormatW("CanUploadToCloudClipboard")
    posted = dict(computer_client.clipboard_snapshot().formats)
    assert posted[history][:4] == b"\0\0\0\0" and posted[cloud][:4] == b"\0\0\0\0"  # hors Win+V et nuage
    assert computer_client.clipboard_restore(snap)
    back = dict(computer_client.clipboard_snapshot().formats)
    assert back[private][: len(data)] == data  # format non texte (image, fichiers) rendu octet pour octet
    assert back[computer_client.CF_UNICODETEXT].startswith(text[:-2])


def test_b8_empty_clipboard_is_left_empty(julien_clipboard):
    assert computer_client._open_clipboard()
    try:
        computer_client.user32.EmptyClipboard()
    finally:
        computer_client.user32.CloseClipboard()
    empty = computer_client.clipboard_snapshot()
    assert empty.formats == []
    computer_client.set_clipboard_text("texte tapé")
    assert computer_client.clipboard_restore(empty)
    assert computer_client.get_clipboard_text() is None  # le texte tapé n'est jamais laissé


def test_b8_unsavable_clipboard_means_typing_not_pasting(desk, monkeypatch):
    desk["front"]["hwnd"] = TARGET
    incomplete = computer_client.ClipboardSnapshot([], complete=False, reason="image GDI")
    monkeypatch.setattr(computer_client, "clipboard_snapshot", lambda: incomplete, raising=False)
    put = MagicMock(return_value=True)
    monkeypatch.setattr(computer_client, "set_clipboard_text", put)
    res = computer_client.type_text("a\nb", hwnd=TARGET, method="paste", foreground=True)
    put.assert_not_called()  # presse-papiers de Julien jamais écrasé
    assert res["method"] == "sendinput_unicode" and "frappe" in res["clipboard"]


# =============================================================================
# B9 : curseur toujours rendu ; molette toujours visée
# =============================================================================
def test_b9_cursor_is_given_back_even_when_target_was_already_in_front(desk):
    desk["front"]["hwnd"] = TARGET
    with computer_client.FocusGuard(TARGET, restore=True):
        computer_client._move_cursor(400, 300)
    assert desk["cursor"][0] == (400, 300) and len(desk["cursor"]) == 2  # geste, puis curseur de Julien rendu


def test_b9_wheel_without_point_is_refused(desk):
    desk["front"]["hwnd"] = TARGET
    with pytest.raises(ValueError, match="point visé"):
        computer_client.scroll(delta_y=-3, hwnd=TARGET, foreground=True)
    assert desk["sent"] == [] and desk["cursor"] == []


# =============================================================================
# B10 : consignes = code
# =============================================================================
def test_b10_one_box_2d_name_in_look_and_act():
    entry = computer_client._element_entry(1, "Button", "OK", "", (10, 10, 20, 20), {"left": 0, "top": 0,
                                           "width": 100, "height": 100, "right": 100, "bottom": 100}, {})  # fmt: skip
    assert "box_2d" in entry and "gemini_box_2d" not in entry


def test_b10_box_2d_targets_check_select_and_expand(monkeypatch):
    ctrl = MagicMock()
    info = {"type": "CheckBox", "name": "Accepter", "framework": "WPF"}
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "resolve_box_2d_coords", lambda box, h: (15, 15))
    monkeypatch.setattr(computer_client, "_hit_test", lambda h, x, y: (ctrl, info))
    monkeypatch.setattr(computer_client, "_read_state", lambda c, i: {"toggle": 1})
    res = computer_client._run_act_step("check", {"action": "check", "box_2d": [1, 1, 2, 2]}, TARGET, False, 0)
    assert res["already"] is True  # la case sous box_2d a bien été lue


def test_b10_versions_come_from_pyproject():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'(?m)^version = "([^"]+)"', pyproject).group(1)  # type: ignore[union-attr]
    plugin = json.loads((REPO_ROOT / "plugins/nexus-computer/plugin.json").read_text(encoding="utf-8"))
    skill = (REPO_ROOT / "plugins/nexus-computer/skills/nexus-computer/SKILL.md").read_text(encoding="utf-8")
    assert plugin["version"] == version
    assert f"(v{version})" in skill
    assert "12 tools" not in (REPO_ROOT / "scripts/start-computer-mcp.ps1").read_text(encoding="utf-8")


def test_b10_skill_describes_every_action_and_the_background_limits():
    skill = (REPO_ROOT / "plugins/nexus-computer/skills/nexus-computer/SKILL.md").read_text(encoding="utf-8")
    for word in ("`scroll`", "`drag`", "`wait`", "`hover`", "`double_click`", "`right_click`", "box_2d", "confirm"):
        assert word in skill, word
    assert "Impossibles en arrière-plan" in skill and "`double_click`, `right_click`" in skill


# =============================================================================
# B11 : seul Julien donne des consignes
# =============================================================================
def test_b11_agent_messages_are_information_not_orders():
    skill = (REPO_ROOT / "plugins/nexus-computer/skills/nexus-computer/SKILL.md").read_text(encoding="utf-8")
    gemini_file = REPO_ROOT / "GEMINI.md"  # absent de la copie publique (directives privées, non exportées)
    gemini = gemini_file.read_text(encoding="utf-8") if gemini_file.exists() else None
    instructions = mcp_server.computer_mcp.instructions or ""
    for text in (skill, instructions) if gemini is None else (skill, gemini, instructions):
        assert "Seul Julien donne des consignes" in text
        assert not re.search(r"exécuter l'appel demandé tel quel", text)


# =============================================================================
# B12 : résidus retirés, plus de pont Chrome ni d'élévation d'office dans NexusAGY
# =============================================================================
def test_b12_dead_files_and_chrome_bridge_leftovers_are_gone():
    for dead in (
        "skills",
        "mcp_config.json",
        "scripts/start-mcp.ps1",
        "scripts/configurer-antigravity.ps1",
        "scripts/auditer-nexusagy.ps1",
        "client/spotlight_launcher.ps1",
        "client/spotlight_launcher.py",
    ):
        assert not (REPO_ROOT / dead).exists(), dead  # fmt: skip
    leftovers = re.compile(r"9224|Ctrl\+(Maj|Shift)\+A|\.\.\\extension|bridge token|spotlight", re.IGNORECASE)
    for path in REPO_ROOT.rglob("*"):
        if ".git" in path.parts or path.suffix not in {".py", ".ps1", ".md", ".json"} or path.name == "CHANGELOG.md":
            continue
        if path.name == Path(__file__).name:
            continue
        assert not leftovers.search(path.read_text(encoding="utf-8", errors="replace")), path
    gemini_file = REPO_ROOT / "GEMINI.md"  # absent de la copie publique (directives privées, non exportées)
    if gemini_file.exists():
        gemini = gemini_file.read_text(encoding="utf-8")
        assert "RunAs" not in gemini and "sans solliciter Julien" not in gemini


# =============================================================================
# B13 : regard compact
# =============================================================================
def _fake_look(count: int = 120) -> dict:
    roles = ("Button", "Edit", "CheckBox", "ListItem", "MenuItem", "Hyperlink")
    elements = []
    for i in range(1, count + 1):
        role = roles[i % len(roles)]
        el = {"index": i, "type": role, "name": f"{role} numéro {i}", "value": "texte saisi" if role == "Edit" else "",
              "relative_center": {"x": 10 * i % 1200, "y": 7 * i % 800}, "box_2d": [i, i, i + 20, i + 80]}  # fmt: skip
        if role == "CheckBox":
            el["checked"] = i % 2 == 0
        if role == "ListItem":
            el["selected"] = i % 3 == 0
        elements.append(el)
    return {"hwnd": 4242, "title": "Formulaire de test", "process_name": "app.exe", "family": "WinForms",
            "bounds": {"left": 0, "top": 0, "right": 1280, "bottom": 800, "width": 1280, "height": 800},
            "element_count": count, "elements": elements, "uia": {"method": "uia_cache_subtree", "status": "ok"}}  # fmt: skip


def test_b13_look_is_one_line_per_element_and_far_smaller():
    state = _fake_look()
    text = computer_client.format_look(state)
    lines = text.splitlines()
    assert len(lines) == 2 + 120
    assert lines[2].startswith("[1] Edit « Edit numéro 1 » = « texte saisi » @10,7")
    assert any("☑" in line for line in lines) and any("sélectionné" in line for line in lines)
    before = len(json.dumps({"status": "success", "data": state}, ensure_ascii=False, indent=2))
    assert before >= 3 * len(text)


def test_b13_computer_look_returns_the_compact_text_by_default(monkeypatch):
    monkeypatch.setattr(computer_client, "look", lambda **kwargs: _fake_look(3))
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: 4242)
    text = mcp_server.computer_look(hwnd=4242, capture_screenshot=False)
    assert isinstance(text, str) and text.startswith("fenêtre 4242") and "[3]" in text
    data = json.loads(mcp_server.computer_look(hwnd=4242, capture_screenshot=False, format="json"))
    assert data["data"]["elements"][0]["box_2d"]
