"""Défauts relevés par Antigravity à la passe 2 du banc commun du 28/10/2026 (commun/benchmarks/windows/passe2/
RESULTATS-2026-10-28.md). Hors ligne : aucune fenêtre ouverte, aucune entrée envoyée (os.startfile et Popen simulés)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))

import computer_client  # noqa: E402
import mcp_server  # noqa: E402
import win32_controls  # noqa: E402

TARGET = 333


# =============================================================================
# 1. launch : arguments d'un programme (chaîne entière passée à os.path.exists)
# =============================================================================
@pytest.fixture
def program(tmp_path):
    folder = tmp_path / "Mon Dossier"
    folder.mkdir()
    exe = folder / "Editeur Test.exe"
    exe.write_text("x", encoding="utf-8")
    doc = tmp_path / "notes du jour.txt"
    doc.write_text("x", encoding="utf-8")
    return exe, doc


def test_existing_path_with_spaces_is_never_split(program):
    exe, _doc = program
    assert computer_client._split_launch(str(exe)) == (str(exe), "")
    assert computer_client._split_launch(f'"{exe}"') == (str(exe), "")


def test_arguments_after_the_program_are_split_off(program):
    exe, doc = program
    assert computer_client._split_launch(f"{exe} {doc}") == (str(exe), str(doc))
    assert computer_client._split_launch(f'"{exe}" "{doc}"') == (str(exe), f'"{doc}"')
    head, args = computer_client._split_launch(f"notepad.exe {doc}")
    assert head.lower().endswith("notepad.exe") and Path(head).is_absolute() and args == str(doc)


def test_documents_urls_and_protocols_are_not_split(program, tmp_path):
    _exe, doc = program
    assert computer_client._split_launch(f"{doc} suite") == (f"{doc} suite", "")  # pas un programme : introuvable
    assert computer_client._split_launch("ms-settings:display") == ("ms-settings:display", "")
    assert computer_client._split_launch("https://exemple.fr/a b") == ("https://exemple.fr/a b", "")


def test_arguments_are_split_like_windows():
    assert computer_client.split_command_args(r'"C:\a b\c.txt" d') == [r"C:\a b\c.txt", "d"]
    assert computer_client.split_command_args("  ") == []


def _open(monkeypatch, opened):
    monkeypatch.setattr(computer_client, "OPEN_WAIT_S", 0.4, raising=False)
    monkeypatch.setattr(computer_client, "list_windows", lambda visible_only=True: list(opened))
    monkeypatch.setattr(computer_client, "_give_back_after_open", lambda seen, front: False)


def test_open_path_passes_arguments_and_reads_back_the_document_tab(monkeypatch, program):
    exe, doc = program
    # Fenêtre déjà ouverte du programme : le document passé en argument y arrive en onglet, titre relu.
    opened = [{"hwnd": 5, "title": "Sans titre", "process_name": "Editeur Test.exe"}]
    _open(monkeypatch, opened)

    def start(path, arguments=None):
        assert (path, arguments) == (str(exe), str(doc))
        opened[0] = {"hwnd": 5, "title": f"{doc.name} - Éditeur", "process_name": "Editeur Test.exe"}

    with patch("os.startfile", side_effect=start) as started:
        res = computer_client.open_path(f"{exe} {doc}")
    started.assert_called_once()
    assert res["verified"] is True and res["hwnd"] == 5 and res["arguments"] == str(doc)


def test_mcp_launch_takes_args(monkeypatch, program):
    exe, doc = program
    seen = {}
    monkeypatch.setattr(
        computer_client, "open_path", lambda path_or_url, args="": seen.update(path=path_or_url, args=args) or {}
    )
    mcp_server.launch(str(exe), str(doc))
    assert seen == {"path": str(exe), "args": str(doc)}


def test_arguments_only_for_a_program(monkeypatch, program):
    _exe, doc = program
    _open(monkeypatch, [])
    with patch("os.startfile") as start, pytest.raises(PermissionError, match="programme .exe"):
        computer_client.open_path(str(doc), args="--x")
    start.assert_not_called()


def test_chromium_gets_files_but_never_a_switch(monkeypatch, tmp_path, program):
    _exe, doc = program
    app = tmp_path / "app"
    (app / "resources").mkdir(parents=True)
    (app / "resources" / "app.asar").write_text("x", encoding="utf-8")
    exe = app / "Code.exe"
    exe.write_text("x", encoding="utf-8")
    _open(monkeypatch, [])
    started: list[list[str]] = []
    with patch("subprocess.Popen", side_effect=lambda cmd, **k: started.append(cmd)), patch("os.startfile"):
        for switch in ("--remote-debugging-port=9222", "/user-data-dir=C:\\x", "-inspect"):
            with pytest.raises(PermissionError, match="commutateur"):
                computer_client.open_path(str(exe), args=switch)
        assert started == []
        computer_client.open_path(str(exe), args=f'"{doc}"')
    assert started[0][-1] == str(doc) and started[0][1].startswith("--disable-features=")


# =============================================================================
# 2. menu : racine ouverte d'abord, entrée suivante relue dans le menu surgi
# =============================================================================
def test_win32_menu_matches_unicode_ellipsis_and_accelerators(monkeypatch):
    posted = []
    monkeypatch.setattr(
        win32_controls,
        "menu_items",
        lambda top: [("Fichier > Enregistrer", 10), ("Fichier > Enregistrer sous...", 11), ("Fichier > Exécuter", 12),
                     ("Fichier > Exécuter...", 13)],
    )  # fmt: skip
    monkeypatch.setattr(win32_controls, "post", lambda hwnd, msg, wparam, lparam: posted.append(wparam))
    for path in ("Fichier > Enregistrer sous…", "&Fichier > Enregistrer sous", "fichier > enregistrer sous..."):
        assert win32_controls.menu_command(1, path) == "wm_command_menu"
    win32_controls.menu_command(1, "Fichier > Exécuter...")
    win32_controls.menu_command(1, "Fichier > Exécuter")  # chacun garde la sienne
    assert posted == [11, 11, 11, 13, 12]


def _menu_env(monkeypatch, family):
    monkeypatch.setattr(computer_client, "resolve_window", lambda h: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client.win32_controls, "family", lambda h: family)
    monkeypatch.setattr(computer_client, "window_fingerprint", lambda h, **k: {})
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)


def test_winforms_main_menu_uses_wm_command(monkeypatch):
    # L'éditeur de test (MainMenu WinForms, vraie barre HMENU) : plus réservé à la famille Win32.
    _menu_env(monkeypatch, "WinForms")
    sent = []
    monkeypatch.setattr(computer_client.win32_controls, "menu_items", lambda h: [("Fichier > Enregistrer sous...", 4)])
    monkeypatch.setattr(computer_client.win32_controls, "menu_command", lambda h, p: sent.append(p) or "wm")
    monkeypatch.setattr(computer_client, "_wait_window_effect", lambda h, before: (True, "boîte ouverte"))
    out = computer_client.menu_command("Fichier > Enregistrer sous…", hwnd=TARGET)
    assert sent == ["Fichier > Enregistrer sous…"] and out["technique"] == "WM_COMMAND menu" and out["verified"]


class _Item:
    def __init__(self, expand=True, invoke=True, expand_error=None):
        self.calls: list[str] = []
        self._expand, self._invoke, self._error = expand, invoke, expand_error

    def GetExpandCollapsePattern(self):  # noqa: N802 - API uiautomation
        if not self._expand:
            return None
        item = self

        class _Pattern:
            def Expand(self):  # noqa: N802
                if item._error:
                    raise item._error
                item.calls.append("expand")

            def Collapse(self):  # noqa: N802
                item.calls.append("collapse")

        return _Pattern()

    def GetInvokePattern(self):  # noqa: N802
        return MagicMock() if self._invoke else None


def _uia_menu(monkeypatch, items, appear_after):
    """Menu UIA sans barre HMENU : `items` par libellé ; les entrées de sous-menu n'apparaissent qu'après
    `appear_after` relectures (menu surgi qui se dessine)."""
    _menu_env(monkeypatch, "WinUI")
    monkeypatch.setattr(computer_client, "uia_fast", MagicMock())
    monkeypatch.setattr(computer_client.win32_controls, "menu_items", lambda h: [])
    monkeypatch.setattr(computer_client, "_window_pid", lambda h: 7)
    monkeypatch.setattr(computer_client, "_process_windows", lambda pid: (TARGET, 900))
    monkeypatch.setattr(computer_client, "_checkpoint", lambda: None)
    monkeypatch.setattr(computer_client.time, "sleep", lambda s: None)
    monkeypatch.setattr(computer_client, "_wait_window_effect", lambda h, before: (True, "boîte ouverte"))
    reads = {"n": 0}
    invoked = []

    def find(hwnds, label):
        if label != "Fichier":
            reads["n"] += 1
            if reads["n"] <= appear_after:
                return None
            assert hwnds[0] == 900  # le menu surgi d'abord
        return items.get(label)

    def invoke(item):
        invoked.append(item)
        return "invoked"

    monkeypatch.setattr(computer_client, "_find_menu_item", find)
    monkeypatch.setattr(computer_client, "_invoke_with_timeout", invoke)
    return reads, invoked


def test_root_menu_opened_then_next_item_read_back_until_it_appears(monkeypatch):
    root, leaf = _Item(), _Item(expand=False)
    reads, invoked = _uia_menu(monkeypatch, {"Fichier": root, "Enregistrer sous…": leaf}, appear_after=3)
    out = computer_client.menu_command("Fichier > Enregistrer sous…", hwnd=TARGET)
    assert root.calls == ["expand"] and invoked == [leaf] and reads["n"] == 4
    assert out["technique"] == "UIA menu" and out["verified"] is True


def test_root_without_expand_or_with_refused_expand_is_invoked(monkeypatch):
    for root in (_Item(expand=False), _Item(expand_error=RuntimeError("état courant"))):
        leaf = _Item(expand=False)
        _reads, invoked = _uia_menu(monkeypatch, {"Fichier": root, "Enregistrer": leaf}, appear_after=0)
        computer_client.menu_command("Fichier > Enregistrer", hwnd=TARGET)
        assert invoked == [root, leaf]


def test_missing_item_closes_the_opened_menu(monkeypatch):
    root = _Item()
    _uia_menu(monkeypatch, {"Fichier": root}, appear_after=0)
    monkeypatch.setattr(computer_client, "MENU_OPEN_WAIT_S", 0.0)
    with pytest.raises(RuntimeError, match="introuvable dans le menu ouvert « Fichier »"):
        computer_client.menu_command("Fichier > Absent", hwnd=TARGET)
    assert root.calls == ["expand", "collapse"]


# =============================================================================
# 3. Saisie : une ComboBox modifiable visée mène à SON champ Edit
# =============================================================================
@pytest.fixture
def combo_cache(monkeypatch):
    infos = {
        1: {"type": "ComboBox", "name": "Nom du fichier :", "tree_index": 40, "hwnd": 0},
        2: {"type": "Edit", "name": "", "tree_index": 41, "combo_parent": 40, "hwnd": 0},
        3: {"type": "ComboBox", "name": "Type :", "tree_index": 50, "hwnd": 0},
    }
    controls = {i: MagicMock(name=f"ctrl{i}") for i in infos}
    monkeypatch.setattr(computer_client, "_element_info", infos)
    monkeypatch.setattr(computer_client, "_element_cache", controls)
    monkeypatch.setattr(computer_client, "get_cached_element", lambda i, h=None: controls[i])
    return infos, controls


def test_combo_targeted_by_index_or_alone_by_name_types_into_its_edit(combo_cache):
    # L'Edit sans nom (ou absent du même palier de noms) : choose_label ne voit que la ComboBox, le correctif du 22/10
    # ne départage rien ; la saisie suit quand même l'enfant direct relu dans l'arbre.
    infos, controls = combo_cache
    field = computer_client._combo_edit_field(1, controls[1], infos[1], TARGET)
    assert field is not None
    ctrl, info, idx = field
    assert (ctrl, idx) == (controls[2], 2) and info["type"] == "Edit"


def test_edit_read_live_when_absent_from_the_list(combo_cache):
    infos, controls = combo_cache
    del infos[2]
    edit = MagicMock(ControlTypeName="EditControl", NativeWindowHandle=0, ClassName="Edit")
    edit.Name = "Nom du fichier :"
    inner = MagicMock(ControlTypeName="ComboBoxControl")
    inner.GetChildren.return_value = [edit]  # ComboBoxEx32 > ComboBox > Edit
    controls[1].GetChildren.return_value = [MagicMock(ControlTypeName="ButtonControl"), inner]
    field = computer_client._combo_edit_field(1, controls[1], infos[1], TARGET)
    assert field is not None
    ctrl, info, idx = field
    assert ctrl is edit and info["type"] == "Edit" and idx == 1


def test_non_editable_combo_and_other_roles_are_left_alone(combo_cache):
    infos, controls = combo_cache
    controls[3].GetChildren.return_value = [MagicMock(ControlTypeName="ListControl")]
    assert computer_client._combo_edit_field(3, controls[3], infos[3], TARGET) is None
    assert computer_client._combo_edit_field(2, controls[2], infos[2], TARGET) is None


def test_type_text_on_the_combo_writes_the_edit(monkeypatch, combo_cache):
    infos, controls = combo_cache
    monkeypatch.setattr(computer_client, "_cached_window_hwnd", TARGET)
    monkeypatch.setattr(computer_client, "resolve_window", lambda h: TARGET)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "ensure_default_desktop", lambda: None)
    monkeypatch.setattr(computer_client, "is_electron_window", lambda h: False)
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)
    monkeypatch.setattr(computer_client, "_read_state", lambda c, i: {"value": "rapport.txt"})
    planned = []

    def plan(ctrl, info, hwnd, text, clear_first, method, secret=False):
        planned.append((ctrl, info))
        return "Win32", [("EM_REPLACESEL", lambda: "em")], lambda d: (True, "valeur relue"), text

    monkeypatch.setattr(computer_client, "_text_plan", plan)
    out = computer_client.type_text("rapport.txt", hwnd=TARGET, element_index=1, clear_first=True)
    assert planned == [(controls[2], infos[2])]
    assert out["element_index"] == 2 and "[1]" in out["field_from"] and out["verified"] is True


# =============================================================================
# 4. Raccourci posté sans effet relu (Paint, WinUI) : inconnu, jamais « fait », message vers le bouton ou le menu
# =============================================================================
def test_ignored_posted_shortcut_is_unknown_and_points_to_the_command(monkeypatch):
    monkeypatch.setattr(computer_client, "_designated_field", lambda h: None)
    monkeypatch.setattr(computer_client.win32_controls, "family", lambda h: "Win32")
    monkeypatch.setattr(computer_client.win32_controls, "root_of", lambda h: h)
    monkeypatch.setattr(computer_client.win32_controls, "is_chromium_top", lambda h: False)
    monkeypatch.setattr(computer_client.win32_controls, "keyboard_target", lambda h: h)
    monkeypatch.setattr(computer_client.win32_controls, "post_shortcut", lambda *a, **k: "wm_keydown_modifiers")
    monkeypatch.setattr(computer_client, "window_fingerprint", lambda h, **k: {})
    monkeypatch.setattr(computer_client, "_wait_window_effect", lambda h, before: (None, ""))
    parts = ["ctrl", "shift", "s"]
    out = computer_client._background_keys(
        TARGET, "ctrl+shift+s", parts, [(0x11, False), (0x10, False), (0x53, False)], None
    )
    assert out is not None and out["success"] is None and out["verified"] is None
    assert "bouton ou le menu" in out["message"]
    monkeypatch.setattr(computer_client, "_wait_window_effect", lambda h, before: (True, "boîte ouverte"))
    out = computer_client._background_keys(
        TARGET, "ctrl+shift+s", parts, [(0x11, False), (0x10, False), (0x53, False)], None
    )
    assert out is not None and out["verified"] is True and "message" not in out
