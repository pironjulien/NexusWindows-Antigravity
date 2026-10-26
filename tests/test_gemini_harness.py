"""Harnais conçu pour Gemini (constat du 16/10 : six renvois du même lot « UNVERIFIED », voie physique choisie alors
que l'arrière-plan marchait). Hors ligne : aucune vraie fenêtre de Julien n'est touchée."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "client"))

import agent_guard  # noqa: E402
import computer_client  # noqa: E402
import computer_logger  # noqa: E402
import mcp_server  # noqa: E402
import win32_controls  # noqa: E402


class _NoOpGuard:
    entered = 0

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        type(self).entered += 1
        return self

    def __exit__(self, *exc):
        return False


class FakeField:
    """Champ de saisie UIA factice : motif Value qui écrit vraiment, valeur relue par _read_state."""

    def __init__(self, value: str = ""):
        self.value = value
        self.pattern = MagicMock()
        self.pattern.IsReadOnly = False
        self.pattern.SetValue.side_effect = self._set
        self.ctrl = MagicMock()
        self.ctrl.GetValuePattern.return_value = self.pattern
        self.ctrl.BoundingRectangle = MagicMock(left=10, right=110, top=10, bottom=30)
        self.info = {"type": "Edit", "name": "Nom", "hwnd": 0, "framework": "WPF", "props": {"has_value": True}}

    def _set(self, text):
        self.value = text


@pytest.fixture
def fake_window(monkeypatch):
    """Fenêtre factice 4242 (WPF) : protection, résolution et relecture neutralisées."""
    fields: dict[int, FakeField] = {}
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: 4242)
    monkeypatch.setattr(computer_client, "is_protected_system_window", lambda h: (False, ""))
    monkeypatch.setattr(computer_client, "ensure_default_desktop", lambda: True)
    monkeypatch.setattr(computer_client, "is_electron_window", lambda h: False)
    monkeypatch.setattr(computer_client.win32_controls, "family", lambda h: "WPF")
    monkeypatch.setattr(computer_client.user32, "IsWindow", lambda h: 1)

    def read_state(ctrl, info):
        for field in fields.values():
            if field.ctrl is ctrl:
                return {"value": field.value, "exists": True}
        return {"exists": True}

    monkeypatch.setattr(computer_client, "_read_state", read_state)
    monkeypatch.setattr(computer_client, "FocusGuard", _NoOpGuard)
    _NoOpGuard.entered = 0
    return fields


# -----------------------------------------------------------------------------
# 1. `next` : chaque réponse dit quoi faire ensuite
# -----------------------------------------------------------------------------
def test_marks_and_next_for_unit_results():
    assert agent_guard.mark(True, True) == "✓"
    assert agent_guard.mark(True, True, already=True) == "="
    assert agent_guard.mark(None, None) == "~"
    assert agent_guard.mark(False, False) == "✗"
    assert agent_guard.next_for_result({"verified": True, "success": True}).startswith("✓ fait")
    assert "NE PAS recommencer" in agent_guard.next_for_result({"already": True, "verified": True})
    unknown = agent_guard.next_for_result({"verified": None, "success": None})
    assert unknown.startswith("~") and "image jointe" in unknown and "ne renvoie pas le même lot" in unknown
    failed = agent_guard.next_for_result({"verified": False, "success": False, "verified_by": "valeur inchangée"})
    assert failed.startswith("✗ échec : valeur inchangée")


def test_next_for_errors_names_the_alternative():
    error = computer_client.NeedsForegroundError("long", what="touches « ctrl+s » — impossible en arrière-plan")
    hint = agent_guard.next_for_error(error)
    assert hint.startswith("✗ échec : touches « ctrl+s »") and "foreground=true" in hint
    assert "regarde la fenêtre" in agent_guard.next_for_error(ValueError("Élément cible 'X' introuvable"))
    assert "ne relance pas" in agent_guard.next_for_error(computer_client.UserInterruptError("repris"))
    assert "quelques secondes" in agent_guard.next_for_error(TimeoutError("NexusClaude tient la souris"))
    assert len(agent_guard.next_for_error(RuntimeError("mot " * 200))) < 320  # court, coupé à un mot entier


def test_next_for_act_points_at_the_first_problem():
    ok = {"steps": [{"step": 0, "status": "ok", "mark": "✓"}, {"step": 1, "status": "ok", "mark": "="}]}
    assert agent_guard.next_for_act(ok).startswith("✓")
    unknown = {"steps": [{"step": 0, "status": "ok", "mark": "✓"}, {"step": 1, "status": "unverified", "mark": "~"}]}
    assert "étapes [1]" in agent_guard.next_for_act(unknown)
    failed = {"steps": [{"step": 0, "status": "failed", "mark": "✗", "result": {"verified_by": "coche inchangée"}}]}
    text = agent_guard.next_for_act(failed)
    assert text.startswith("✗ échec à l'étape 0 : coche inchangée") and "renvoie seulement la suite" in text
    error = {"steps": [{"step": 2, "status": "error", "error": "boom", "error_type": "RuntimeError"}]}
    assert agent_guard.next_for_act(error).startswith("étape 2 : ✗ échec : boom")


def _fake_capture(hwnd, max_dimension=1568, return_meta=False):
    """Capture factice (WebP), sans empreinte : jointe à chaque fois."""
    return (b"RIFFwebp", {"image_print": None}) if return_meta else b"RIFFwebp"


def test_mcp_action_reply_carries_next_and_image_when_effect_unseen(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: 4242)
    monkeypatch.setattr(computer_client, "capture_window_image", _fake_capture)
    unseen = {"success": None, "steps": [{"step": 0, "status": "unverified", "mark": "~"}]}
    unseen["next"] = agent_guard.next_for_act(unseen)
    with patch.object(computer_client, "act", return_value=unseen):
        reply = mcp_server.computer_act(steps=[{"action": "click", "target": "OK"}], hwnd=4242)
    assert isinstance(reply, list) and len(reply) == 2
    payload = json.loads(reply[0])
    assert payload["next"].startswith("~ effet non vu")
    assert reply[1].to_image_content().mime_type == "image/webp"

    done = {"success": True, "steps": [{"step": 0, "status": "ok", "mark": "✓"}], "next": agent_guard.NEXT_OK}
    with patch.object(computer_client, "act", return_value=done):
        reply = mcp_server.computer_act(steps=[{"action": "click", "target": "Autre"}], hwnd=4242)
    assert isinstance(reply, str)  # effet relu : aucune image, réponse courte
    assert json.loads(reply)["next"].startswith("✓")


def test_mcp_unit_action_gets_next_and_mark(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: 4242)
    with patch.object(computer_client, "press_key", return_value={"success": True, "verified": True, "sent": True}):
        payload = json.loads(mcp_server.computer_press_key("tab", hwnd=4242))
    assert payload["next"].startswith("✓") and payload["data"]["mark"] == "✓"
    error = computer_client.NeedsForegroundError("x", what="touches « f5 » — impossible en arrière-plan (UWP)")
    monkeypatch.setattr(computer_client, "capture_window_image", _fake_capture)
    with patch.object(computer_client, "press_key", side_effect=error):
        reply = mcp_server.computer_press_key("f5", hwnd=4242)
    payload = json.loads(reply[0])
    assert payload["status"] == "error" and payload["needs_foreground"] is True
    assert payload["next"].startswith("✗ échec : touches « f5 »")


# -----------------------------------------------------------------------------
# 2. Vérification automatique : la plupart des actions reviennent vrai/faux
# -----------------------------------------------------------------------------
def test_click_on_a_field_retains_it_and_typing_without_target_lands_there(fake_window):
    field = FakeField("ancien")
    fake_window[1] = field
    with patch.object(computer_client, "_hit_test", return_value=(field.ctrl, field.info)):
        click = computer_client.click(hwnd=4242, box_2d=[100, 100, 200, 300], foreground=False)
    assert click["verified"] is True and click["method"] == "field_designation"
    assert click["hit_test"] == "Edit « Nom »"
    keys = computer_client.press_key("ctrl+a", hwnd=4242, foreground=False)
    # Revue B4 : sélection notée mais non relue (ni EM_GETSEL ni TextPattern) → ~, jamais ✓.
    assert keys["verified"] is None and keys["method"] == "field_select_all"
    typed = computer_client.type_text("Julien", hwnd=4242, foreground=False)
    assert typed["verified"] is True and typed["method"] == "uia_set_value"
    assert typed["field_from"] == "champ retenu"
    assert field.value == "Julien"  # Ctrl+A noté : texte remplacé, pas ajouté
    assert _NoOpGuard.entered == 0  # aucun geste physique


def test_ctrl_v_on_retained_field_writes_clipboard_in_background(fake_window, monkeypatch):
    field = FakeField("")
    fake_window[1] = field
    computer_client._designate(4242, field.ctrl, field.info)
    monkeypatch.setattr(computer_client, "get_clipboard_text", lambda: "collé")
    res = computer_client.press_key("ctrl+v", hwnd=4242, foreground=False)
    assert res["verified"] is True and res["pasted_from_clipboard"] is True
    assert field.value == "collé"
    assert _NoOpGuard.entered == 0


def test_click_effect_seen_in_uia_tree_when_image_is_unchanged(monkeypatch):
    before = {"title": "t", "windows": (1,), "image": None, "tree": "avant"}
    monkeypatch.setattr(computer_client, "window_fingerprint", lambda hwnd, with_tree=False: dict(before, tree=None))
    monkeypatch.setattr(computer_client, "_tree_digest", lambda hwnd: "après")
    verified, how = computer_client._wait_window_effect(4242, before, timeout=0.05)
    assert verified is True and "arbre" in how
    monkeypatch.setattr(computer_client, "_tree_digest", lambda hwnd: "avant")
    assert computer_client._wait_window_effect(4242, before, timeout=0.05) == (None, "")


def test_point_click_is_brought_back_to_the_element_and_done_in_background(fake_window):
    button = MagicMock()
    info = {"type": "Button", "name": "Valider", "hwnd": 0, "framework": "WPF", "props": {"has_invoke": True}}
    with (
        patch.object(computer_client, "_hit_test", return_value=(button, info)),
        patch.object(computer_client, "_invoke_with_timeout", return_value="invoked") as invoke,
        patch.object(computer_client, "_wait_window_effect", return_value=(True, "image de la fenêtre")),
        patch.object(computer_client, "window_fingerprint", return_value={}),
        patch.object(computer_client, "mouse_click") as mouse,
    ):
        res = computer_client.click(hwnd=4242, box_2d=[500, 400, 560, 600], foreground=True)
    invoke.assert_called_once()
    mouse.assert_not_called()
    assert res["verified"] is True and res["method"] == "uia_invoke" and res["hit_test"] == "Button « Valider »"
    assert not res.get("physical")


# -----------------------------------------------------------------------------
# 3. Garde anti-répétition
# -----------------------------------------------------------------------------
def test_repeat_guard_refuses_blind_resend_and_look_unblocks():
    guard = agent_guard.RepeatGuard(window_s=10)
    lot = {"steps": [{"action": "click", "box_2d": [1, 2, 3, 4]}]}
    assert guard.check("act", 7, lot, now=100.0) is None
    refusal = guard.check("act", 7, lot, now=103.0)
    assert refusal and "Regarde d'abord" in refusal and "repeat=true" in refusal
    assert refusal.startswith("✗") and "RIEN n'a été fait" in refusal  # revue B5 : jamais « = » (déjà fait)
    assert guard.check("act", 8, lot, now=103.5) is None  # autre fenêtre : indépendant
    assert guard.check("act", 7, {"steps": [{"action": "click", "target": "OK"}]}, now=104.0) is None  # autre lot
    guard.observed(7, now=105.0)
    assert guard.check("act", 7, lot, now=106.0) is None  # regardé entre les deux : permis
    assert guard.check("act", 7, lot, now=107.0)  # de nouveau sans regarder : refusé
    assert guard.check("act", 7, lot, repeat=True, now=108.0) is None  # forcé en connaissance de cause
    assert guard.check("act", 7, lot, now=119.0) is None  # au-delà de la fenêtre de 10 s


def test_signature_ignores_key_order():
    assert agent_guard.signature("act", {"a": 1, "b": [1, {"x": 2, "y": 3}]}) == agent_guard.signature(
        "act", {"b": [1, {"y": 3, "x": 2}], "a": 1}
    )


def test_mcp_refuses_same_lot_until_computer_look(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: 4242)
    calls = []

    def act(**kwargs):
        calls.append(kwargs["steps"])
        return {"success": True, "steps": [], "next": agent_guard.NEXT_OK}

    lot = [{"action": "click", "box_2d": [10, 10, 20, 20]}]
    look = {"hwnd": 4242, "elements": []}
    with (
        patch.object(computer_client, "act", side_effect=act),
        patch.object(computer_client, "look", return_value=look),
    ):
        assert json.loads(mcp_server.computer_act(steps=lot, hwnd="Formulaire"))["status"] == "success"
        refused = json.loads(mcp_server.computer_act(steps=lot, hwnd="Formulaire"))
        assert refused["status"] == "refused" and refused["next"] == agent_guard.NEXT_REPEAT
        assert len(calls) == 1  # rien envoyé
        mcp_server.computer_look(hwnd="Formulaire", capture_screenshot=False)
        assert json.loads(mcp_server.computer_act(steps=lot, hwnd="Formulaire"))["status"] == "success"
        forced = json.loads(mcp_server.computer_act(steps=lot, hwnd="Formulaire", repeat=True))
        assert forced["status"] == "success" and len(calls) == 3


def test_unit_tools_are_guarded_too(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: 4242)
    with patch.object(computer_client, "click", return_value={"success": True, "verified": True}) as click:
        assert json.loads(mcp_server.computer_click(hwnd=4242, element_index=3))["status"] == "success"
        assert json.loads(mcp_server.computer_click(hwnd=4242, element_index=3))["status"] == "refused"
        assert json.loads(mcp_server.computer_click(hwnd=4242, element_index=4))["status"] == "success"
    assert click.call_count == 2


# -----------------------------------------------------------------------------
# 4. Arrière-plan d'abord, même avec foreground=True ; presse-papiers en dernier recours
# -----------------------------------------------------------------------------
def test_foreground_true_still_tries_background_first(fake_window):
    field = FakeField("")
    fake_window[1] = field
    computer_client._element_cache.clear()
    computer_client._element_info.clear()
    computer_client._element_cache[1] = field.ctrl
    computer_client._element_info[1] = field.info
    monkey_hwnd = computer_client._cached_window_hwnd
    computer_client._cached_window_hwnd = 4242
    try:
        with patch.object(computer_client, "get_cached_element", return_value=field.ctrl):
            res = computer_client.act(
                [{"action": "set", "target": "#1", "text": "Lyon"}], hwnd=4242, then="none", foreground=True
            )
    finally:
        computer_client._cached_window_hwnd = monkey_hwnd
    assert res["success"] is True and res["physical_steps"] == 0
    assert _NoOpGuard.entered == 0  # aucune garde de lot : le premier plan n'a jamais été pris
    assert field.value == "Lyon"


def test_physical_fallback_types_before_using_the_clipboard(fake_window, monkeypatch):
    sent, clip = [], []
    monkeypatch.setattr(computer_client, "_send_inputs", lambda inputs: sent.append(inputs) or len(inputs))
    monkeypatch.setattr(computer_client, "set_clipboard_text", lambda text: clip.append(text) or True)
    monkeypatch.setattr(computer_client, "get_clipboard_text", lambda: None)
    monkeypatch.setattr(computer_client, "_focused_value", lambda: "court")
    res = computer_client.type_text("court", hwnd=4242, foreground=True)  # aucun champ connu : repli physique
    assert res["method"] == "sendinput_unicode" and clip == [] and sent
    res = computer_client.type_text("ligne 1\nligne 2", hwnd=4242, foreground=True)
    assert res["method"] == "clipboard_paste" and clip == ["ligne 1\nligne 2"]  # multiligne : dernier recours


def test_without_foreground_physical_is_refused_and_nothing_is_sent(fake_window, monkeypatch):
    sent = []
    monkeypatch.setattr(computer_client, "_send_inputs", lambda inputs: sent.append(inputs) or len(inputs))
    with pytest.raises(computer_client.NeedsForegroundError, match="rien n'a été envoyé"):
        computer_client.type_text("x", hwnd=4242, foreground=False)
    with (
        patch.object(computer_client, "_hit_test", return_value=None),
        patch.object(computer_client, "mouse_click") as mouse,
    ):
        res = computer_client.act([{"action": "click", "x": 5, "y": 5}], hwnd=4242, then="none")
    mouse.assert_not_called()
    assert sent == [] and res["steps"][0]["error_type"] == "NeedsForegroundError"
    assert "foreground=true" in res["next"]


# -----------------------------------------------------------------------------
# 5. WPF et UWP : techniques UIA prouvées, refus explicite là où rien n'est possible
# -----------------------------------------------------------------------------
def test_uwp_keyboard_is_refused_explicitly(fake_window, monkeypatch):
    monkeypatch.setattr(computer_client.win32_controls, "family", lambda h: "UWP")
    with patch.object(computer_client, "_send_inputs") as send:
        with pytest.raises(computer_client.NeedsForegroundError, match="UWP/WinUI ignore"):
            computer_client.press_key("enter", hwnd=4242, foreground=False)
    send.assert_not_called()


def test_wpf_shortcut_refused_but_plain_key_posted(fake_window):
    with pytest.raises(computer_client.NeedsForegroundError, match="WPF ignore les raccourcis"):
        computer_client.press_key("ctrl+s", hwnd=4242, foreground=False)
    with (
        patch.object(win32_controls, "post_key", return_value="wm_keydown") as post,
        patch.object(computer_client, "window_fingerprint", return_value={}),
        patch.object(computer_client, "_wait_window_effect", return_value=(True, "image de la fenêtre")),
    ):
        res = computer_client.press_key("tab", hwnd=4242, foreground=False)
    post.assert_called_once_with(4242, 0x09)
    assert res["method"] == "win32_post_key" and res["verified"] is True


def _item(name, runtime_id, selected=False):
    props = {"control_type": 50007, "name": name, "runtime_id": runtime_id, "selected": selected}
    element = MagicMock(name=f"item-{name}")
    return element, props


def test_wpf_option_search_by_tiers_with_runtime_id_dedup(monkeypatch):
    """Sous-arbre d'abord ; liste dépliée puis surgissante apparue ; doublon WPF (même identifiant) compté une fois."""
    ctrl = MagicMock()
    expand = MagicMock()
    expand.ExpandCollapseState = 0
    ctrl.GetExpandCollapsePattern.return_value = expand
    bravo = _item("Bravo", (42, 7))
    tiers = {"sub": [], "popup": [_item("Alpha", (42, 6)), bravo, (bravo[0], dict(bravo[1]))]}
    monkeypatch.setattr(computer_client, "_uia_descendants", lambda c: tiers["sub"])
    monkeypatch.setattr(computer_client, "app_pid", lambda h: 99)
    windows = iter([(1,), (1, 2), (1, 2)])
    monkeypatch.setattr(computer_client, "_process_windows", lambda pid: next(windows, (1, 2)))
    monkeypatch.setattr(computer_client, "_popup_items", lambda hwnds: computer_client._dedup_items(tiers["popup"]))
    selected = []

    def wrap(element, info):
        wrapped = MagicMock()
        wrapped.GetSelectionItemPattern.return_value.Select.side_effect = lambda: selected.append(element)
        return wrapped

    monkeypatch.setattr(computer_client, "_wrap_element", wrap)
    assert computer_client._uia_select_option(ctrl, "Bravo", 4242) == "uia"
    expand.Expand.assert_called_once()
    assert selected == [bravo[0]]
    ambiguous = computer_client._dedup_items([_item("Bravo", (1,)), _item("Bravo", (2,))])
    with pytest.raises(win32_controls.MessageError, match="2 fois"):
        computer_client._pick_item(ambiguous, "Bravo")


def test_uwp_identity_falls_back_to_own_process_for_classic_windows():
    hwnd = computer_client.user32.GetForegroundWindow()
    if not hwnd:
        pytest.skip("aucune fenêtre au premier plan")
    assert computer_client.uwp_core_window(hwnd) == 0 or computer_client.app_pid(hwnd) != 0
    assert computer_client.app_pid(hwnd) > 0


def test_uia_reader_keeps_auto_set_focus_off():
    reader = computer_client.uia_fast.reader()
    assert reader.auto_set_focus is False
    assert {"runtime_id", "pid", "has_scroll_item"} <= set(computer_client.uia_fast.PROPS)


# -----------------------------------------------------------------------------
# 6. Surface d'outils pour Gemini
# -----------------------------------------------------------------------------
LISTED = {"windows", "look", "act", "launch", "window"}  # noms communs des trois NexusWindows


def test_computer_server_lists_five_short_tools_with_one_example_each():
    listed = mcp_server.listed_tool_names(mcp_server.computer_mcp)
    assert set(listed) == LISTED
    for tool in mcp_server.computer_mcp._tool_manager.list_tools():
        if tool.name in LISTED:
            lines = [line for line in (tool.description or "").splitlines() if line.strip()]
            assert 2 <= len(lines) <= 6, tool.name
            assert sum("Example" in line for line in lines) == 1, tool.name
    assert "GOLDEN RULE" in (mcp_server.computer_mcp.instructions or "")
    assert "GOLDEN RULE" in (mcp_server.computer_look.__doc__ or "")


def test_aliases_stay_callable_and_listed_by_the_full_server():
    registered = {tool.name for tool in mcp_server.computer_mcp._tool_manager.list_tools()}
    aliases = {"computer_click", "computer_type_text", "computer_press_key", "computer_get_window_state",
               "computer_take_screenshot", "computer_focus_window", "computer_list_apps"}  # fmt: skip
    assert aliases <= registered  # appelables par leur nom sur le serveur « computer »
    assert not aliases & set(mcp_server.listed_tool_names(mcp_server.computer_mcp))
    assert not hasattr(mcp_server, "combined_mcp")  # revue B12 : serveur « all » mort retiré


def test_guides_are_short_imperative_and_in_sync():
    assert not (REPO_ROOT / "skills").exists()  # revue B12 : une seule copie de la compétence (le plugin)
    skill = (REPO_ROOT / "plugins/nexus-computer/skills/nexus-computer/SKILL.md").read_text(encoding="utf-8")
    assert "GOLDEN RULE" in skill and "| Situation | Tool |" in skill
    assert len(skill.splitlines()) < 90
    # GEMINI.md ne porte plus la doc de l'outil : Julien l'a réservé aux règles souveraines (a4baed2, e0a4a4b, 20d4aa7).


# -----------------------------------------------------------------------------
# 7. Les tests n'écrivent plus dans le vrai journal
# -----------------------------------------------------------------------------
def test_tests_never_write_the_real_computer_log():
    real = Path.home() / ".nexusagy" / "computer.log"
    before = real.stat().st_mtime_ns if real.exists() else None
    size = real.stat().st_size if real.exists() else None
    assert computer_logger.LOG_FILE != real
    computer_logger.log_action("act", "batch", 1, 0.1, "FAILURE", {"error": "échec simulé"})
    assert "échec simulé" in computer_logger.LOG_FILE.read_text(encoding="utf-8")
    if before is not None:
        assert (real.stat().st_mtime_ns, real.stat().st_size) == (before, size)
    import client.computer_logger as package_logger

    assert package_logger.LOG_FILE != real


# -----------------------------------------------------------------------------
# 8. Banc et validation réelle branchés
# -----------------------------------------------------------------------------
def test_bench_and_live_validation_cover_gemini_scenarios():
    bench = (REPO_ROOT / "tests/bench_gemini_task.py").read_text(encoding="utf-8")
    assert "naïf" in bench and "guidé" in bench and "PHYSICAL_IDLE_S = 120.0" in bench
    live = (REPO_ROOT / "tests/live_computer_validation.py").read_text(encoding="utf-8")
    assert "validate_gemini_form" in live and "wpf_form" in live and '"refused"' in live
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    import bench_gemini_task

    lot = bench_gemini_task._naive_lot(
        {
            "elements": [{"name": n, "box_2d": [1, 2, 3, 4]} for n in ("Nom", "Email", "Ville", "Accepter", "Valider")]
        }  # fmt: skip
    )
    assert [s["action"] for s in lot[:3]] == ["click", "key", "type"] and len(lot) == 12


# -----------------------------------------------------------------------------
# 9. Statut global = pire étape (banc du 16/10 : « success » avec une étape en erreur)
# -----------------------------------------------------------------------------
def test_status_reflects_worst_step():
    ok = {"success": True, "steps": [{"step": 0, "status": "ok", "mark": "✓"}]}
    error = {"success": False, "error": "Étape 1", "steps": [{"step": 0, "status": "ok", "mark": "✓"},
             {"step": 1, "status": "error", "mark": "✗", "error": "Bravo introuvable"}]}  # fmt: skip
    unknown = {"success": None, "steps": [{"step": 0, "status": "unverified", "mark": "~"}]}
    already = {"success": True, "steps": [{"step": 0, "status": "ok", "already": True, "mark": "="}]}
    assert agent_guard.status_for(ok) == "success"
    assert agent_guard.status_for(error) == "failed"
    assert agent_guard.status_for({"success": True, "steps": [{"step": 0, "status": "timeout"}]}) == "failed"
    assert agent_guard.status_for(unknown) == "unverified"
    assert agent_guard.status_for(already) == "success" and agent_guard.mark_for_status("success", already) == "="
    assert agent_guard.status_for({"success": False, "verified": False}) == "failed"
    assert agent_guard.status_for({"success": None, "verified": None}) == "unverified"
    assert agent_guard.status_for({"success": True, "already": True}) == "success"


def test_mcp_act_status_and_next_agree_with_the_failing_step(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: 4242)
    monkeypatch.setattr(computer_client, "capture_window_image", _fake_capture)
    data = {"success": False, "error": "Étape 1 (click) : Élément cible 'Bravo' introuvable dans la fenêtre.",
            "steps": [{"step": 0, "status": "ok", "mark": "✓", "verified": True},
                      {"step": 1, "action": "click", "status": "error", "mark": "✗", "error_type": "ValueError",
                       "error": "Élément cible 'Bravo' introuvable dans la fenêtre."}]}  # fmt: skip
    data["next"] = agent_guard.next_for_act(data)
    with patch.object(computer_client, "act", return_value=data):
        reply = mcp_server.computer_act(steps=[{"action": "click", "target": "Bravo"}], hwnd=4242)
    payload = json.loads(reply[0])  # échec : image jointe
    assert payload["status"] == "failed" and payload["data"]["mark"] == "✗"
    assert payload["next"].startswith("étape 1 : ✗ échec") and "look" in payload["next"]
    unseen = {"success": None, "steps": [{"step": 0, "status": "unverified", "mark": "~"}]}
    unseen["next"] = agent_guard.next_for_act(unseen)
    with patch.object(computer_client, "act", return_value=unseen):
        payload = json.loads(mcp_server.computer_act(steps=[{"action": "key", "key": "f5"}], hwnd=4242)[0])
    assert payload["status"] == "unverified" and payload["next"].startswith("~")


def test_mcp_unit_action_status_follows_its_readback(monkeypatch):
    monkeypatch.setattr(computer_client, "resolve_window", lambda hwnd=None: 4242)
    monkeypatch.setattr(computer_client, "capture_window_image", _fake_capture)
    with patch.object(computer_client, "click", return_value={"success": False, "verified": False}):
        payload = json.loads(mcp_server.computer_click(hwnd=4242, element_index=3)[0])
    assert payload["status"] == "failed" and payload["next"].startswith("✗")


def test_bench_open_list_scenario_and_verdict():
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    import bench_gemini_task

    first, second = bench_gemini_task._open_list_lots()
    assert first[-1] == {"action": "click", "target": "Formule"} and second[0] == {"action": "click", "target": "Bravo"}
    good = {"family": "WinForms", "scenario": "liste ouverte", "task_ok": True, "physical_sessions": 0,
            "clipboard_writes": 0, "open_list_seen": True, "statuses_ok": True}  # fmt: skip
    assert bench_gemini_task.verdict([good], 0) == []
    bad = dict(good, task_ok=False, result="Résultat : …;Formule=;Envois=1", statuses_ok=False, statuses=["success"])
    failures = bench_gemini_task.verdict([bad], 2)
    assert len(failures) == 3 and "premier plan" in failures[-1]


def test_resolve_step_target_supports_coordinates_and_box_2d():
    step = {"action": "click", "target": "@250,300"}
    idx, box = computer_client._resolve_step_target(step, 4242)
    assert idx is None and box is None
    assert step["x"] == 250 and step["y"] == 300
    assert "coordonnées relatives" in step["_target_note"]

    step_box = {"action": "click", "target": "box_2d:[100, 200, 300, 400]"}
    idx, box = computer_client._resolve_step_target(step_box, 4242)
    assert idx is None and box == [100, 200, 300, 400]

    step_fallback = {"action": "click", "target": "Inconnu", "x": 100, "y": 200}
    with patch.object(computer_client, "_find_by_label", return_value=(None, None)):
        idx, box = computer_client._resolve_step_target(step_fallback, 4242)
    assert idx is None and box is None
    assert "repli visuel sur coordonnées" in step_fallback["_target_note"]
