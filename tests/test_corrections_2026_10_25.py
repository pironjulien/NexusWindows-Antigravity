"""Three defects seen live in Chrome by NexusWindows for Claude (25/10/2026), checked and fixed here: owned dialogs and
process-name targeting, false success on a Chromium file-picker trigger, false positive of the Enter guard on a help
button next to a field."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "client"))

import computer_client  # noqa: E402


@dataclass
class Node:
    control_type: str
    name: str
    parent: int
    props: dict[str, Any] = field(default_factory=dict)


def form(*buttons: tuple[str, str]) -> list[Node]:
    """Window root, a form group, the field, then the buttons next to it."""
    nodes = [Node("Window", "Page", -1), Node("Group", "Form", 0), Node("Edit", "Description*", 1)]
    nodes += [Node(role, name, 1) for role, name in buttons]
    return nodes


def test_help_button_next_to_a_field_is_not_what_enter_triggers():
    nodes = form(("Button", "Pourquoi ne puis-je pas envoyer cet élément ?"), ("Hyperlink", "Envoyer"))
    assert computer_client._neighbors(nodes, 2) == []


def test_send_button_of_a_composer_stays_protected():
    nodes = form(("Button", "Envoyer"), ("SplitButton", "Publier le post"))
    assert [n.name for n in computer_client._neighbors(nodes, 2)] == ["Envoyer", "Publier le post"]
    assert not computer_client.command_label("Envoyer ce message à toute la liste maintenant")  # a sentence


def test_file_picker_triggers_are_recognised_in_english_and_french():
    for role, name in (
        ("Button", "Choisir un fichier"),
        ("Button", "Parcourir…"),
        ("Hyperlink", "Upload"),
        ("Group", "Déposez vos fichiers ici"),
        ("Button", "Choose file"),
    ):
        assert computer_client.opens_file_picker(role, name), name
    assert not computer_client.opens_file_picker("Button", "Envoyer")
    assert not computer_client.opens_file_picker("Edit", "Upload")  # a field, not a trigger


def window(hwnd: int, title: str, process: str, dialog_of: int = 0) -> dict[str, Any]:
    out: dict[str, Any] = {"hwnd": hwnd, "title": title, "process_name": process}
    if dialog_of:
        out["dialog_of"] = dialog_of
    return out


def test_process_name_targets_the_main_window_and_title_targets_the_dialog():
    windows = [window(10, "Chrome Web Store - Google Chrome", "chrome.exe"), window(11, "Ouvrir", "chrome.exe", 10)]
    keys = ("title", "process_name")
    assert computer_client._pick_window(windows, "chrome", keys) == 10
    assert computer_client._pick_window(windows, "Ouvrir", keys) == 11
    assert "[boîte de 10]" in computer_client._window_line(windows[1])


def test_two_main_windows_of_a_process_stay_ambiguous():
    windows = [window(10, "A - Google Chrome", "chrome.exe"), window(12, "B - Google Chrome", "chrome.exe")]
    try:
        computer_client._pick_window(windows, "chrome", ("title", "process_name"))
    except ValueError as error:
        assert "2 fenêtres" in str(error)
    else:
        raise AssertionError("ambiguous target accepted")


def test_right_click_is_proven_only_by_a_new_menu(monkeypatch):
    """Parity bench of 26/10: a posted right click answered ✓ with no menu received."""
    monkeypatch.setattr(computer_client, "app_pid", lambda _hwnd: 42)
    menus = [{7}]
    monkeypatch.setattr(computer_client, "context_menus", lambda _pid: menus[0])
    verified, how = computer_client._wait_context_menu(1, {7}, timeout=0.05)
    assert verified is None and "aucun menu" in how
    menus[0] = {7, 8}
    verified, how = computer_client._wait_context_menu(1, {7}, timeout=0.05)
    assert verified is True


def test_context_menus_of_a_real_window_list_is_a_set():
    assert isinstance(computer_client.context_menus(0), set)


def test_a_tree_change_alone_does_not_prove_a_chromium_key(monkeypatch):
    """Parity bench of 26/10: the simulated activation moves the focus (tree changed) and Ctrl+K in Electron answered ✓
    with nothing received. Keys sent under simulated activation are proven by structure only (title, windows, size)."""
    same = {"title": "Labo", "windows": (1,), "image": None, "rect": (0, 0, 10, 10), "tree": "avant"}
    monkeypatch.setattr(computer_client, "window_fingerprint", lambda _hwnd, with_tree=False: dict(same))
    monkeypatch.setattr(computer_client, "_tree_digest", lambda _hwnd: "après")  # focus moved by the activation
    verified, _how = computer_client._wait_window_effect(1, dict(same), timeout=0.05, structural_only=True)
    assert verified is None
    verified, how = computer_client._wait_window_effect(1, dict(same), timeout=0.05)
    assert verified is True and "arbre" in how  # without structural_only, the tree alone would have passed
    retitled = dict(same, title="Labo — Ctrl+K")
    monkeypatch.setattr(computer_client, "window_fingerprint", lambda _hwnd, with_tree=False: dict(retitled))
    verified, _how = computer_client._wait_window_effect(1, dict(same), timeout=0.05, structural_only=True)
    assert verified is True


def test_a_label_missing_from_the_window_is_looked_for_in_the_open_menus(monkeypatch):
    """Parity bench of 26/10: right click opened the WinForms context menu (its own top-level window), then "Copier"
    was not found in the main window. It is now looked for in the open menus of the same process, never elsewhere."""
    monkeypatch.setattr(computer_client, "app_pid", lambda _hwnd: 42)
    monkeypatch.setattr(computer_client, "context_menus", lambda _pid: {10, 20})

    def resolve(s, hwnd):
        if hwnd == 20:
            return 3, None
        raise computer_client.TargetNotFoundError("absent")

    monkeypatch.setattr(computer_client, "_resolve_step_target", resolve)
    assert computer_client._resolve_in_open_menus({"target": "Copier"}, 1) == (20, 3, None)
    assert computer_client._resolve_in_open_menus({"target": [1, 2, 3, 4]}, 1) is None


def test_a_changed_control_text_proves_an_effect_but_not_a_chromium_key():
    """26/10: a WinForms status label with a fixed accessible name changed its text, unseen by the UIA tree; the
    action answered ~ although the app received it. A changed native control text now proves the effect."""
    before = {"title": "Labo", "windows": (1,), "image": None, "rect": (0, 0, 10, 10), "controls": "a"}
    after = dict(before, controls="b")
    assert computer_client._fingerprint_changed(before, after) == "texte d'un contrôle"
    assert "texte d'un contrôle" not in computer_client.STRUCTURAL  # simulated-activation keys stay structural only
    assert computer_client._fingerprint_changed(before, dict(before, controls=None)) == ""
