"""Document ouvert par une application Store (MP4 → Lecteur multimédia) : association sans exécutable, cadre UWP titré
au nom de l'application. Activation par ActivateForFile (pid rendu), fenêtre reconnue par l'arbre du pid, nom du
document lu dans l'arbre UI Automation pour une instance déjà ouverte ; repli shell sans contrat d'ouverture.
Portage du correctif de NexusWindows pour Claude 3.3.1 (26/10)."""

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "client"))

import computer_client  # noqa: E402

AUMID = "Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic"
FRAME = {"hwnd": 77, "title": "Lecteur multimédia", "process_name": "ApplicationFrameHost.exe", "process_id": 900}


def _open(tmp_path, windows_after, *, activate=None, before=(), shows=False, startfile=None):
    video = tmp_path / "globale.mp4"
    video.write_bytes(b"")
    calls = {"n": 0}

    def listing(visible_only=True):
        calls["n"] += 1
        return list(before) if calls["n"] == 1 else list(windows_after)

    with (
        patch.object(computer_client, "_assoc_executable", return_value=""),
        patch.object(computer_client, "_packaged_handler", return_value=AUMID),
        patch.object(computer_client, "_activate_for_file", side_effect=activate or (lambda app, path: 900)),
        patch.object(computer_client, "_process_tree", side_effect=lambda pid: {pid}),
        patch.object(computer_client, "_core_window_titles", return_value=set()),
        patch.object(computer_client, "_shows_document", return_value=shows),
        patch.object(computer_client, "list_windows", side_effect=listing),
        patch.object(computer_client, "_give_back_after_open", return_value=False),
        patch.object(computer_client, "OPEN_WAIT_S", 0.6),
        patch.object(computer_client, "DOCUMENT_REUSED_AFTER_S", 0.2),
        patch("os.startfile", side_effect=startfile or AssertionError("document Store jamais ouvert par le shell")),
    ):
        return computer_client.open_path(str(video))


def test_new_store_window_of_the_activated_process_proves_the_opening(tmp_path):
    res = _open(tmp_path, [FRAME])
    assert res["verified"] is True and res["hwnd"] == 77 and res["application"] == AUMID
    assert "Store" in res["verified_by"]


def test_reused_instance_counts_only_if_its_tree_shows_the_document(tmp_path):
    assert _open(tmp_path, [FRAME], before=[FRAME], shows=False)["verified"] is None
    res = _open(tmp_path, [FRAME], before=[FRAME], shows=True)
    assert res["verified"] is True and "instance déjà ouverte" in res["verified_by"]


def test_window_of_another_process_never_counts(tmp_path):
    other = {**FRAME, "hwnd": 78, "process_id": 1234}
    res = _open(tmp_path, [other])
    assert res["verified"] is None and "~ ouverture non vérifiée" in res["message"]


def test_no_file_contract_falls_back_to_the_shell(tmp_path):
    """Photos, Bloc-notes : ActivateForFile refuse (0x80270254), le shell ouvre ; titre portant le nom = preuve."""
    opened: list[str] = []
    named = {"hwnd": 79, "title": "globale.mp4 - Photos", "process_name": "Photos.exe", "process_id": 5}

    def refuse(app, path):
        raise OSError("0x80270254")

    res = _open(tmp_path, [named], activate=refuse, startfile=opened.append)
    assert opened and res["verified"] is True and res["hwnd"] == 79


def test_packaged_handler_is_empty_for_folders_and_unknown_types(tmp_path):
    assert computer_client._packaged_handler(str(tmp_path)) == ""
    assert computer_client._packaged_handler(str(tmp_path / "sans_extension")) == ""


def test_process_tree_contains_the_pid_itself():
    import os

    assert os.getpid() in computer_client._process_tree(os.getpid())
