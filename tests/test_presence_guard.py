"""Common bench rule (shared bench 7331db8, after a lab window appeared in front of the user on 25/10): no test window
while the user is active; on their first physical input during a run, every open test window is closed at once."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import desktop_fixtures as df  # noqa: E402


class FakeInput:
    def __init__(self, idle: float):
        self.idle = idle
        self.touched = False

    def user_idle_s(self) -> float:
        return self.idle

    def mark(self):
        return (time.monotonic(), 0)

    def user_touched_since(self, _token) -> bool:
        return self.touched


class FakeWindow:
    def __init__(self):
        self.closed = False
        df.LIVE.add(self)

    def close(self) -> None:
        df.LIVE.discard(self)
        self.closed = True


def test_no_test_window_while_the_user_is_active():
    with pytest.raises(df.JulienActive):
        df.PresenceGuard(FakeInput(idle=30)).require_absent()
    df.PresenceGuard(FakeInput(idle=df.ABSENCE_S)).require_absent()


def test_return_of_the_user_closes_every_test_window_and_blocks_new_ones():
    pi = FakeInput(idle=600)
    guard = df.PresenceGuard(pi, poll_s=0.01)
    guard.start()
    try:
        windows = [FakeWindow(), FakeWindow()]
        guard.check()
        pi.touched = True
        deadline = time.monotonic() + 2
        while not guard.returned and time.monotonic() < deadline:
            time.sleep(0.01)
        assert guard.returned and all(w.closed for w in windows) and not df.LIVE
        with pytest.raises(df.JulienActive):
            guard.check()
        with pytest.raises(df.JulienActive):
            df.Fixture("test", ["unused"])  # nothing is launched after the return
    finally:
        guard.stop()
        df.ABORT.clear()
