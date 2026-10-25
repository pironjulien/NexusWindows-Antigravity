"""Commande `nexus-windows-antigravity` du paquet PyPI (uvx) : les modules du client sont chargés à plat, depuis leur
dossier, exactement comme scripts/start-computer-mcp.ps1 lance client/mcp_server.py (un seul exemplaire de chaque
module : un arrêt d'urgence, un seul suivi des gestes de l'utilisateur). `install` / `uninstall` : plugin Antigravity
(install_antigravity.py)."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    if sys.argv[1:2] in (["install"], ["uninstall"]):
        import install_antigravity

        sys.exit(install_antigravity.main(sys.argv[1:]))
    import mcp_server

    mcp_server.main()


if __name__ == "__main__":
    main()
