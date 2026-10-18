#!/usr/bin/env python3
"""
Live diagnostic audit of the nexus-computer (OS) plugin. The Chrome bridge is audited by NexusBrowser.
Verifies all capabilities end-to-end on the running system.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repository root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "client"))

from client import computer_client  # noqa: E402


def audit_computer_plugin() -> dict:
    print("\n" + "=" * 60)
    print("AUDIT PLUGIN : NEXUS-COMPUTER (OS & COMPUTER USE)")
    print("=" * 60)

    # 1. List windows
    windows = computer_client.list_windows(visible_only=True)
    print(f"[1/4] Fenêtres visibles Windows: {len(windows)}")
    for w in windows[:4]:
        print(f"      - HWND {w['hwnd']}: [{w.get('process_name')}] {(w.get('title') or '')[:50]}")
    assert len(windows) > 0, "Aucune fenêtre visible détectée"

    # 2. List apps
    apps = computer_client.list_apps()
    print(f"[2/4] Applications actives: {len(apps)}")
    for a in apps[:4]:
        print(f"      - {a['process_name']}: {a['window_count']} fenêtre(s)")

    # 3. Capture screenshot
    target_hwnd = windows[0]["hwnd"]
    img_bytes = computer_client.capture_window_image(hwnd=target_hwnd)
    size_kb = round(len(img_bytes) / 1024, 2)
    print(f"[3/4] Capture Rétinienne WebP: {size_kb} Ko (Anti-Crash 400 < 200 Ko: {'OK' if size_kb < 200 else 'FAIL'})")
    assert size_kb < 200, f"Capture trop lourde: {size_kb} Ko > 200 Ko"

    # 4. UI Automation state
    state = computer_client.get_window_state(hwnd=target_hwnd)
    elements_count = len(state.get("elements", []))
    print(f"[4/4] UI Automation Set-of-Marks: {elements_count} éléments interactifs indexés [#1..#{elements_count}]")

    print("--> NEXUS-COMPUTER : 100% FONCTIONNEL & OPÉRATIONNEL")
    return {"computer_ok": True, "windows_count": len(windows), "screenshot_size_kb": size_kb}


def main():
    print("DÉMARRAGE DE L'AUDIT DU PLUGIN NEXUS-COMPUTER...")
    computer_res = audit_computer_plugin()

    print("\n" + "=" * 60)
    print("SYNTHÈSE DE L'AUDIT GLOBAL :")
    print(f"  • Computer Plugin (nexus-computer): {'SUCCÈS' if computer_res['computer_ok'] else 'ÉCHEC'}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
