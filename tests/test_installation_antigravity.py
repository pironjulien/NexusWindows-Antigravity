"""Installation of the nexus-windows plugin into Antigravity (client/install_antigravity.py, command
`nexus-windows-antigravity install`), on a fake profile (USERPROFILE redirected), never the real one."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = ROOT / "plugins/nexus-windows"
SKILL = "skills/nexus-windows/SKILL.md"


def run(profile: Path, *args: str, check: bool = True):
    env = {**os.environ, "USERPROFILE": str(profile), "PYTHONUTF8": "1"}
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "client/launch.py"), *args],
        env=env,
        capture_output=True,
        text=True,
        check=check,
    )


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def launcher(tmp_path) -> Path:
    path = tmp_path / "clone maison/scripts/start-computer-mcp.ps1"
    path.parent.mkdir(parents=True)
    path.write_text("# lanceur", encoding="utf-8")
    return path


def test_plugin_is_declared_once_and_config_json_never_written(tmp_path, monkeypatch):
    """From PyPI: the server is declared once, at its latest version through uvx (updated at each Antigravity start);
    a discovered plugin is enabled by default, so config.json is left alone (Antigravity rewrites it on exit)."""
    sys.path.insert(0, str(ROOT / "client"))
    import install_antigravity

    monkeypatch.setenv("USERPROFILE", str(tmp_path / "pc"))
    assert install_antigravity.main(["install", "--check"]) == 1
    assert not (tmp_path / "pc/.gemini").exists()  # --check never writes
    assert install_antigravity.main(["install"]) == 0
    assert install_antigravity.main(["install", "--check"]) == 0
    config = tmp_path / "pc/.gemini/config"
    server = read_json(config / "plugins/nexus-windows/mcp_config.json")["mcpServers"]
    assert list(server) == ["nexus-windows"]
    assert Path(server["nexus-windows"]["command"]).stem.lower() == "uvx"
    assert server["nexus-windows"]["args"] == ["--python", "3.14", "nexus-windows-antigravity@latest"]
    assert server["nexus-windows"]["env"] == {"PYTHONUTF8": "1"}
    assert not (config / "mcp_config.json").exists() and not (config / "config.json").exists()
    assert (config / "plugins/nexus-windows" / SKILL).read_bytes() == (PLUGIN_SOURCE / SKILL).read_bytes()
    assert read_json(config / "plugins/nexus-windows/plugin.json") == read_json(PLUGIN_SOURCE / "plugin.json")


def test_clone_launcher_drift_and_obsolete_files_repaired_other_plugins_kept(tmp_path, launcher):
    profile = tmp_path / "pc"
    plugins = profile / ".gemini/config/plugins"
    other = plugins / "github/plugin.json"
    other.parent.mkdir(parents=True)
    other.write_text('{"name": "github"}', encoding="utf-8")
    run(profile, "install", "--launcher", str(launcher))
    server = read_json(plugins / "nexus-windows/mcp_config.json")["mcpServers"]["nexus-windows"]
    assert server == {"command": "pwsh", "args": ["-NoProfile", "-File", str(launcher)]}
    skill = plugins / "nexus-windows" / SKILL
    skill.write_text("local edit", encoding="utf-8")
    stale = plugins / "nexus-windows/hooks.json"  # e.g. the former Google guard copied into this plugin (2.6.0)
    stale.write_text('{"garde-google-mutate": {}}', encoding="utf-8")
    assert run(profile, "install", "--check", "--launcher", str(launcher), check=False).returncode == 1
    run(profile, "install", "--launcher", str(launcher))
    run(profile, "install", "--check", "--launcher", str(launcher))
    assert skill.read_bytes() == (PLUGIN_SOURCE / SKILL).read_bytes()
    assert not stale.exists()
    assert other.read_text(encoding="utf-8") == '{"name": "github"}'


def test_former_duplicate_declarations_are_removed_and_others_kept(tmp_path, launcher):
    """A global mcp_config.json entry (the former installer's, or the one the README had users write for PyPI) and a
    global skills copy doubled the server and its guide: they are removed; the other servers, keys and skills stay."""
    profile = tmp_path / "pc"
    config = profile / ".gemini/config"
    config.mkdir(parents=True)
    others = {
        "nexus-browser": {"command": "python.exe", "args": ["-B", "mcp_server.py"], "env": {"A": "1"}},
        "nexus-android": {"command": "python.exe", "args": ["-m", "nexus_android"]},
    }
    original = {
        "mcpServers": {
            "nexus-browser": others["nexus-browser"],
            "nexus-windows": {"command": "pwsh", "args": ["-NoProfile", "-File", "ancien.ps1"]},
            "nexus-computer": {"command": "pwsh", "args": ["-NoProfile", "-File", "ancien-nom.ps1"]},
            "nexus-windows-antigravity": {"command": "uvx", "args": ["nexus-windows-antigravity"]},
            "nexus-android": others["nexus-android"],
        },
        "custom": {"keep": True},
    }
    (config / "mcp_config.json").write_text(json.dumps(original), encoding="utf-8")
    legacy_skill = config / "skills/nexus-windows/SKILL.md"
    legacy_skill.parent.mkdir(parents=True)
    legacy_skill.write_text("ancienne copie", encoding="utf-8")
    former_name_skill = config / "skills/nexus-computer/SKILL.md"
    former_name_skill.parent.mkdir(parents=True)
    former_name_skill.write_text("ancienne copie sous l'ancien nom", encoding="utf-8")
    browser_skill = config / "skills/nexus-browser/SKILL.md"
    browser_skill.parent.mkdir(parents=True)
    browser_skill.write_text("compétence de NexusBrowser", encoding="utf-8")
    settings = {"userSettings": {"keep": 1}, "plugins": {"nexus-windows": {"enabled": False}}}
    (config / "config.json").write_text(json.dumps(settings), encoding="utf-8")

    result = run(profile, "install", "--launcher", str(launcher))
    run(profile, "install", "--check", "--launcher", str(launcher))
    merged = read_json(config / "mcp_config.json")
    assert list(merged["mcpServers"]) == ["nexus-browser", "nexus-android"]
    assert merged["mcpServers"] == others and merged["custom"] == {"keep": True}
    assert not legacy_skill.exists() and not legacy_skill.parent.exists()
    assert not former_name_skill.exists() and not former_name_skill.parent.exists()
    assert browser_skill.read_text(encoding="utf-8") == "compétence de NexusBrowser"
    # The user's own choice is kept and reported, never overwritten.
    assert read_json(config / "config.json") == settings
    assert "turned off" in result.stdout


def test_former_nexus_computer_plugin_is_replaced_never_two_active(tmp_path, launcher):
    """Identity migration (28/10/2026): the plugin was called nexus-computer. Installing nexus-windows removes the whole
    former folder (its own server declaration and guide), so Antigravity never loads two copies of the engine; --check
    reports a former folder still present."""
    profile = tmp_path / "pc"
    plugins = profile / ".gemini/config/plugins"
    former = plugins / "nexus-computer"
    (former / "skills/nexus-computer").mkdir(parents=True)
    (former / "plugin.json").write_text('{"name": "nexus-computer"}', encoding="utf-8")
    (former / "mcp_config.json").write_text('{"mcpServers": {"nexus-computer": {"command": "pwsh"}}}', encoding="utf-8")
    (former / "skills/nexus-computer/SKILL.md").write_text("ancien guide", encoding="utf-8")
    assert run(profile, "install", "--check", "--launcher", str(launcher), check=False).returncode == 1
    run(profile, "install", "--launcher", str(launcher))
    run(profile, "install", "--check", "--launcher", str(launcher))
    assert not former.exists()
    assert sorted(p.name for p in plugins.iterdir()) == ["nexus-windows"]
    assert list(read_json(plugins / "nexus-windows/mcp_config.json")["mcpServers"]) == ["nexus-windows"]
    (former / "skills").mkdir(parents=True)  # empty folders: nothing declared (Antigravity may still hold them)
    run(profile, "install", "--check", "--launcher", str(launcher))
    (former / "plugin.json").write_text("{}", encoding="utf-8")
    assert run(profile, "install", "--check", "--launcher", str(launcher), check=False).returncode == 1


def test_locked_former_plugin_file_fails_before_the_new_plugin_is_declared(tmp_path, launcher):
    """A former file that cannot be removed (held open) stops the installation before nexus-windows is declared: the
    former plugin stays alone, never two declarations of the engine; once released, installing again completes."""
    profile = tmp_path / "pc"
    former = profile / ".gemini/config/plugins/nexus-computer"
    former.mkdir(parents=True)
    declaration = former / "mcp_config.json"
    declaration.write_text('{"mcpServers": {"nexus-computer": {"command": "pwsh"}}}', encoding="utf-8")
    with declaration.open("rb"):  # Windows: an open file without FILE_SHARE_DELETE cannot be deleted
        assert run(profile, "install", "--launcher", str(launcher), check=False).returncode != 0
        assert not (profile / ".gemini/config/plugins/nexus-windows/mcp_config.json").exists()
    run(profile, "install", "--launcher", str(launcher))
    assert not former.exists()


def test_former_name_turned_off_stays_off_under_the_new_name(tmp_path, launcher):
    """A user who turned nexus-computer off keeps it off: the choice is carried to nexus-windows before the new plugin
    is laid down (a discovered plugin is on by default), the other settings untouched, and reported."""
    profile = tmp_path / "pc"
    config = profile / ".gemini/config"
    config.mkdir(parents=True)
    settings = {
        "userSettings": {"keep": 1},
        "plugins": {"nexus-computer": {"enabled": False}, "github": {"enabled": True}},
    }
    (config / "config.json").write_text(json.dumps(settings), encoding="utf-8")
    assert run(profile, "install", "--check", "--launcher", str(launcher), check=False).returncode == 1
    result = run(profile, "install", "--launcher", str(launcher))
    plugins = read_json(config / "config.json")["plugins"]
    assert plugins["nexus-windows"] == {"enabled": False} and plugins["github"] == {"enabled": True}
    assert read_json(config / "config.json")["userSettings"] == {"keep": 1}
    assert "turned off" in result.stdout
    run(profile, "install", "--check", "--launcher", str(launcher))
    # An explicit choice under the new name always wins.
    plugins["nexus-windows"] = {"enabled": True}
    (config / "config.json").write_text(json.dumps({"plugins": plugins}), encoding="utf-8")
    run(profile, "install", "--launcher", str(launcher))
    assert read_json(config / "config.json")["plugins"]["nexus-windows"] == {"enabled": True}


def test_uninstall_removes_the_plugin_only(tmp_path, launcher):
    profile = tmp_path / "pc"
    run(profile, "install", "--launcher", str(launcher))
    other = profile / ".gemini/config/plugins/github/plugin.json"
    other.parent.mkdir(parents=True)
    other.write_text("{}", encoding="utf-8")
    run(profile, "uninstall")
    assert not (profile / ".gemini/config/plugins/nexus-windows").exists()
    assert other.exists()


def test_guide_option_installs_another_agent_guide_and_check_follows_it(tmp_path, launcher):
    """A private clone keeps its own translation of the agent guide (install.ps1 passes --guide): it replaces the
    shipped English guide, and --check compares against it."""
    profile = tmp_path / "pc"
    guide = tmp_path / "SKILL.fr.md"
    guide.write_text("---\nname: nexus-windows\n---\n# Guide\n", encoding="utf-8")
    run(profile, "install", "--launcher", str(launcher), "--guide", str(guide))
    skill = profile / ".gemini/config/plugins/nexus-windows" / SKILL
    assert skill.read_bytes() == guide.read_bytes()
    run(profile, "install", "--check", "--launcher", str(launcher), "--guide", str(guide))
    assert run(profile, "install", "--check", "--launcher", str(launcher), check=False).returncode == 1


def test_public_guide_is_english_and_private_translation_matches_it():
    """The shipped guide is the public, English one (no first name); the private French copy, when present, keeps the
    same version and the same sections."""
    public = (PLUGIN_SOURCE / SKILL).read_text(encoding="utf-8")
    assert "Julien" not in public and "the user" in public
    private_file = ROOT / "guide/SKILL.fr.md"  # absent from the public copy
    if not private_file.exists():
        return
    private = private_file.read_text(encoding="utf-8")
    version = json.loads((PLUGIN_SOURCE / "plugin.json").read_text(encoding="utf-8"))["version"]
    assert f"(v{version})" in public and f"(v{version})" in private
    heading = [line for line in public.splitlines() if line.startswith("#")]
    assert len(heading) == len([line for line in private.splitlines() if line.startswith("#")])


def test_manifest_uses_only_keys_of_antigravity_plugin_schema():
    """plugin.json follows https://antigravity.google/schemas/v1/plugin.json (additionalProperties false): known keys
    only, at most three suggested prompts, a logo file inside the plugin (marketplace listing)."""
    manifest = read_json(PLUGIN_SOURCE / "plugin.json")
    allowed = {
        "$schema",
        "name",
        "displayName",
        "description",
        "version",
        "logo",
        "suggestedPrompts",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
    }
    assert set(manifest) <= allowed
    assert manifest["$schema"] == "https://antigravity.google/schemas/v1/plugin.json"
    assert 1 <= len(manifest["suggestedPrompts"]) <= 3
    assert (PLUGIN_SOURCE / manifest["logo"]).is_file()
