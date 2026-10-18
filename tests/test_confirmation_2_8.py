"""2.8.0 : la confirmation porte sur ce que le geste DÉCLENCHE, pas seulement sur le libellé cliqué.

Contournements fermés : Entrée / submit qui déclencheraient le bouton par défaut « Envoyer », Espace sur un bouton au
focus, Entrée dans le composeur d'une messagerie (bouton d'envoi voisin), clic par coordonnées sur un texte
« Payer » qui n'est pas un contrôle UI Automation.
"""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import computer_client  # noqa: E402
import win32_controls  # noqa: E402

TARGET = 4242
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_u32.CreateWindowExW.restype = wintypes.HWND
_u32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                 wintypes.HINSTANCE, wintypes.LPVOID)  # fmt: skip
_u32.DestroyWindow.argtypes = (wintypes.HWND,)
_k32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
_k32.GetModuleHandleW.restype = wintypes.HMODULE

WS_CHILD_VISIBLE = 0x50000000
WS_POPUP_VISIBLE_HIDDEN = 0x80000000  # fenêtre parente jamais affichée


@pytest.fixture(autouse=True)
def confirmation_on(monkeypatch):
    monkeypatch.delenv("NEXUS_AGY_CONFIRM", raising=False)


@pytest.fixture
def form():
    """Fenêtre Win32 réelle invisible (classe STATIC) : un champ et un bouton par défaut au libellé donné."""
    hinst = _k32.GetModuleHandleW(None)
    made: list[int] = []

    def make(default_label: str, other_label: str = "Annuler") -> SimpleNamespace:
        parent = _u32.CreateWindowExW(0, "STATIC", "Test", WS_POPUP_VISIBLE_HIDDEN, 0, 0, 400, 300, None, None,
                                      hinst, None)  # fmt: skip
        made.append(parent)

        def child(kind: str, text: str, style: int, ident: int) -> int:
            return _u32.CreateWindowExW(0, kind, text, WS_CHILD_VISIBLE | style, 0, 0, 100, 30, parent,
                                        wintypes.HMENU(ident), hinst, None)  # fmt: skip

        return SimpleNamespace(parent=parent, edit=child("EDIT", "", 0x0080, 21),
                               default=child("BUTTON", default_label, 0x1, 22),
                               other=child("BUTTON", other_label, 0x0, 23))  # fmt: skip

    yield make
    for hwnd in made:
        _u32.DestroyWindow(hwnd)


# --- Bouton par défaut Win32 (BS_DEFPUSHBUTTON, WinForms AcceptButton) ------------------------------------------
def test_default_button_is_found_on_a_real_window(form):
    f = form("Envoyer")
    assert win32_controls.default_button(f.parent) == f.default
    assert win32_controls.get_text(f.default) == "Envoyer"


@pytest.mark.parametrize("keys", ["enter", "Return", "ctrl+enter"])
def test_enter_refused_when_default_button_sends(form, monkeypatch, keys):
    f = form("Envoyer")
    monkeypatch.setattr(computer_client, "_window_tree", MagicMock(side_effect=RuntimeError("pas d'UIA ici")))
    with pytest.raises(computer_client.ConfirmationRequiredError, match="bouton par défaut") as refused:
        computer_client.require_key_confirmation(f.parent, keys, False)
    assert "Envoyer" in str(refused.value) and "confirm=true" in str(refused.value)
    computer_client.require_key_confirmation(f.parent, keys, True)  # oui explicite de Julien : passe


@pytest.mark.parametrize("label", ["OK", "Enregistrer", "Valider", "Suivant"])
def test_enter_free_when_default_button_is_harmless(form, monkeypatch, label):
    f = form(label, other_label="Envoyer")  # « Envoyer » présent mais pas déclenché par Entrée
    monkeypatch.setattr(computer_client, "_window_tree", MagicMock(side_effect=RuntimeError("pas d'UIA ici")))
    computer_client.require_key_confirmation(f.parent, "enter", False)


@pytest.mark.parametrize("keys", ["tab", "a", "ctrl+a", "backspace", "alt+f4", "ctrl+s"])
def test_other_keys_never_ask(form, keys):
    f = form("Payer")
    computer_client.require_key_confirmation(f.parent, keys, False)


def test_confirm_off_disables_key_confirmation(form, monkeypatch):
    f = form("Payer")
    monkeypatch.setenv("NEXUS_AGY_CONFIRM", "off")
    computer_client.require_key_confirmation(f.parent, "enter", False)


def test_press_key_refuses_before_sending_anything(form, monkeypatch):
    f = form("Publier")
    monkeypatch.setattr(computer_client, "_window_tree", MagicMock(side_effect=RuntimeError("pas d'UIA ici")))
    posted = MagicMock()
    monkeypatch.setattr(win32_controls, "post_key", posted)
    monkeypatch.setattr(computer_client, "_send_inputs", posted)
    with pytest.raises(computer_client.ConfirmationRequiredError):
        computer_client.press_key("enter", hwnd=f.parent)
    posted.assert_not_called()


# --- Bouton au focus : Entrée et Espace l'activent -----------------------------------------------------------
@pytest.mark.parametrize("keys", ["enter", "space"])
def test_focused_send_button_needs_confirm(form, monkeypatch, keys):
    f = form("OK", other_label="Envoyer")
    monkeypatch.setattr(win32_controls, "focused_push_button", lambda top: f.other)
    monkeypatch.setattr(computer_client, "_window_tree", MagicMock(side_effect=RuntimeError("pas d'UIA ici")))
    with pytest.raises(computer_client.ConfirmationRequiredError, match="focus"):
        computer_client.require_key_confirmation(f.parent, keys, False)


def test_space_ignores_default_button(form, monkeypatch):
    f = form("Envoyer")
    monkeypatch.setattr(win32_controls, "focused_push_button", lambda top: 0)
    computer_client.require_key_confirmation(f.parent, "space", False)


def test_key_step_on_targeted_send_button_needs_confirm(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "_element_info", {4: {"type": "Button", "name": "Envoyer"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    res = computer_client.act([{"action": "key", "keys": "space", "target": "#4"}], hwnd=TARGET, then="none")
    assert res["success"] is False and res["steps"][0]["error_type"] == "ConfirmationRequiredError"


# --- Composeur d'une messagerie / formulaire web : bouton d'envoi voisin du champ -------------------------------
def _uia_node(kind: str, name: str, parent: int, runtime_id: tuple = ()) -> SimpleNamespace:
    type_id = next(k for k, v in computer_client.uia_fast.CONTROL_TYPES.items() if v == kind)
    element = MagicMock()
    element.GetCurrentPropertyValue.return_value = 0
    return SimpleNamespace(control_type=kind, name=name, parent=parent, element=element,
                           props={"control_type": type_id, "runtime_id": runtime_id, "enabled": True})  # fmt: skip


def _chat_tree(send_label: str) -> SimpleNamespace:
    """Fenêtre ▸ Volet conversation ▸ Pied (composeur : champ + bouton d'envoi) ; Barre d'outils ailleurs."""
    return SimpleNamespace(status="ok", nodes=[
        _uia_node("Window", "Messagerie", -1),
        _uia_node("ToolBar", "Outils", 0),
        _uia_node("Button", "Envoyer/Recevoir", 1),  # loin du champ : jamais déclenché par Entrée
        _uia_node("Pane", "Conversation", 0),
        _uia_node("Group", "Pied", 3),
        _uia_node("Edit", "Tapez un message", 4, runtime_id=(42, 7)),
        _uia_node("Button", "Joindre", 4),
        _uia_node("Button", send_label, 4),
    ])  # fmt: skip


def _chat(monkeypatch, send_label: str) -> tuple:
    monkeypatch.setattr(computer_client, "_window_tree", lambda *a, **k: _chat_tree(send_label))
    monkeypatch.setattr(win32_controls, "family", lambda hwnd: "Chromium")
    field = (MagicMock(), {"type": "Edit", "name": "Tapez un message", "props": {"runtime_id": (42, 7)}})
    return field


def test_enter_in_chat_composer_needs_confirm(monkeypatch):
    field = _chat(monkeypatch, "Envoyer")
    with pytest.raises(computer_client.ConfirmationRequiredError, match="voisin du champ"):
        computer_client.require_key_confirmation(TARGET, "enter", False, field)
    computer_client.require_key_confirmation(TARGET, "enter", True, field)


def test_enter_in_field_far_from_send_button_is_free(monkeypatch):
    field = _chat(monkeypatch, "Micro")  # seul « Envoyer/Recevoir » de la barre d'outils, hors du composeur
    computer_client.require_key_confirmation(TARGET, "enter", False, field)


def test_uia_default_button_state_counts(monkeypatch):
    tree = _chat_tree("Micro")
    tree.nodes[2].element.GetCurrentPropertyValue.return_value = computer_client.STATE_SYSTEM_DEFAULT
    tree.nodes[2].name = "Payer"
    monkeypatch.setattr(computer_client, "_window_tree", lambda *a, **k: tree)
    monkeypatch.setattr(win32_controls, "family", lambda hwnd: "WPF")
    with pytest.raises(computer_client.ConfirmationRequiredError, match="bouton par défaut"):
        computer_client.require_key_confirmation(TARGET, "enter", False)


def test_type_submit_refused_before_typing(monkeypatch):
    field = _chat(monkeypatch, "Envoyer")
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: field[0])
    monkeypatch.setattr(computer_client, "_element_info", {5: field[1]})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    typed = MagicMock()
    monkeypatch.setattr(computer_client, "_run_chain", typed)
    with pytest.raises(computer_client.ConfirmationRequiredError):
        computer_client.type_text("Bonjour", hwnd=TARGET, element_index=5, submit=True)
    typed.assert_not_called()


# --- Clic par coordonnées hors contrôle UI Automation -------------------------------------------------------
def test_coordinate_click_on_drawn_pay_text_needs_confirm(monkeypatch):
    text = SimpleNamespace(control_type="Text", name="Payer 49 €", rect=(100, 100, 180, 130), props={})
    group = SimpleNamespace(control_type="Group", name="Panier", rect=(0, 0, 400, 400), props={})
    root = SimpleNamespace(control_type="Window", name="Boutique", rect=(0, 0, 500, 500), props={})
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "_aim_point", lambda *a: (120, 110, "screen_coordinates"))
    monkeypatch.setattr(computer_client, "_hit_test", lambda *a: None)
    monkeypatch.setattr(computer_client.user32, "IsWindow", lambda h: 1)
    monkeypatch.setattr(computer_client, "_window_tree",
                        lambda *a, **k: SimpleNamespace(status="ok", nodes=[root, group, text]))  # fmt: skip
    physical = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "_physical_point_click", physical)
    with pytest.raises(computer_client.ConfirmationRequiredError, match="Payer"):
        computer_client.click(hwnd=TARGET, x=120, y=110, coords="screen")
    physical.assert_not_called()
    computer_client.click(hwnd=TARGET, x=120, y=110, coords="screen", confirm=True)
    physical.assert_called_once()
    assert computer_client._label_at(TARGET, 300, 300) == "Panier"  # ailleurs : rien à confirmer


# --- SDK MCP 2.3 : annotations d'outils -----------------------------------------------------------------------
def test_every_tool_carries_annotations():
    import mcp_server

    tools = {}
    for tool in mcp_server.computer_mcp._tool_manager.list_tools():
        assert tool.annotations is not None, tool.name
        tools[tool.name] = tool.annotations
    for name in ("computer_look", "computer_list_windows", "computer_get_window_state", "computer_take_screenshot"):
        assert tools[name].read_only_hint is True, name
    for name in ("computer_act", "computer_click", "computer_type_text", "computer_press_key", "computer_open_path"):
        assert tools[name].read_only_hint is False and tools[name].destructive_hint is True, name
    assert tools["computer_close_window"].destructive_hint is False


# --- Gestes irréversibles ajoutés en 2.8.0 -------------------------------------------------------------------
@pytest.mark.parametrize(
    "label",
    ["Désinstaller", "Uninstall", "Formater", "Format disk", "Réinitialiser", "Réinitialiser ce PC",
     "Reset this PC", "Factory reset", "Résilier mon abonnement", "Cancel subscription", "Supprimer mon compte",
     "Delete account", "Effacer les données", "Effacer toutes les données", "Supprimer mes données", "Erase all data",
     "Wipe device"],
)  # fmt: skip
def test_irreversible_gestures_need_confirm(label):
    with pytest.raises(computer_client.ConfirmationRequiredError):
        computer_client.require_confirmation(label, False, "clic", "Button")


@pytest.mark.parametrize("label", ["Réinitialiser les filtres", "Réinitialiser le zoom", "Reset", "Format", "Données"])
def test_harmless_lookalikes_stay_free(label):
    computer_client.require_confirmation(label, False, "clic", "Button")


def _window_saying(monkeypatch, title: str, texts: list[str]):
    nodes = [SimpleNamespace(name=t) for t in texts]
    monkeypatch.setattr(computer_client.user32, "IsWindow", lambda h: 1)
    monkeypatch.setattr(computer_client.user32, "GetWindowTextW",
                        lambda h, buf, n: setattr(buf, "value", title) or len(title))  # fmt: skip
    monkeypatch.setattr(computer_client, "_window_tree", lambda *a, **k: SimpleNamespace(status="ok", nodes=nodes))


@pytest.mark.parametrize("label", ["Valider", "Confirmer", "OK", "Confirm"])
def test_validate_needs_confirm_in_a_payment_window(monkeypatch, label):
    _window_saying(monkeypatch, "Nouveau virement - Ma banque", ["IBAN du bénéficiaire", label])
    with pytest.raises(computer_client.ConfirmationRequiredError, match="paiement ou virement"):
        computer_client.require_confirmation(label, False, "clic", "Button", TARGET)


@pytest.mark.parametrize("label", ["Valider", "Confirmer", "OK"])
def test_validate_free_elsewhere(monkeypatch, label):
    _window_saying(monkeypatch, "Commande", ["Nom", "Email", label])
    computer_client.require_confirmation(label, False, "clic", "Button", TARGET)


@pytest.mark.parametrize(
    "texts", [["Moyens de paiement acceptés", "OK"], ["IBAN FR76 cité dans le mail", "OK"], ["Virements", "Valider"]]
)
def test_payment_words_inside_the_page_do_not_block_ok(monkeypatch, texts):
    """Revue d'Antigravity : contexte lu dans le TITRE seul (cookies d'Amazon, mail citant un IBAN, onglet bancaire)."""
    _window_saying(monkeypatch, "Amazon.fr", texts)
    tree = MagicMock(side_effect=AssertionError("aucune lecture d'arbre pour le contexte"))
    monkeypatch.setattr(computer_client, "_window_tree", tree)
    computer_client.require_confirmation(texts[-1], False, "clic", "Button", TARGET)


def test_start_needs_confirm_in_a_format_dialog(monkeypatch):
    _window_saying(monkeypatch, "Formater Disque local (D:)", ["Système de fichiers", "Démarrer"])
    with pytest.raises(computer_client.ConfirmationRequiredError, match="formatage"):
        computer_client.require_confirmation("Démarrer", False, "clic", "Button", TARGET)
    _window_saying(monkeypatch, "Document - Word", ["Format", "Démarrer"])  # menu « Format » : pas un formatage
    computer_client.require_confirmation("Démarrer", False, "clic", "Button", TARGET)


def test_click_on_validate_reads_window_context(monkeypatch):
    _window_saying(monkeypatch, "Paiement sécurisé", ["Carte bancaire", "Valider"])
    clicked = MagicMock(return_value={"success": True, "verified": True})
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h: MagicMock())
    monkeypatch.setattr(computer_client, "_element_info", {4: {"type": "Button", "name": "Valider"}})
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "_click_element", clicked)
    res = computer_client.act([{"action": "click", "target": "#4"}], hwnd=TARGET, then="none")
    assert res["success"] is False and res["steps"][0]["error_type"] == "ConfirmationRequiredError"
    clicked.assert_not_called()


# --- Revue d'Antigravity (tour 1) : faux positifs et contournements --------------------------------------------
@pytest.mark.parametrize("keys", ["shift+enter", "alt+enter"])
def test_newline_shortcuts_in_chat_are_free(monkeypatch, keys):
    field = _chat(monkeypatch, "Envoyer")
    computer_client.require_key_confirmation(TARGET, keys, False, field)


@pytest.mark.parametrize("label", ["Formater le document", "Formater la sélection", "Format Document", "Mise en forme"])
def test_document_formatting_is_free(label):
    computer_client.require_confirmation(label, False, "commande de menu", "MenuItem")


@pytest.mark.parametrize(
    "label", ["Formater", "Formater…", "Formater le disque", "Formater la clé USB", "Format drive"]
)
def test_drive_formatting_needs_confirm(label):
    with pytest.raises(computer_client.ConfirmationRequiredError):
        computer_client.require_confirmation(label, False, "commande de menu", "MenuItem")


def test_coordinate_click_on_a_sentence_is_free(monkeypatch):
    sentence = SimpleNamespace(control_type="Text", name="Ne pas oublier d'envoyer le rapport", rect=(0, 0, 300, 20),
                               props={})  # fmt: skip
    root = SimpleNamespace(control_type="Window", name="Notes", rect=(0, 0, 500, 500), props={})
    monkeypatch.setattr(computer_client.user32, "IsWindow", lambda h: 1)
    monkeypatch.setattr(computer_client, "_window_tree",
                        lambda *a, **k: SimpleNamespace(status="ok", nodes=[root, sentence]))  # fmt: skip
    assert computer_client._label_at(TARGET, 10, 10) == ""


def test_enter_in_payment_form_triggers_validate(monkeypatch):
    """Revue d'Antigravity : Entrée dans le champ Montant d'une fenêtre de virement déclencherait « Valider »."""
    field = _chat(monkeypatch, "Valider")
    _window_saying(monkeypatch, "Nouveau virement", [])
    monkeypatch.setattr(computer_client, "_window_tree", lambda *a, **k: _chat_tree("Valider"))
    with pytest.raises(computer_client.ConfirmationRequiredError, match="paiement ou virement"):
        computer_client.require_key_confirmation(TARGET, "enter", False, field)
    computer_client.require_key_confirmation(TARGET, "shift+enter", False, field)


def test_alt_mnemonic_of_send_button_needs_confirm(monkeypatch):
    tree = _chat_tree("Envoyer")
    tree.nodes[7].props["access_key"] = "Alt+E"
    tree.nodes[6].props["access_key"] = "Alt+J"
    monkeypatch.setattr(computer_client, "_window_tree", lambda *a, **k: tree)
    monkeypatch.setattr(win32_controls, "family", lambda hwnd: "WPF")
    with pytest.raises(computer_client.ConfirmationRequiredError, match=r"Alt\+E"):
        computer_client.require_key_confirmation(TARGET, "alt+e", False)
    computer_client.require_key_confirmation(TARGET, "alt+j", False)  # « Joindre » : rien à confirmer
    computer_client.require_key_confirmation(TARGET, "alt+x", False)  # aucun bouton


def test_ctrl_enter_reaches_the_ribbon_send_button(monkeypatch):
    """Revue d'Antigravity : Ctrl+Entrée envoie un mail d'Outlook (bouton « Envoyer » du ruban, loin du corps)."""
    tree = _chat_tree("Micro")
    tree.nodes[2].name = "Envoyer"
    monkeypatch.setattr(computer_client, "_window_tree", lambda *a, **k: tree)
    monkeypatch.setattr(win32_controls, "family", lambda hwnd: "Win32")
    monkeypatch.setattr(win32_controls, "focused_push_button", lambda top: 0)
    monkeypatch.setattr(win32_controls, "default_button", lambda top: 0)
    monkeypatch.setattr(win32_controls, "keyboard_target", lambda top: top)
    with pytest.raises(computer_client.ConfirmationRequiredError, match="bouton d'action de la fenêtre"):
        computer_client.require_key_confirmation(TARGET, "ctrl+enter", False)
    computer_client.require_key_confirmation(TARGET, "enter", False)  # Entrée seule : loin du ruban


@pytest.mark.parametrize("keys", ["space", "enter"])
def test_uia_focused_button_counts_outside_win32(monkeypatch, keys):
    tree = _chat_tree("Envoyer")
    tree.nodes[7].props["focus"] = True
    monkeypatch.setattr(computer_client, "_window_tree", lambda *a, **k: tree)
    monkeypatch.setattr(win32_controls, "family", lambda hwnd: "Chromium")
    with pytest.raises(computer_client.ConfirmationRequiredError, match="focus"):
        computer_client.require_key_confirmation(TARGET, keys, False)


# --- Accord « garde-fous » du 18/10 : gestionnaires de mots de passe jamais lus, dépôt public confirmé ------------
@pytest.mark.parametrize(
    "proc",
    ["KeePass.exe", "KeePassXC.exe", "Bitwarden.exe", "1Password.exe", "Dashlane.exe", "NordPass.exe",
     "RoboForm.exe", "LastPass.exe"],
)  # fmt: skip
def test_password_managers_are_never_read_nor_driven(monkeypatch, proc):
    monkeypatch.setattr(computer_client.user32, "IsWindow", lambda h: 1)
    monkeypatch.setattr(computer_client, "get_process_image_path", lambda pid: ("", proc))
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: TARGET)
    protected, reason = computer_client.is_protected_system_window(TARGET)
    assert protected and "mots de passe" in reason
    tree = MagicMock(side_effect=AssertionError("arbre UIA jamais lu"))
    monkeypatch.setattr(computer_client, "_window_tree", tree)
    monkeypatch.setattr(computer_client, "capture_window_background_gdi", tree)
    for read in (lambda: computer_client.look(hwnd=TARGET), lambda: computer_client.capture_window_image(TARGET)):
        with pytest.raises(computer_client.ProtectedWindowError, match="Rien n'a été lu"):
            read()
    with pytest.raises(PermissionError, match="mots de passe"):
        computer_client.act([{"action": "click", "target": "#1"}], hwnd=TARGET, then="none")


def test_full_screen_capture_refused_while_a_vault_is_shown(monkeypatch):
    windows = [{"hwnd": 1, "process_name": "notepad.exe"}, {"hwnd": 2, "process_name": "KeePassXC.exe"}]
    monkeypatch.setattr(computer_client, "list_windows", lambda visible_only=True: windows)
    monkeypatch.setattr(computer_client.user32, "IsIconic", lambda h: 0)
    with pytest.raises(computer_client.ProtectedWindowError, match="KeePassXC"):
        computer_client.capture_window_image(full_screen=True)
    monkeypatch.setattr(computer_client.user32, "IsIconic", lambda h: 1 if h == 2 else 0)  # réduit : rien d'affiché
    computer_client.ensure_screen_readable()


def test_mcp_never_attaches_an_image_of_a_vault():
    import mcp_server

    assert "ProtectedWindowError" in mcp_server.NO_IMAGE_ERRORS


@pytest.mark.parametrize(
    "label", ["Make public", "Change to public", "I want to make this repository public", "Rendre public",
              "Passer en public", "Rendre le dépôt public"],
)  # fmt: skip
def test_making_a_repository_public_needs_confirm(label):
    with pytest.raises(computer_client.ConfirmationRequiredError):
        computer_client.require_confirmation(label, False, "clic", "Button")


@pytest.mark.parametrize("label", ["Public", "Dépôts publics", "Make private", "Rendre privé"])
def test_public_words_alone_stay_free(label):
    computer_client.require_confirmation(label, False, "clic", "Button")
