"""Installation of the nexus-computer plugin into Antigravity (scripts/installer-plugin-antigravity.ps1): this product
installs and declares its own plugin, on a fake profile (USERPROFILE redirected), never the real one."""

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = "scripts/installer-plugin-antigravity.ps1"


def run_install(source: Path, profile: Path, *args: str, check: bool = True, app_process: str = "nexus-absent-app"):
    env = {**os.environ, "NEXUSAGY_APP_PROCESS": app_process, "USERPROFILE": str(profile)}
    return subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(source / INSTALLER), *args],
        env=env,
        capture_output=True,
        text=True,
        check=check,
    )


def source_copy(path: Path) -> Path:
    for name in ("scripts", "plugins"):
        shutil.copytree(ROOT / name, path / name)
    return path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_is_declared_once_with_this_clone_path_and_enabled(tmp_path):
    source = source_copy(tmp_path / "clone maison")
    profile = tmp_path / "pc"
    assert run_install(source, profile, "-CheckOnly", check=False).returncode != 0
    assert not (profile / ".gemini").exists()  # -CheckOnly never writes
    run_install(source, profile)
    run_install(source, profile, "-CheckOnly")
    config = profile / ".gemini/config"
    mcp = read_json(config / "plugins/nexus-computer/mcp_config.json")
    assert list(mcp["mcpServers"]) == ["nexus-computer"]
    assert mcp["mcpServers"]["nexus-computer"]["command"] == "pwsh"
    assert mcp["mcpServers"]["nexus-computer"]["args"][-1] == str(source / "scripts/start-computer-mcp.ps1")
    assert not (config / "mcp_config.json").exists()  # no global declaration
    assert read_json(config / "config.json")["plugins"]["nexus-computer"] == {"enabled": True}
    skill = "skills/nexus-computer/SKILL.md"
    assert (config / "plugins/nexus-computer" / skill).read_bytes() == (
        source / "plugins/nexus-computer" / skill
    ).read_bytes()


def test_drift_and_obsolete_files_are_repaired_and_other_plugins_kept(tmp_path):
    source = source_copy(tmp_path / "clone")
    profile = tmp_path / "pc"
    plugins = profile / ".gemini/config/plugins"
    other = plugins / "github/plugin.json"
    other.parent.mkdir(parents=True)
    other.write_text('{"name": "github"}', encoding="utf-8")
    run_install(source, profile)
    skill = plugins / "nexus-computer/skills/nexus-computer/SKILL.md"
    skill.write_text("local edit", encoding="utf-8")
    stale = plugins / "nexus-computer/hooks.json"  # e.g. the former Google guard copied into this plugin (2.6.0)
    stale.write_text('{"garde-google-mutate": {}}', encoding="utf-8")
    assert run_install(source, profile, "-CheckOnly", check=False).returncode != 0
    run_install(source, profile)
    run_install(source, profile, "-CheckOnly")
    assert skill.read_bytes() == (source / "plugins/nexus-computer/skills/nexus-computer/SKILL.md").read_bytes()
    assert not stale.exists()
    assert other.read_text(encoding="utf-8") == '{"name": "github"}'


def test_former_duplicate_declarations_are_removed_and_others_kept(tmp_path):
    """A global mcp_config.json entry and a global skills copy doubled the server and its guide: both are removed;
    nexus-browser, nexus-android, nexus-gmail, the other keys and the other skills stay as they are."""
    source = source_copy(tmp_path / "clone")
    profile = tmp_path / "pc"
    config = profile / ".gemini/config"
    config.mkdir(parents=True)
    others = {
        "nexus-browser": {"command": "python.exe", "args": ["-B", "mcp_server.py"], "env": {"A": "1"}},
        "nexus-android": {"command": "python.exe", "args": ["-m", "nexus_android"]},
        "nexus-gmail": {"command": "python.exe", "args": ["-m", "nexus_gmail.server"]},
    }
    original = {
        "mcpServers": {
            "nexus-browser": others["nexus-browser"],
            "nexus-computer": {"command": "pwsh", "args": ["-NoProfile", "-File", "ancien.ps1"]},
            "nexus-android": others["nexus-android"],
            "nexus-gmail": others["nexus-gmail"],
        },
        "custom": {"keep": True},
    }
    (config / "mcp_config.json").write_text(json.dumps(original), encoding="utf-8")
    legacy_skill = config / "skills/nexus-computer/SKILL.md"
    legacy_skill.parent.mkdir(parents=True)
    legacy_skill.write_text("ancienne copie", encoding="utf-8")
    browser_skill = config / "skills/nexus-browser/SKILL.md"
    browser_skill.parent.mkdir(parents=True)
    browser_skill.write_text("compétence de NexusBrowser", encoding="utf-8")
    (config / "config.json").write_text(
        json.dumps({"userSettings": {"keep": 1}, "plugins": {"github": {"enabled": True}}}), encoding="utf-8"
    )

    run_install(source, profile)
    run_install(source, profile, "-CheckOnly")
    merged = read_json(config / "mcp_config.json")
    assert list(merged["mcpServers"]) == ["nexus-browser", "nexus-android", "nexus-gmail"]
    assert merged["mcpServers"] == others and merged["custom"] == {"keep": True}
    assert not legacy_skill.exists() and not legacy_skill.parent.exists()
    assert browser_skill.read_text(encoding="utf-8") == "compétence de NexusBrowser"
    settings = read_json(config / "config.json")
    assert settings["plugins"] == {"github": {"enabled": True}, "nexus-computer": {"enabled": True}}
    assert settings["userSettings"] == {"keep": 1}


def test_running_antigravity_config_is_not_rewritten(tmp_path):
    """Antigravity open: it rewrites config.json on exit, so the activation is reported, not written."""
    source = source_copy(tmp_path / "clone")
    profile = tmp_path / "pc"
    config = profile / ".gemini/config/config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"plugins": {}}), encoding="utf-8")
    result = run_install(source, profile, app_process="pwsh")
    assert "NON active" in result.stdout
    assert read_json(config) == {"plugins": {}}
    assert (profile / ".gemini/config/plugins/nexus-computer/mcp_config.json").exists()
    run_install(source, profile)
    assert read_json(config)["plugins"]["nexus-computer"] == {"enabled": True}
