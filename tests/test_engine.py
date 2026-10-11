import contextlib
import ctypes
from pathlib import Path

import pytest

import engine
from engine import ComputerError, Frame


def test_input_structure_matches_win64_layout():
    assert ctypes.sizeof(engine.INPUT) == 40


@pytest.mark.parametrize("size", [(2560, 1440), (2560, 1392), (1920, 1080), (800, 600), (3840, 2160), (5120, 1440)])
def test_frame_fits_model_limits(size):
    frame = Frame.fit(1, 0, 0, *size)
    assert max(frame.image_width, frame.image_height) <= engine.MAX_LONG_EDGE
    assert frame.image_width * frame.image_height <= engine.MAX_PIXELS * 1.01
    assert frame.image_width <= size[0] and frame.image_height <= size[1]


def test_small_frames_are_not_upscaled():
    frame = Frame.fit(1, 10, 20, 640, 480)
    assert (frame.image_width, frame.image_height) == (640, 480)
    assert frame.to_screen(0, 0) == (10, 20)
    assert frame.to_screen(639, 479) == (649, 499)


def test_image_pixels_map_inside_the_frame_with_an_offset_origin():
    frame = Frame.fit(1, 0, 0, 2560, 1392)
    shifted = Frame.fit(1, 100, 50, 2560, 1392)
    for x, y in [(0, 0), (713, 400), (frame.image_width - 1, frame.image_height - 1)]:
        sx, sy = frame.to_screen(x, y)
        assert 0 <= sx < 2560 and 0 <= sy < 1392
        assert shifted.to_screen(x, y) == (sx + 100, sy + 50)
        assert frame.to_image(sx, sy) == (x, y)


def test_parse_combo_uses_the_layout_for_punctuation():
    for char in ",.-/":
        scan = engine.VkKeyScanW(char)
        vks = engine.parse_combo(f"ctrl+{char}")
        assert vks[0] == engine.VK_CONTROL
        assert vks[-1] == scan & 0xFF
        assert vks[-1] not in (0x2C, 0x2D, 0x2E, 0x2F)  # Never PrintScreen, Insert, Delete or Help.


def test_parse_combo_names_letters_digits_and_plus():
    assert engine.parse_combo("ctrl+shift+p") == [engine.VK_CONTROL, engine.VK_SHIFT, ord("P")]
    assert engine.parse_combo("ctrl+1") == [engine.VK_CONTROL, ord("1")]
    assert engine.parse_combo("alt+f4") == [engine.VK_MENU, 0x73]
    assert engine.parse_combo("win+r") == [0x5B, ord("R")]
    assert engine.parse_combo("ctrl++")[-1] == engine.VkKeyScanW("+") & 0xFF
    assert engine.parse_combo("ctrl+plus") == engine.parse_combo("ctrl++")


@pytest.mark.parametrize("bad", ["", "ctrl+", "ctrl+nope", "+"])
def test_parse_combo_rejects_malformed_input(bad):
    with pytest.raises(ComputerError):
        engine.parse_combo(bad)


def test_emoji_is_sent_as_a_surrogate_pair():
    assert engine.utf16_units("🎉") == [0xD83C, 0xDF89]
    assert engine.utf16_units("é") == [0xE9]


def test_navigation_keys_are_flagged_extended():
    for vk in (0x25, 0x26, 0x27, 0x28, 0x2E, 0x24, 0x23):
        assert engine._key_input(vk, up=False).u.ki.dwFlags & engine.KEYEVENTF_EXTENDEDKEY
    assert not engine._key_input(ord("A"), up=False).u.ki.dwFlags & engine.KEYEVENTF_EXTENDEDKEY


def test_negative_wheel_delta_is_twos_complement():
    assert engine._mouse_input(engine.MOUSEEVENTF_WHEEL, -120).u.mi.mouseData == 0xFFFFFF88


def test_coordinates_outside_the_image_are_refused():
    frame = Frame.fit(1, 0, 0, 2560, 1392)
    frame.check(0, 0)
    frame.check(frame.image_width - 1, frame.image_height - 1)
    for x, y in [(-1, 10), (10, -1), (frame.image_width, 10), (10, frame.image_height)]:
        with pytest.raises(ComputerError, match="hors de l'image"):
            frame.check(x, y)


def test_bare_characters_are_typed_as_themselves():
    for char in "2A,é":
        scan = engine.VkKeyScanW(char)
        if scan == -1:
            continue
        vks = engine.parse_combo(char)
        assert vks[-1] == scan & 0xFF
        assert (engine.VK_SHIFT in vks) == bool((scan >> 8) & 1)
    assert engine.parse_combo("ctrl+2") == [engine.VK_CONTROL, ord("2")]  # Inside a combination: the physical key.


def test_lone_surrogates_are_replaced():
    assert engine.clean("ok\ud83d") == "ok�"
    assert engine.clean("🎉 é") == "🎉 é"


def test_marks_are_drawn_without_changing_the_image_size():
    from PIL import Image

    image = Image.new("RGB", (200, 100), (240, 240, 240))
    engine._draw_marks(image, [(1, (10, 30, 60, 60)), (12, (100, 0, 190, 40))])
    assert image.size == (200, 100)
    assert image.getpixel((10, 45)) == (230, 30, 90)  # Box outline.


def test_badges_of_tiny_neighbours_do_not_overlap():
    taken = []
    for index, box in [(35, (100, 50, 111, 62)), (37, (112, 50, 123, 62)), (39, (124, 50, 135, 62))]:
        spot = engine._badge_spot(box, (16, 12), taken, (400, 200))
        rect = (spot[0], spot[1], spot[0] + 16, spot[1] + 12)
        assert all(rect[2] <= a or rect[0] >= c or rect[3] <= b or rect[1] >= d for a, b, c, d in taken)
        taken.append(rect)


def test_real_input_needs_explicit_foreground():
    import server

    with pytest.raises(ComputerError, match="foreground=True"):
        server._require_foreground(False, "Le clavier")
    server._require_foreground(True, "Le clavier")


def test_every_real_input_tool_exposes_foreground():
    import asyncio

    import server

    tools = {t.name: t.inputSchema["properties"] for t in asyncio.run(server.mcp.list_tools())}
    for name in (
        "computer_click",
        "computer_move_mouse",
        "computer_type_text",
        "computer_press_key",
        "computer_scroll",
        "computer_drag",
    ):
        assert tools[name]["foreground"]["default"] is False


def test_actions_need_a_capture_of_the_target():
    engine.SESSION.frames.clear()
    with pytest.raises(ComputerError, match="Aucune capture"):
        engine.action_frame(engine.SCREEN)


def test_container_badges_never_push_small_badges_away():
    container, button = (0, 0, 400, 200), (0, 0, 30, 14)
    spots = engine._badge_layout([(1, container), (2, button)], {1: (16, 13), 2: (16, 13)}, (400, 200))
    assert spots[2] == (0, 0)  # The button keeps the spot inside its own top-left corner.
    assert spots[1] != (0, 0)


def test_large_containers_get_a_badge_but_no_outline():
    from PIL import Image

    image = Image.new("RGB", (200, 100), (0, 0, 0))
    engine._draw_marks(image, [(1, (0, 0, 200, 100))])
    assert image.getpixel((199, 99)) == (0, 0, 0)  # No outline framing the whole image.
    assert image.getpixel((1, 12)) != (0, 0, 0)  # The badge is still there.


def test_badges_let_the_element_show_through():
    from PIL import Image

    image = Image.new("RGB", (100, 50), (0, 0, 0))
    engine._draw_marks(image, [(7, (10, 10, 60, 30))])
    expected = [c * engine.BADGE_ALPHA / 255 for c in engine.MARK_RGB]
    assert all(abs(got - want) <= 2 for got, want in zip(image.getpixel((11, 22)), expected, strict=True))
    assert 0 < engine.BADGE_ALPHA < 200


class _Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class _FakeControl:
    def __init__(
        self,
        name="",
        control_type="ButtonControl",
        box=(0, 0, 10, 10),
        control_element=True,
        children=(),
        patterns=None,
    ):
        self.Name, self.ControlTypeName, self.IsControlElement = name, control_type, control_element
        self.BoundingRectangle = _Rect(*box)
        self.IsOffscreen, self.IsEnabled, self.HasKeyboardFocus, self.IsKeyboardFocusable = False, True, False, True
        self.children, self.patterns, self.next, self.parent = list(children), patterns or {}, None, None
        for first, second in zip(self.children, self.children[1:]):
            first.next = second
        for child in self.children:
            child.parent = self

    def GetFirstChildControl(self):
        return self.children[0] if self.children else None

    def GetNextSiblingControl(self):
        return self.next

    def GetParentControl(self):
        return self.parent

    def GetPattern(self, pattern_id):
        return self.patterns.get(pattern_id)


def test_elements_outside_the_uia_control_view_are_not_listed(monkeypatch):
    hidden = _FakeControl("Agrandir", box=(100, 0, 120, 20), control_element=False)
    shown = _FakeControl("Restaurer", box=(100, 0, 120, 20))
    inner = _FakeControl("Envoyer", box=(10, 50, 60, 70))
    wrapper = _FakeControl("", "GroupControl", box=(0, 40, 200, 80), control_element=False, children=[inner])
    root = _FakeControl("root", "WindowControl", box=(0, 0, 200, 100), children=[hidden, shown, wrapper])
    monkeypatch.setattr(engine, "current_frame", lambda hwnd: Frame.fit(hwnd, 0, 0, 200, 100))
    monkeypatch.setattr(engine.uia, "ControlFromHandle", lambda hwnd: root)
    _, lines, _ = engine.window_elements(123, max_elements=10)
    names = " ".join(lines)
    assert "Restaurer" in names and "Envoyer" in names  # Children of a non-control element are still visited.
    assert "Agrandir" not in names


class _FakeToggle:
    def __init__(self):
        self.ToggleState, self.waits = 0, []

    def Toggle(self, waitTime):
        self.waits.append(waitTime)
        self.ToggleState = 1


def test_background_toggle_reads_the_new_state_without_the_package_delay():
    toggle = _FakeToggle()
    control = _FakeControl("Option", "CheckBoxControl", patterns={engine.uia.PatternId.TogglePattern: toggle})
    assert engine.background_activate(control) == "coché"
    assert toggle.waits == [0]  # uiautomation sleeps 0.5 s after each call unless told otherwise.


def test_an_expand_that_changes_nothing_is_reported_as_such():
    class Stuck:
        ExpandCollapseState = 0

        def Expand(self, waitTime):
            pass

    control = _FakeControl("Pays", "ComboBoxControl", patterns={engine.uia.PatternId.ExpandCollapsePattern: Stuck()})
    assert engine.background_activate(control) == "dépliage demandé, état inchangé"


@pytest.fixture
def desk(monkeypatch):
    """A fake desktop for ForegroundGuard: window 1 is the user's, 2 the target, 3 another application."""
    state = {"fg": 1, "input": 100, "given": []}
    pids = {1: 10, 2: 20, 3: 30}
    monkeypatch.setattr(engine, "foreground", lambda: state["fg"])
    monkeypatch.setattr(engine, "window_pid", lambda hwnd: pids.get(hwnd, 0))
    monkeypatch.setattr(engine, "z_anchor", lambda hwnd: 0)
    monkeypatch.setattr(engine, "user_input_tick", lambda: state["input"])
    monkeypatch.setattr(engine, "give_foreground", lambda hwnd: state["given"].append(hwnd))
    return state


def test_guard_lets_the_uia_call_finish_then_hands_the_foreground_back(desk):
    guard = engine.ForegroundGuard(2)
    guard._input_tick = 100
    desk["fg"] = 2
    guard._check()
    assert guard.taken == 1 and desk["given"] == []  # The activation belongs to the call (BM_CLICK needs it).
    guard._action_done.set()
    guard._check()
    assert desk["given"] == [1]
    desk["fg"] = 1
    guard._check()
    assert "rendu en" in guard.summary()


def test_guard_never_fights_the_user(desk):
    guard = engine.ForegroundGuard(2)
    guard._input_tick = 100
    guard._action_done.set()
    desk["fg"], desk["input"] = 3, 150  # Julien clicked another application during the action.
    guard._check()
    assert guard.yielded and desk["given"] == []
    assert "sans doute Julien" in guard.summary()


def test_guard_takes_back_a_window_the_action_opened_elsewhere(desk):
    guard = engine.ForegroundGuard(2)
    guard._input_tick = 100
    guard._action_done.set()
    desk["fg"] = 3  # E.g. a link opened in the browser, with no user input since the action started.
    guard._check()
    assert desk["given"] == [1] and not guard.yielded


def test_guard_stays_idle_when_the_user_works_in_the_target(desk):
    desk["fg"] = 2
    assert not engine.ForegroundGuard(2).active


def test_target_goes_back_under_its_anchor(monkeypatch):
    above = {9: [5]}  # The anchor 7 was above the target 9; the action raised 9 over it.
    calls = []

    def set_window_pos(hwnd, after, *args):
        calls.append((hwnd, after, args[-1]))
        above[9] = [5, 7]
        return True

    monkeypatch.setattr(engine, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(engine, "windows_above", lambda hwnd: above[hwnd])
    monkeypatch.setattr(engine, "SetWindowPos", set_window_pos)
    assert engine.restore_z_order(9, 7) is True
    assert calls[0][:2] == (9, 7) and calls[0][2] & engine.SWP_NOACTIVATE
    assert engine.restore_z_order(9, 7) is None  # Already in place: nothing moves.
    assert len(calls) == 1


class _FakeScroll:
    def __init__(self, percent=50.0, step=1.0):
        self.VerticallyScrollable, self.HorizontallyScrollable = True, False
        self.VerticalScrollPercent, self.step, self.calls = percent, step, []

    def Scroll(self, horizontal, vertical, waitTime):
        self.calls.append((horizontal, vertical, waitTime))
        self.VerticalScrollPercent = max(
            0.0, min(100.0, self.VerticalScrollPercent + (self.step if vertical == 4 else -self.step))
        )


def test_background_scroll_climbs_to_the_container_and_reads_the_position_back():
    scroll = _FakeScroll()
    item = _FakeControl("Ligne 1", "ListItemControl")
    _FakeControl("Liste", "ListControl", children=[item], patterns={engine.uia.PatternId.ScrollPattern: scroll})
    assert engine.background_scroll(item, "down", 3) == "position 50 % → 53 %"
    assert scroll.calls == [(2, 4, 0)] * 3  # One small step per notch, without the package's 0.5 s sleeps.


def test_impossible_scroll_positions_are_not_reported():
    class Reversed(_FakeScroll):  # Chromium on a reversed chat list: positions beyond 100 %.
        def Scroll(self, horizontal, vertical, waitTime):
            self.VerticalScrollPercent += 40.0

    page = _FakeControl(
        "Page", "DocumentControl", patterns={engine.uia.PatternId.ScrollPattern: Reversed(percent=277.0)}
    )
    assert engine.background_scroll(page, "up", 1) == "position illisible : vérifier par une capture"
    page = _FakeControl(
        "Page", "DocumentControl", patterns={engine.uia.PatternId.ScrollPattern: _FakeScroll(percent=277.0)}
    )
    assert engine.background_scroll(page, "up", 1) == "position 100 %"


def test_a_scroll_that_moves_nothing_says_so():
    scroll = _FakeScroll(percent=100.0)
    page = _FakeControl("Page", "DocumentControl", patterns={engine.uia.PatternId.ScrollPattern: scroll})
    assert "rien n'a bougé" in engine.background_scroll(page, "down", 1)
    assert engine.background_scroll(_FakeControl("Seul"), "down", 1) is None  # Nothing around it can scroll.


@pytest.mark.parametrize(
    ("class_name", "existing", "synthetic_cr"),
    [
        ("WindowsForms10.RICHEDIT50W.app", "ligne 1\r", True),
        ("RICHEDIT50W", "ligne 1\r\r", True),
        ("RICHEDIT50W", "", True),
        ("Edit", "ligne 1\n", False),
        ("CustomEditor", "ligne 1\r", False),
    ],
)
def test_appending_preserves_existing_line_breaks(class_name, existing, synthetic_cr):
    class Value:
        IsReadOnly = False

        def __init__(self):
            self.Value = existing + ("\r" if synthetic_cr else "")
            self.written = None

        def SetValue(self, text, waitTime):
            self.written = text
            self.Value = text + ("\r" if synthetic_cr else "")

    pattern = Value()
    control = _FakeControl("Saisie", "DocumentControl", patterns={engine.uia.PatternId.ValuePattern: pattern})
    control.ClassName = class_name
    assert engine.set_value(control, "suite", append=True)
    assert pattern.written == existing + "suite"


def test_named_mutex_input_lock():
    with engine.input_lock(timeout_ms=1000):
        # Nested re-entry or inner test
        assert True


def test_drag_tuple_signature_mocked(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "move_cursor", lambda x, y: calls.append(("move", x, y)))
    monkeypatch.setattr(engine, "_send", lambda *args: calls.append(("send", len(args))))
    monkeypatch.setattr(engine, "SetCursorPos", lambda x, y: calls.append(("cursor", x, y)))
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    res = engine.drag(start=(10, 20), end=(100, 200), steps=5)
    assert res is None
    assert any(c[0] == "move" for c in calls)
    assert any(c[0] == "cursor" for c in calls)


def test_drag_coordinate_signature_mocked(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "GetForegroundWindow", lambda: 12345)
    monkeypatch.setattr(engine, "get_window_rect", lambda h: {"left": 100, "top": 100, "width": 800, "height": 600})
    monkeypatch.setattr(engine, "ensure_point", lambda h, x, y: calls.append(("point", x, y)))
    monkeypatch.setattr(engine, "move_cursor", lambda x, y: calls.append(("move", x, y)))
    monkeypatch.setattr(engine, "_send", lambda *args: calls.append(("send", len(args))))
    monkeypatch.setattr(engine, "SetCursorPos", lambda x, y: calls.append(("cursor", x, y)))
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    res = engine.drag(start=10, end=20, to_x=50, to_y=60, hwnd=12345, steps=5)
    assert res["success"] is True
    assert res["from"] == (10, 20)
    assert res["to"] == (50, 60)
    assert res["steps"] == 5
    assert ("point", 110, 120) in calls and ("point", 150, 160) in calls


def test_drag_inactive_window_without_foreground_raises(monkeypatch):
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "GetForegroundWindow", lambda: 99999)  # different foreground

    with pytest.raises(ComputerError, match="requiert la mise au premier plan"):
        engine.drag(start=10, end=20, to_x=50, to_y=60, hwnd=12345, foreground=False)


def test_input_lock_timeout_raises_busy(monkeypatch):
    monkeypatch.setattr(engine, "CreateMutexW", lambda sec, init, name: 1234)
    monkeypatch.setattr(engine, "WaitForSingleObject", lambda handle, timeout: engine.WAIT_TIMEOUT)
    monkeypatch.setattr(engine, "CloseHandle", lambda handle: True)

    with pytest.raises(ComputerError, match="INPUT_BUSY"):
        with engine.input_lock(timeout_ms=100):
            pass


def test_drag_button_released_on_exception(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "GetForegroundWindow", lambda: 12345)
    monkeypatch.setattr(engine, "get_window_rect", lambda h: {"left": 0, "top": 0, "width": 800, "height": 600})
    monkeypatch.setattr(engine, "ensure_point", lambda h, x, y: None)
    monkeypatch.setattr(engine, "move_cursor", lambda x, y: None)
    monkeypatch.setattr(engine, "_send", lambda *args: calls.append("send"))
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    def failing_setpos(x, y):
        raise RuntimeError("Simulated failure during drag trajectory")

    monkeypatch.setattr(engine, "SetCursorPos", failing_setpos)

    with pytest.raises(RuntimeError, match="Simulated failure"):
        engine.drag(start=10, end=20, to_x=50, to_y=60, hwnd=12345, steps=5)

    # 1 down + 1 up in finally
    assert calls.count("send") == 2


def test_scroll_physical_mocked(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "GetForegroundWindow", lambda: 12345)
    monkeypatch.setattr(engine, "get_window_rect", lambda h: {"left": 0, "top": 0, "width": 800, "height": 600})
    monkeypatch.setattr(engine, "ensure_input_target", lambda h: None)
    monkeypatch.setattr(engine, "ensure_point", lambda h, x, y: None)
    monkeypatch.setattr(engine, "scroll_at", lambda x, y, direction, amount: calls.append((x, y, direction, amount)))

    res = engine.scroll(delta_y=-3, delta_x=2, hwnd=12345, foreground=True)
    assert res["success"] is True
    assert ("down", 3) in [(c[2], c[3]) for c in calls]
    assert ("right", 2) in [(c[2], c[3]) for c in calls]
    assert {(c[0], c[1]) for c in calls} == {(400, 300)}  # The window's center, not wherever the cursor was.


@pytest.fixture
def fake_desktop(monkeypatch):
    """A desktop where window 12345 is in front; every input is recorded instead of sent."""
    state = {"foreground": 12345, "sent": []}
    monkeypatch.setattr(engine, "GetForegroundWindow", lambda: state["foreground"])
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "describe", lambda h: f"hwnd {h}")
    monkeypatch.setattr(engine, "get_window_rect", lambda h: {"left": 0, "top": 0, "width": 800, "height": 600})
    monkeypatch.setattr(engine, "ensure_point", lambda h, x, y: None)
    monkeypatch.setattr(engine, "SetCursorPos", lambda x, y: state["sent"].append(("cursor", x, y)))
    monkeypatch.setattr(engine, "_send", lambda *inputs: state["sent"].append(("send", len(inputs))))
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)
    return state


def _contended_lock(state, new_foreground):
    """The lock is granted only after another agent brought its own window forward."""

    @contextlib.contextmanager
    def lock(timeout_ms=5000):
        state["foreground"] = new_foreground
        yield

    return lock


@pytest.mark.parametrize(
    "action",
    [
        lambda: engine.click(hwnd=12345, x=10, y=10),
        lambda: engine.mouse_move(x=10, y=10, hwnd=12345),
        lambda: engine.type_text("abc", hwnd=12345),
        lambda: engine.press_key("ctrl+s", hwnd=12345),
        lambda: engine.scroll(delta_y=-3, hwnd=12345),
        lambda: engine.drag(start=10, end=20, to_x=50, to_y=60, hwnd=12345),
        lambda: engine.drag(start=(10, 20), end=(50, 60), hwnd=12345),
    ],
    ids=["click", "mouse_move", "type_text", "press_key", "scroll", "drag", "drag_tuple"],
)
def test_foreground_is_checked_after_the_lock_is_granted(monkeypatch, fake_desktop, action):
    # Checked before waiting for the lock, the target was in front; once granted, another window is.
    monkeypatch.setattr(engine, "input_lock", _contended_lock(fake_desktop, 99999))
    with pytest.raises(ComputerError, match="requiert la mise au premier plan"):
        action()
    assert fake_desktop["sent"] == []


def test_input_target_holds_the_lock_from_activation_to_the_last_input(monkeypatch):
    events = []

    @contextlib.contextmanager
    def lock(timeout_ms=5000):
        events.append("lock")
        yield
        events.append("unlock")

    monkeypatch.setattr(engine, "input_lock", lock)
    monkeypatch.setattr(engine, "ensure_input_target", lambda h: events.append("front"))
    monkeypatch.setattr(engine, "ensure_point", lambda h, x, y: events.append(("point", x, y)))
    with engine.input_target(42, (1, 2), (3, 4)):
        events.append("input")
    assert events == ["lock", "front", ("point", 1, 2), ("point", 3, 4), "input", "unlock"]


def test_input_target_never_activates_without_permission(monkeypatch, fake_desktop):
    monkeypatch.setattr(
        engine, "ensure_input_target", lambda h: pytest.fail("foreground taken without foreground=True")
    )
    fake_desktop["foreground"] = 99999
    with pytest.raises(ComputerError, match="passez foreground=True"):
        with engine.input_target(12345, activate=False):
            pytest.fail("input sent to a window that is not in front")


@pytest.mark.parametrize("name", ["server.py", "adapters/claude/server.py", "adapters/codex/server.py"])
def test_adapters_send_physical_input_only_inside_input_target(name):
    source = (Path(__file__).resolve().parents[1] / name).read_text(encoding="utf-8")
    assert "ensure_input_target" not in source  # Activation outside the transaction reopens the race.
    assert source.count("engine.input_target(") == 7


def test_legacy_element_from_another_window_is_stale(monkeypatch, fake_desktop):
    control = object()
    monkeypatch.setattr(engine.SESSION, "elements", {1: control})
    monkeypatch.setattr(engine.SESSION, "elements_hwnd", 99999)
    monkeypatch.setattr(engine, "_element_cache", {1: control})
    monkeypatch.setattr(engine, "_cached_window_hwnd", 99999)
    monkeypatch.setattr(engine, "background_activate", lambda c: pytest.fail("element of another window activated"))
    for action in (
        lambda: engine.click(hwnd=12345, element_index=1, foreground=True),
        lambda: engine.type_text("abc", hwnd=12345, element_index=1, foreground=True),
        lambda: engine.scroll(delta_y=-1, hwnd=12345, element_index=1, foreground=True),
    ):
        with pytest.raises(ComputerError, match="STALE_ELEMENT"):
            action()
    assert fake_desktop["sent"] == []


def test_legacy_physical_click_reuses_the_checked_element(monkeypatch, fake_desktop):
    class Rect:
        left, top, right, bottom = 100, 200, 140, 220

    class Control:
        BoundingRectangle = Rect()

    stale = Control()
    stale.BoundingRectangle = None  # Any lookup outside the checked listing would fail.
    monkeypatch.setattr(engine.SESSION, "elements", {1: Control()})
    monkeypatch.setattr(engine.SESSION, "elements_hwnd", 12345)
    monkeypatch.setattr(engine, "_element_cache", {1: stale})
    monkeypatch.setattr(engine, "_cached_window_hwnd", 0)
    monkeypatch.setattr(engine, "ensure_input_target", lambda h: None)
    clicks = []
    monkeypatch.setattr(engine, "click_at", lambda x, y, button, count: clicks.append((x, y, button, count)))
    res = engine.click(hwnd=12345, element_index=1, button="right", foreground=True)
    assert res["method"] == "physical_click"
    assert clicks == [(120, 210, "right", 1)]


def test_legacy_press_key_errors_are_computer_errors(fake_desktop):
    for keys, message in (("", "Combinaison de touches vide"), ("ctrl+invalidkey123", "Touche inconnue")):
        with pytest.raises(ComputerError, match=message):
            engine.press_key(keys)
    fake_desktop["foreground"] = 99999
    with pytest.raises(ComputerError, match="requiert la mise au premier plan"):
        engine.press_key("ctrl+s", hwnd=12345)
    assert fake_desktop["sent"] == []


def test_legacy_press_key_keeps_its_aliases(fake_desktop):
    for alias, vk in (("cmd", 0x5B), ("page_up", 0x21), ("page_down", 0x22), ("return", 0x0D), ("esc", 0x1B)):
        assert engine.press_key(f"ctrl + {alias}")["vk_codes"] == [engine.VK_CONTROL, vk]


def test_drag_tuple_signature_checks_its_window(monkeypatch, fake_desktop):
    monkeypatch.setattr(engine, "IsWindow", lambda h: False)
    with pytest.raises(ComputerError, match="introuvable"):
        engine.drag(start=(10, 20), end=(50, 60), hwnd=777)
    assert fake_desktop["sent"] == []


def test_post_message_click_mocked(monkeypatch):
    posted = []
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "RealChildWindowFromPoint", lambda hwnd, pt: hwnd)
    monkeypatch.setattr(engine, "ScreenToClient", lambda hwnd, pt_ptr: True)
    monkeypatch.setattr(engine, "PostMessageW", lambda h, msg, wparam, lparam: posted.append((h, msg, wparam, lparam)))
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    res = engine.post_message_click(12345, 150, 80, button="left", count=1)
    assert res is True
    expected_lparam = (80 << 16) | 150
    assert (12345, engine.WM_MOUSEMOVE, 0, expected_lparam) in posted
    assert (12345, engine.WM_LBUTTONDOWN, engine.MK_LBUTTON, expected_lparam) in posted
    assert (12345, engine.WM_LBUTTONUP, 0, expected_lparam) in posted

    # Test with target_control_hwnd
    posted.clear()
    res2 = engine.post_message_click(12345, 150, 80, button="left", count=1, target_control_hwnd=99999)
    assert res2 is True
    assert (99999, engine.WM_MOUSEMOVE, 0, expected_lparam) in posted
    assert (99999, engine.WM_LBUTTONDOWN, engine.MK_LBUTTON, expected_lparam) in posted


def test_post_message_type_mocked(monkeypatch):
    chars_posted = []
    sent_messages = []
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(
        engine,
        "SendMessageTimeoutW",
        lambda h, msg, wparam, lparam, flags, timeout, res_ptr: sent_messages.append((h, msg, wparam, lparam)) or 1,
    )
    monkeypatch.setattr(
        engine, "PostMessageW", lambda h, msg, wparam, lparam: chars_posted.append((h, msg, wparam, lparam))
    )
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    # 1. With target_control_hwnd != hwnd: WM_SETTEXT sent to child
    count = engine.post_message_type(12345, "A\nB", target_control_hwnd=99999, clear_first=True)
    assert count == 3
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == 99999
    assert sent_messages[0][1] == engine.WM_SETTEXT
    assert (99999, engine.WM_CHAR, 65, 0) in chars_posted

    # 2. When target == hwnd: WM_SETTEXT must NEVER be sent to root hwnd!
    sent_messages.clear()
    monkeypatch.setattr(engine, "get_focused_child_hwnd", lambda h: None)
    count2 = engine.post_message_type(12345, "C", clear_first=True)
    assert count2 == 1
    assert len(sent_messages) == 0


def test_launch_app_background_uses_sw_showminnoactive(monkeypatch):
    captured = {}

    class FakeProc:
        pid = 4242

    def mock_popen(args, startupinfo=None, shell=False):
        captured["args"] = args
        captured["startupinfo"] = startupinfo
        captured["shell"] = shell
        return FakeProc()

    monkeypatch.setattr(engine.subprocess, "Popen", mock_popen)
    monkeypatch.setattr(
        engine,
        "list_windows",
        lambda visible_only: [
            {"pid": 4242, "hwnd": 1111, "title": "Tooltip"},
            {"pid": 4242, "hwnd": 9876, "title": "Background App"},
        ],
    )
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    res = engine.launch_app("notepad.exe", background=True, wait_ms=10)
    assert res["success"] is True
    assert res["pid"] == 4242
    assert res["hwnd"] == 9876
    assert res["title"] == "Background App"
    assert res["background"] is True
    assert captured["args"] == "notepad.exe"
    assert captured["shell"] is False
    assert captured["startupinfo"].wShowWindow == engine.SW_SHOWMINNOACTIVE


def test_click_method_post_message(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "get_window_rect", lambda h: {"left": 0, "top": 0, "width": 800, "height": 600})
    monkeypatch.setattr(
        engine,
        "post_message_click",
        lambda hwnd, x, y, button="left", count=1, target_control_hwnd=None: calls.append(
            (hwnd, x, y, button, count, target_control_hwnd)
        ),
    )

    res = engine.click(hwnd=12345, x=50, y=60, method="post_message")
    assert res["success"] is True
    assert res["method"] == "post_message"
    assert calls == [(12345, 50, 60, "left", 1, None)]


def test_type_text_method_post_message(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "get_focused_child_hwnd", lambda h: 88888)
    monkeypatch.setattr(
        engine,
        "post_message_type",
        lambda hwnd, text, target_control_hwnd=None, clear_first=False: (
            calls.append((hwnd, text, target_control_hwnd, clear_first)) or len(text)
        ),
    )

    res = engine.type_text("Hello", hwnd=12345, method="post_message", clear_first=True)
    assert res["success"] is True
    assert res["method"] == "post_message_char"
    assert res["length"] == 5
    assert calls == [(12345, "Hello", 88888, True)]


def test_click_and_type_reject_unknown_methods():
    with pytest.raises(ComputerError, match="method inconnue"):
        engine.click(hwnd=12345, x=10, y=10, method="telepathy")
    with pytest.raises(ComputerError, match="method inconnue"):
        engine.type_text("test", hwnd=12345, method="quantum")


def test_type_text_post_message_with_element_and_readback(monkeypatch):
    calls = []

    class FakeValPat:
        Value = "Expected Test Value"

    class FakeControl:
        NativeWindowHandle = 55555

        def GetValuePattern(self):
            return FakeValPat()

    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "_cached_element", lambda h, idx: FakeControl())
    monkeypatch.setattr(
        engine,
        "post_message_type",
        lambda hwnd, text, target_control_hwnd=None, clear_first=False: (
            calls.append((hwnd, text, target_control_hwnd, clear_first)) or len(text)
        ),
    )
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    res = engine.type_text("Test", hwnd=12345, element_index=3, method="post_message", clear_first=True)
    assert res["success"] is True
    assert res["verified_value"] == "Expected Test Value"
    assert calls == [(12345, "Test", 55555, True)]


def test_type_text_post_message_verification_failure_raises(monkeypatch):
    class FakeValPat:
        Value = "Completely Different Value"

    class FakeControl:
        NativeWindowHandle = 55555

        def GetValuePattern(self):
            return FakeValPat()

    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "_cached_element", lambda h, idx: FakeControl())
    monkeypatch.setattr(
        engine,
        "post_message_type",
        lambda hwnd, text, target_control_hwnd=None, clear_first=False: len(text),
    )
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    with pytest.raises(ComputerError, match="Échec de la saisie dans \\[3\\]"):
        engine.type_text("ExpectedText", hwnd=12345, element_index=3, method="post_message")


def test_type_text_post_message_without_element_and_no_focus_raises(monkeypatch):
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "get_focused_child_hwnd", lambda h: None)

    with pytest.raises(ComputerError, match="aucun champ de saisie n'a le focus"):
        engine.type_text("Hello", hwnd=12345, method="post_message")


def test_post_message_click_resolves_nested_child(monkeypatch):
    posted = []
    hierarchy = {1000: 2000, 2000: 3000, 3000: 3000}
    monkeypatch.setattr(engine, "IsWindow", lambda h: True)
    monkeypatch.setattr(engine, "RealChildWindowFromPoint", lambda hwnd, pt: hierarchy.get(hwnd, hwnd))
    monkeypatch.setattr(engine, "ScreenToClient", lambda hwnd, pt_ptr: True)
    monkeypatch.setattr(engine, "PostMessageW", lambda h, msg, wparam, lparam: posted.append((h, msg, wparam, lparam)))
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    res = engine.post_message_click(1000, 100, 100, button="left", count=1)
    assert res is True
    assert posted[0][0] == 3000


def test_launch_app_with_pipes_uses_shell(monkeypatch):
    captured = {}

    class FakeProc:
        pid = 7777

    def mock_popen(args, startupinfo=None, shell=False):
        captured["args"] = args
        captured["shell"] = shell
        return FakeProc()

    monkeypatch.setattr(engine.subprocess, "Popen", mock_popen)
    monkeypatch.setattr(
        engine,
        "list_windows",
        lambda visible_only: [{"pid": 7777, "hwnd": 9999, "title": "Piped Output"}],
    )
    monkeypatch.setattr(engine.time, "sleep", lambda s: None)

    res = engine.launch_app("dir | findstr py", background=True, wait_ms=10)
    assert res["success"] is True
    assert res["pid"] == 7777
    assert captured["shell"] is True
