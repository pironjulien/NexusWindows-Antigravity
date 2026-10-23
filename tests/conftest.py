"""Isolation commune des tests : arrêt d'urgence, journal du bureau et état des agents propres à chaque test."""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))


# Les tests importent le client sous deux noms (« emergency_stop » et « client.emergency_stop ») : deux copies du
# module, chacune redirigée.
_STOP_MODULES = ("emergency_stop", "client.emergency_stop")


@pytest.fixture(autouse=True)
def isolated_emergency_stop(tmp_path_factory, monkeypatch):
    """Aucun test n'écrit ni ne lit le vrai ~/.nexus/stop (il figerait les autres agents de Julien), et chaque test
    part d'un arrêt levé."""
    directory = tmp_path_factory.mktemp("nexus-stop")
    for name in _STOP_MODULES:
        module = importlib.import_module(name)
        monkeypatch.setattr(module, "STOP_FILE", directory / "stop")
        monkeypatch.setattr(module, "OWNER_FILE", directory / "stop.owner")
        monkeypatch.setattr(module, "_latched_until", 0.0)
        monkeypatch.setattr(module, "_seen_version", None)
    yield directory


_LOGGER_MODULES = ("computer_logger", "client.computer_logger")


@pytest.fixture(autouse=True)
def isolated_computer_log(tmp_path_factory, monkeypatch):
    """Aucun test n'écrit dans le vrai ~/.nexusagy/computer.log (constat du 16/10 : cibles factices, « voler »,
    « échec simulé » s'y mêlaient à l'usage réel de Gemini) : journal redirigé vers un dossier temporaire."""
    directory = tmp_path_factory.mktemp("nexus-log")
    for name in _LOGGER_MODULES:
        module = importlib.import_module(name)
        monkeypatch.setattr(module, "LOG_DIR", directory)
        monkeypatch.setattr(module, "LOG_FILE", directory / "computer.log")
    yield directory


@pytest.fixture(autouse=True)
def fresh_agent_state():
    """Chaque test part sans lot mémorisé par la garde anti-répétition ni champ retenu par un clic."""
    for name in ("agent_guard", "client.agent_guard"):
        module = sys.modules.get(name)
        if module is not None:
            module.GUARD.reset()
    for name in ("computer_client", "client.computer_client"):
        module = sys.modules.get(name)
        if module is not None:
            module._designated.clear()
    yield


@pytest.fixture(autouse=True)
def indicator_off(monkeypatch):
    """Aucun logo « agent au travail » pendant les tests : rien ne s'affiche à l'écran de Julien (test_busy_indicator
    l'éprouve sans fenêtre)."""
    monkeypatch.setenv("NEXUS_WINDOWS_INDICATOR", "0")


@pytest.fixture(autouse=True)
def journal_commun_isole(monkeypatch, tmp_path):
    """Journal commun des Nexus Windows dans un dossier du test, jamais le vrai journal du poste (NexusJournal)."""
    monkeypatch.setenv("NEXUS_JOURNAL_HOME", str(tmp_path / "journal-commun"))
