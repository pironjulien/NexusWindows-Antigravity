"""Lancement d'une application Chromium/Electron recouverte (recette commune du 24/10, banc « lancement recouvert ») :
commutateurs anti-occlusion et accessibilité, raccourci à arguments propres gardé tel quel, premier plan rendu même
quand l'application s'active après l'apparition de sa fenêtre."""

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "client"))

import computer_client  # noqa: E402


def _electron(tmp_path: Path) -> Path:
    exe = tmp_path / "app" / "Logi.exe"
    (exe.parent / "resources").mkdir(parents=True)
    (exe.parent / "resources" / "app.asar").write_bytes(b"")
    exe.write_bytes(b"MZ")
    return exe


def test_chromium_app_known_by_its_resources(tmp_path):
    exe = _electron(tmp_path)
    plain = tmp_path / "plain" / "notepad.exe"
    plain.parent.mkdir()
    plain.write_bytes(b"MZ")
    assert computer_client.is_chromium_app(str(exe))
    assert not computer_client.is_chromium_app(str(plain))


def test_shortcut_with_own_arguments_never_rewritten(tmp_path):
    exe = _electron(tmp_path)
    link = str(tmp_path / "Chrome.lnk")
    with patch.object(computer_client, "_shortcut_target", return_value=(str(exe), "--profile-directory=Default")):
        assert computer_client.chromium_launch_target(link) == ""
    with patch.object(computer_client, "_shortcut_target", return_value=(str(exe), "")):
        assert computer_client.chromium_launch_target(link) == str(exe)


def test_open_path_starts_chromium_with_switches(tmp_path):
    exe = _electron(tmp_path)
    started: list[list[str]] = []
    opened = [{"hwnd": 1, "title": "Autre"}]
    shown = {"hwnd": 88, "title": "Logi Options+", "process_name": "logi.exe"}

    def popen(cmd, **kwargs):
        started.append(cmd)
        assert kwargs["startupinfo"].wShowWindow == computer_client.SW_SHOWNOACTIVATE
        opened.append(shown)

    with (
        patch("subprocess.Popen", side_effect=popen),
        patch("os.startfile", side_effect=AssertionError("Chromium jamais ouvert par le shell, sans commutateurs")),
        patch.object(computer_client, "list_windows", side_effect=lambda visible_only=True: list(opened)),
        patch.object(computer_client, "_give_back_after_open", return_value=False),
    ):
        res = computer_client.open_path(str(exe))
    assert started == [[str(exe), "--disable-features=CalculateNativeWinOcclusion", "--force-renderer-accessibility"]]
    assert res["verified"] is True and res["hwnd"] == 88 and "chromium" in res


def test_late_activation_handed_back_by_its_holder(monkeypatch):
    """L'application s'active APRÈS l'apparition de sa fenêtre : le premier plan est rendu par son détenteur."""
    fg = {"hwnd": 500}  # Julien
    clock = {"t": 0.0, "ticks": 0}
    monkeypatch.setattr(computer_client, "OPEN_GIVE_BACK_S", 0.3)
    monkeypatch.setattr(computer_client.user32, "GetForegroundWindow", lambda: fg["hwnd"])
    monkeypatch.setattr(computer_client.win32_controls, "root_of", lambda h: h)
    monkeypatch.setattr(computer_client, "_other_agent_holds_token", lambda: False)
    monkeypatch.setattr(computer_client, "_restore_if_stolen", lambda front: False)
    handed: list[tuple[int, int]] = []

    def hand_back(top, front, timeout_s=0.4):
        handed.append((top, front))
        fg["hwnd"] = front
        return True

    def sleep(s):
        clock["t"] += s
        clock["ticks"] += 1
        if clock["ticks"] == 3:
            fg["hwnd"] = 88  # activation tardive de l'application ouverte

    monkeypatch.setattr(computer_client, "_hand_back", hand_back)
    monkeypatch.setattr(computer_client.time, "sleep", sleep)
    monkeypatch.setattr(computer_client.time, "monotonic", lambda: clock["t"])
    assert computer_client._give_back_after_open({"hwnd": 88}, 500) is True
    assert handed == [(88, 500)] and fg["hwnd"] == 500
