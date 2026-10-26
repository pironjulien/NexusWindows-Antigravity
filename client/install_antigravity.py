"""Installation du plugin `nexus-computer` dans Antigravity (`~/.gemini/config/plugins/nexus-computer`), en une commande :

    uvx --python 3.14 nexus-windows-antigravity install      (depuis PyPI : aucun clone, ni PowerShell 7, ni Git)

Le plugin (guide de l'agent, manifeste) est copié depuis le paquet ou le clone ; son `mcp_config.json` déclare le
serveur une seule fois : `uvx --python 3.14 nexus-windows-antigravity@latest` (chemin absolu de uvx, pour un
Antigravity déjà ouvert dont le PATH est ancien), ou, depuis un clone (`install.ps1`), le lanceur
`scripts/start-computer-mcp.ps1`. Un plugin découvert est actif par défaut (documentation embarquée d'Antigravity :
`config.json` ne garde qu'un choix explicite de l'utilisateur) : `config.json` n'est jamais écrit, un plugin que
l'utilisateur a désactivé est seulement signalé. Les anciennes déclarations en double (entrée du `mcp_config.json`
global, copie globale `skills/nexus-computer`) sont retirées ; les autres serveurs, plugins et clés restent intacts.
`--check` contrôle sans rien écrire ; `uninstall` retire le plugin. `--guide` (clone privé de Julien) installe son guide en
français (`guide/SKILL.fr.md`, non exporté) à la place du guide public anglais."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

PLUGIN = "nexus-computer"
PACKAGE = "nexus-windows-antigravity"
# Anciennes déclarations globales du même serveur : celle de l'installeur d'avant le plugin, et celle que le README
# faisait écrire à la main pour l'installation depuis PyPI (3.0 à 3.1.3).
GLOBAL_DUPLICATES = (PLUGIN, PACKAGE)
GUIDE = f"skills/{PLUGIN}/SKILL.md"
HERE = Path(__file__).resolve().parent


class Drift(Exception):
    """Contrôle (`--check`) : l'installation n'est pas alignée."""


def config_root() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home()) / ".gemini" / "config"


def plugin_source() -> Path:
    """Plugin livré : `plugin/` dans le paquet PyPI, `plugins/nexus-computer` dans un clone."""
    for candidate in (HERE / "plugin", HERE.parent / "plugins" / PLUGIN):
        if (candidate / "plugin.json").is_file():
            return candidate
    raise FileNotFoundError(f"plugin.json of {PLUGIN} not found next to {HERE}")


def server_declaration(launcher: Path | None) -> dict:
    """Déclaration unique du serveur, écrite dans le `mcp_config.json` du plugin."""
    if launcher is not None:
        return {"command": "pwsh", "args": ["-NoProfile", "-File", str(launcher)]}
    uvx = shutil.which("uvx") or "uvx"
    # @latest : chaque démarrage d'Antigravity lance la dernière version publiée (mise à jour sans l'appli Nexus ni
    # réinstallation ; contrat « mises à jour hors conteneur » du 26/10). Le serveur écrit son état au démarrage.
    return {
        "command": uvx,
        "args": ["--python", "3.14", f"{PACKAGE}@latest"],
        "env": {"PYTHONUTF8": "1"},
    }


class Installer:
    def __init__(self, check: bool) -> None:
        self.check = check
        self.changes = 0
        self.root = config_root()
        self.target = self.root / "plugins" / PLUGIN

    def write(self, path: Path, data: bytes) -> None:
        if path.is_file():
            current = path.read_bytes()
            if current == data:
                return
            if path.suffix == ".json":
                try:
                    if json.loads(current) == json.loads(data):
                        return
                except ValueError:
                    pass
        if self.check:
            raise Drift(f"not aligned: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{PLUGIN}-{uuid.uuid4().hex}")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        self.changes += 1

    def remove(self, path: Path) -> None:
        if self.check:
            raise Drift(f"obsolete file: {path}")
        path.unlink()
        self.changes += 1

    def install(self, launcher: Path | None, guide: Path | None = None) -> None:
        source = plugin_source()
        # 1. Fichiers du plugin, copiés octet pour octet ; ceux que la version livrée n'a plus sont retirés.
        shipped = set()
        for file in sorted(source.rglob("*")):
            relative = file.relative_to(source)
            if not file.is_file() or relative.name == "mcp_config.json" or "__pycache__" in relative.parts:
                continue
            shipped.add(relative)
            data = guide.read_bytes() if guide is not None and relative == Path(GUIDE) else file.read_bytes()
            self.write(self.target / relative, data)
        # Un fichier illisible (chemin de plus de 260 caractères sans les chemins longs de Windows) manquerait sans
        # bruit : le plugin sans son guide n'est pas installé.
        missing = {Path("plugin.json"), Path(GUIDE)} - shipped
        if missing:
            raise FileNotFoundError(f"plugin files not readable in {source}: {', '.join(map(str, sorted(missing)))}")
        if self.target.is_dir():
            for file in sorted(self.target.rglob("*")):
                relative = file.relative_to(self.target)
                if file.is_file() and relative.name != "mcp_config.json" and relative not in shipped:
                    self.remove(file)
            if not self.check:
                for folder in sorted((p for p in self.target.rglob("*") if p.is_dir()), reverse=True):
                    if not any(folder.iterdir()):
                        folder.rmdir()
        # 2. La déclaration unique du serveur.
        declaration = {"mcpServers": {PLUGIN: server_declaration(launcher)}}
        self.write(self.target / "mcp_config.json", (json.dumps(declaration, indent=2) + "\n").encode("utf-8"))
        # 3. Doublons anciens : serveur déclaré aussi dans le mcp_config.json global (outils en double), guide copié
        #    aussi dans les compétences globales.
        global_mcp = self.root / "mcp_config.json"
        if global_mcp.is_file():
            content = json.loads(global_mcp.read_text(encoding="utf-8"))
            servers = content.get("mcpServers") if isinstance(content, dict) else None
            if isinstance(servers, dict) and any(name in servers for name in GLOBAL_DUPLICATES):
                for name in GLOBAL_DUPLICATES:
                    servers.pop(name, None)
                self.write(global_mcp, (json.dumps(content, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        legacy_skill = self.root / "skills" / PLUGIN / "SKILL.md"
        if legacy_skill.is_file():
            self.remove(legacy_skill)
            if not any(legacy_skill.parent.iterdir()):
                legacy_skill.parent.rmdir()

    def disabled_by_user(self) -> bool:
        settings = self.root / "config.json"
        try:
            entry = json.loads(settings.read_text(encoding="utf-8")).get("plugins", {}).get(PLUGIN)
        except (OSError, ValueError, AttributeError):
            return False
        return isinstance(entry, dict) and entry.get("enabled") is False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{PACKAGE} install",
        description="Install the nexus-computer plugin (agent guide + MCP server) into Google Antigravity.",
    )
    parser.add_argument("action", choices=["install", "uninstall"])
    parser.add_argument("--check", action="store_true", help="check the installation without writing anything")
    parser.add_argument("--launcher", type=Path, help="development clone: start the server with this PowerShell script")
    parser.add_argument(
        "--guide", type=Path, help="development clone: install this agent guide instead of the shipped one"
    )
    args = parser.parse_args(argv)
    installer = Installer(check=args.check)
    if args.action == "uninstall":
        if installer.target.is_dir() and not args.check:
            shutil.rmtree(installer.target)
        print(f"NexusWindows for Antigravity: plugin removed from {installer.target}. Restart Antigravity.")
        return 0
    try:
        installer.install(
            args.launcher.resolve() if args.launcher else None, args.guide.resolve() if args.guide else None
        )
    except Drift as drift:
        print(f"NexusWindows for Antigravity: {drift}. Run the install command again.", file=sys.stderr)
        return 1
    if args.check:
        state = "up to date"
    elif installer.changes:
        state = "installed. Restart Antigravity (or open a new conversation) to load it"
    else:
        state = "already up to date"
    print(f"NexusWindows for Antigravity: plugin {PLUGIN} {state} ({installer.target}).")
    if installer.disabled_by_user():
        print("The plugin is turned off in Antigravity: turn it on in Customizations > Installed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
