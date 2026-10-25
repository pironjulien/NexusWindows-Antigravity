"""Product state for the Nexus app (~/.nexus/status/windows-antigravity.json), written at server start: version,
latest version read on PyPI at most once a day, never an exception toward the server."""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))

import status_file  # noqa: E402

NOW = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)


def test_state_is_written_with_the_latest_version_checked_once_a_day(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    calls = []

    def fetch():
        calls.append(1)
        return "3.3.0"

    data = status_file.record("3.2.0", fetch=fetch, now=lambda: NOW)
    path = tmp_path / ".nexus/status/windows-antigravity.json"
    assert json.loads(path.read_text(encoding="utf-8")) == data
    assert data["product"] == "windows-antigravity" and data["version"] == "3.2.0" and data["latest"] == "3.3.0"
    assert data["state"] == "idle" and data["checked_at"] == "2026-10-26T10:00:00Z"
    assert "3.3.0 is available" in data["message"]
    # Same day: PyPI is not asked again; the next day it is.
    status_file.record("3.3.0", fetch=fetch, now=lambda: NOW + timedelta(hours=5))
    assert len(calls) == 1
    later = status_file.record("3.3.0", fetch=fetch, now=lambda: NOW + timedelta(days=1, minutes=1))
    assert len(calls) == 2 and later["message"] == "Up to date."


def test_network_failure_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    def fetch():
        raise OSError("offline")

    data = status_file.record("3.2.0", fetch=fetch, now=lambda: NOW)
    assert data["state"] == "failed" and data["latest"] == "" and "OSError" in data["message"]


def test_update_check_can_be_turned_off(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("NEXUS_UPDATE_CHECK", "off")

    def fetch():
        raise AssertionError("no request when the check is off")

    data = status_file.record("3.2.0", fetch=fetch, now=lambda: NOW)
    assert data["latest"] == "" and data["state"] == "idle"
