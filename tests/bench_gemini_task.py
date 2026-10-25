#!/usr/bin/env python3
"""Banc « tâche Gemini » : une petite tâche de formulaire rejouée telle qu'un agent naïf l'enverrait.

Fenêtres de test WinForms et WPF (tests/desktop_fixtures.py) créées ici, sans activation, derrière les fenêtres de
Julien, fermées à la fin. Tâche : remplir Nom, Email, Ville, cocher « Accepter », choisir « Bravo » dans « Formule »,
cliquer « Valider ». L'application elle-même écrit ce qu'elle a reçu (« Résultat : …;Envois=N ») : la réussite est
prouvée par elle, pas par le moteur.

Trois scénarios par famille, par le vrai serveur MCP (fonctions outils de client/mcp_server.py) :
- naïf : ce que Gemini a envoyé le 16/10 — clic par box_2d dans le champ, Ctrl+A, saisie sans cible, case et bouton par
  box_2d ; lot renvoyé une fois tel quel, sans regarder, puis encore tant qu'il ne revient pas réussi (trois envois
  au plus) ;
- guidé : un look puis un seul lot par libellés (set, check, select, click) ;
- liste ouverte : un look, un lot qui remplit, coche et OUVRE la liste « Formule » (click), un look qui doit montrer
  ses options, puis un lot qui choisit « Bravo » dans la liste ouverte et valide (défaut du 16/10 : liste WinForms
  ouverte invisible, « Bravo introuvable », et pourtant `status: success`). Chaque lot doit rendre `status: success`.

Verdict (code de sortie 1 sinon) : chaque scénario donne le résultat attendu (`Formule=Bravo`, `Envois=1`), sans
geste physique ni presse-papiers, et aucun vol de premier plan.

Mesures : réussites vérifiées (étapes `verified` vrai), répétitions bloquées, actions physiques (sessions de vraie
souris/clavier/presse-papiers), envois reçus par l'application, temps total des appels.

Gestes physiques : réels seulement si Julien est inactif depuis 120 s (Raw Input) ; sinon interceptés (comptés, jamais
envoyés, donc jamais réussis) pour ne jamais toucher à sa souris, son clavier, son premier plan ni son presse-papiers.

Usage : python tests/bench_gemini_task.py [--client-dir DOSSIER] [--families winforms,wpf] [--json-out FICHIER]
--client-dir permet de mesurer une autre version du client (mesure « avant »).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parent.parent
PHYSICAL_IDLE_S = 120.0
MAX_SENDS = 3
VALUES = {"Nom": "Julien", "Email": "julien@example.org", "Ville": "Lyon"}
EXPECTED = "Résultat : Nom=Julien;Email=julien@example.org;Ville=Lyon;Accepter=oui;Formule=Bravo;Envois=1"


class PhysicalMeter:
    """Compte les sessions physiques (garde FocusGuard la plus externe, collage presse-papiers) ; les intercepte
    (rien n'est envoyé) quand Julien n'est pas inactif depuis assez longtemps."""

    def __init__(self, cc, real: bool) -> None:
        self.cc = cc
        self.real = real
        self.sessions = 0
        self.clipboard_writes = 0
        self._depth = 0
        meter = self
        original = cc.FocusGuard

        class CountingGuard(original):  # type: ignore[misc, valid-type]
            def __enter__(self):
                if meter._depth == 0:
                    meter.sessions += 1
                meter._depth += 1
                if not meter.real:
                    return self
                try:
                    return super().__enter__()
                except BaseException:
                    meter._depth -= 1
                    raise

            def __exit__(self, *exc):
                meter._depth -= 1
                if not meter.real:
                    return False
                return super().__exit__(*exc)

        cc.FocusGuard = CountingGuard
        original_set_clip = cc.set_clipboard_text

        def set_clip(text: str) -> bool:
            meter.clipboard_writes += 1
            return original_set_clip(text) if meter.real else True

        cc.set_clipboard_text = set_clip
        if not real:
            cc.mouse_click = lambda *a, **k: True
            cc._send_inputs = lambda inputs: len(inputs)
            cc._move_cursor = lambda x, y: None  # geste intercepté : ni curseur ni premier plan touchés
            cc._focused_is_password = lambda: False
            cc.get_clipboard_text = lambda: None
            cc.clipboard_snapshot = lambda: cc.ClipboardSnapshot([])  # presse-papiers de Julien jamais lu ni écrit
            cc.clipboard_restore = lambda snapshot: True
            cc.focus_window = lambda *a, **k: {"success": False, "intercepted": True}

    @property
    def total(self) -> int:
        return self.sessions


def _payload(raw: Any) -> dict[str, Any]:
    """Réponse d'un outil MCP : texte JSON seul, ou liste [texte, image]."""
    if isinstance(raw, (list, tuple)):
        raw = next(item for item in raw if isinstance(item, str))
    return json.loads(raw)


def _naive_lot(state: dict[str, Any]) -> list[dict[str, Any]]:
    boxes = {el["name"]: el["box_2d"] for el in state["elements"]}
    steps: list[dict[str, Any]] = []
    for name, value in VALUES.items():
        steps += [
            {"action": "click", "box_2d": boxes[name]},
            {"action": "key", "key": "ctrl+a"},
            {"action": "type", "text": value},
        ]
    steps += [
        {"action": "click", "box_2d": boxes["Accepter"]},
        {"action": "select", "target": "Formule", "option": "Bravo"},
        {"action": "click", "box_2d": boxes["Valider"]},
    ]
    return steps


def _guided_lot() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [{"action": "set", "target": name, "text": value} for name, value in VALUES.items()]
    steps += [
        {"action": "check", "target": "Accepter"},
        {"action": "select", "target": "Formule", "option": "Bravo"},
        {"action": "click", "target": "Valider"},
    ]
    return steps


def _open_list_lots() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Scénario « liste ouverte » : remplir, cocher, ouvrir la liste ; puis (après un look) choisir et valider."""
    first: list[dict[str, Any]] = [{"action": "set", "target": name, "text": value} for name, value in VALUES.items()]
    first += [{"action": "check", "target": "Accepter"}, {"action": "click", "target": "Formule"}]
    second = [{"action": "click", "target": "Bravo"}, {"action": "click", "target": "Valider"}]
    return first, second


def _count_steps(stats: dict[str, Any], data: dict[str, Any]) -> None:
    for step in data.get("steps", []):
        stats["steps"] += 1
        status = step.get("status")
        if status == "error":
            stats["errors"] += 1
        elif step.get("verified") is True:
            stats["verified"] += 1
        elif status == "failed" or step.get("verified") is False:
            stats["failed"] += 1
        else:
            stats["unverified"] += 1


def run_open_list(mcp, cc, df, fixture, stats: dict[str, Any]) -> float:
    """Ouvrir la liste puis choisir : options visibles dans le look de la liste ouverte, statut de chaque lot."""
    elapsed = 0.0
    t0 = time.perf_counter()
    _payload(mcp.computer_look(hwnd=fixture.hwnd, capture_screenshot=False, max_elements=60, format="json"))
    elapsed += time.perf_counter() - t0
    first, second = _open_list_lots()
    for index, lot in enumerate((first, second)):
        if index == 1:
            t0 = time.perf_counter()
            look = _payload(
                mcp.computer_look(hwnd=fixture.hwnd, capture_screenshot=False, max_elements=60, format="json")
            )
            elapsed += time.perf_counter() - t0
            names = [el["name"] for el in (look.get("data") or {}).get("elements", [])]
            stats["open_list_seen"] = "Bravo" in names
            stats["look_open_s"] = round(time.perf_counter() - t0, 2)
        t0 = time.perf_counter()
        res = _payload(mcp.computer_act(steps=lot, hwnd=fixture.hwnd, then="none"))
        elapsed += time.perf_counter() - t0
        stats["lots_sent"] += 1
        stats["lots_executed"] += res.get("status") != "refused"
        stats.setdefault("statuses", []).append(res.get("status"))
        stats.setdefault("first_next", res.get("next"))
        _count_steps(stats, res.get("data") or {})
    stats["statuses_ok"] = stats["statuses"] == ["success", "success"]
    return elapsed


def run_scenario(mcp, cc, df, make_fixture, scenario: str, meter: PhysicalMeter, watch) -> dict[str, Any]:
    fixture = make_fixture()
    watch.forbidden.add(fixture.pid)
    stats: dict[str, Any] = {
        "family": fixture.name,
        "scenario": scenario,
        "lots_sent": 0,
        "lots_executed": 0,
        "repeats_blocked": 0,
        "steps": 0,
        "verified": 0,
        "unverified": 0,
        "failed": 0,
        "errors": 0,
    }
    sessions_before = meter.sessions
    clip_before = meter.clipboard_writes
    elapsed = 0.0
    try:
        t0 = time.perf_counter()
        look = _payload(mcp.computer_look(hwnd=fixture.hwnd, capture_screenshot=False, max_elements=60, format="json"))
        elapsed += time.perf_counter() - t0
        state = look["data"]
        lot = _naive_lot(state) if scenario == "naïf" else _guided_lot()
        sends = 0 if scenario == "liste ouverte" else MAX_SENDS if scenario == "naïf" else 1
        if scenario == "liste ouverte":
            elapsed += run_open_list(mcp, cc, df, fixture, stats)
        for attempt in range(sends):
            t0 = time.perf_counter()
            res = _payload(mcp.computer_act(steps=lot, hwnd=fixture.hwnd, then="none"))
            elapsed += time.perf_counter() - t0
            stats["lots_sent"] += 1
            if res.get("status") == "refused":
                stats["repeats_blocked"] += 1
                stats.setdefault("next_after_refusal", res.get("next"))
                break  # l'agent suit la consigne (« regarde d'abord ») : fin du renvoi aveugle
            stats["lots_executed"] += 1
            data = res.get("data") or {}
            _count_steps(stats, data)
            stats.setdefault("first_next", data.get("next") or res.get("next"))
            # Agent naïf : renvoie le lot une fois quoi qu'il arrive (comme le 16/10), puis tant qu'il n'est pas réussi.
            if attempt >= 1 and res.get("status") == "success" and data.get("success") is True:
                break
            if scenario != "naïf" and res.get("status") == "success" and data.get("success") is True:
                break
        result = df.wait_result(cc, fixture.hwnd, "Envois=", timeout=1.5)
        stats["result"] = result
        stats["task_ok"] = result == EXPECTED
        stats["sends_received"] = int(result.rsplit("Envois=", 1)[1]) if "Envois=" in result else 0
    finally:
        fixture.close()
    stats["physical_sessions"] = meter.sessions - sessions_before
    stats["clipboard_writes"] = meter.clipboard_writes - clip_before
    stats["time_s"] = round(elapsed, 2)
    return stats


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--client-dir", default=str(REPO_ROOT / "client"))
    parser.add_argument("--families", default="winforms,wpf")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    client_dir = Path(args.client_dir).resolve()
    sys.path.insert(0, str(REPO_ROOT.parent / "commun"))  # jeton commun, même pour un client copié ailleurs
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(client_dir))
    import computer_client as cc
    import computer_logger
    import desktop_fixtures as df
    import mcp_server as mcp
    import physical_input

    # Journal du banc à part : le vrai ~/.nexusagy/computer.log ne reçoit que l'usage réel.
    log_dir = Path(tempfile.mkdtemp(prefix="nexusagy-bench-"))
    computer_logger.LOG_DIR = log_dir
    computer_logger.LOG_FILE = log_dir / "computer.log"
    computer_logger._logger = None
    for handler in list(computer_logger.logging.getLogger("nexusagy.computer").handlers):
        handler.close()
        computer_logger.logging.getLogger("nexusagy.computer").removeHandler(handler)

    raw_ok = physical_input.start(timeout_s=2.0)
    if cc.uia_fast is not None:
        cc.uia_fast.reader()
    idle = physical_input.user_idle_s() if raw_ok else 0.0
    real = raw_ok and idle >= PHYSICAL_IDLE_S
    meter = PhysicalMeter(cc, real)
    watch = df.ForegroundWatch()
    watch.start()
    families = {"winforms": df.winforms_form, "wpf": df.wpf_form}
    rows: list[dict[str, Any]] = []
    try:
        for family in [f.strip().lower() for f in args.families.split(",") if f.strip()]:
            for scenario in ("naïf", "guidé", "liste ouverte"):
                rows.append(run_scenario(mcp, cc, df, families[family], scenario, meter, watch))
    finally:
        watch.stop()

    mode = "réels (Julien inactif)" if real else f"interceptés (Julien actif : inactif depuis {idle:.0f} s)"
    print(f"Banc Gemini {args.label} — client {client_dir} — gestes physiques {mode}")
    print("famille   scénario       lots(env/exé/bloq)  étapes ✓/~/✗/err  physiques  envois  tâche  temps")
    for r in rows:
        print(
            f"{r['family']:<9} {r['scenario']:<14} {r['lots_sent']}/{r['lots_executed']}/{r['repeats_blocked']:<14}"
            f" {r['verified']}/{r['unverified']}/{r['failed']}/{r['errors']:<12} {r['physical_sessions']:<10}"
            f" {r['sends_received']:<7} {'OK' if r['task_ok'] else 'non':<6} {r['time_s']} s"
        )
    summary = {
        "label": args.label,
        "client_dir": str(client_dir),
        "physical": "real" if real else "intercepted",
        "idle_s": round(idle, 1),
        "foreground_stolen_samples": len(watch.hits),
        "rows": rows,
    }
    failures = verdict(rows, len(watch.hits))
    summary["failures"] = failures
    print(json.dumps(summary, ensure_ascii=False))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for failure in failures:
        print(f"ÉCHEC : {failure}")
    return 1 if failures else 0


def verdict(rows: list[dict[str, Any]], foreground_stolen: int) -> list[str]:
    """Écarts au résultat attendu : tâche reçue par l'application, 0 geste physique, 0 vol de premier plan, et pour
    « liste ouverte » options vues dans le look et lots rendus `success`."""
    failures = []
    for r in rows:
        where = f"{r['family']} {r['scenario']}"
        if not r.get("task_ok"):
            failures.append(f"{where} : résultat « {r.get('result')} »")
        if r.get("physical_sessions") or r.get("clipboard_writes"):
            failures.append(
                f"{where} : {r['physical_sessions']} geste(s) physique(s), {r['clipboard_writes']} presse-papiers"
            )
        if r["scenario"] == "liste ouverte":
            if not r.get("open_list_seen"):
                failures.append(f"{where} : options de la liste ouverte absentes du look")
            if not r.get("statuses_ok"):
                failures.append(f"{where} : statuts {r.get('statuses')} (attendu success, success)")
    if foreground_stolen:
        failures.append(f"premier plan pris {foreground_stolen} fois (échantillons de 5 ms)")
    return failures


if __name__ == "__main__":
    sys.exit(main())
