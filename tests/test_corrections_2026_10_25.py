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
