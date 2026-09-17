"""Check deployment process supervision without starting servers or using secrets."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def launcher(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/start_render.py"
    spec = importlib.util.spec_from_file_location("render_launcher_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.signal, "signal", Mock())
    monkeypatch.setattr(module.time, "sleep", Mock())
    return module


def test_child_failure_stops_sibling_and_keeps_api_internal(launcher, monkeypatch):
    api, ui = Mock(), Mock()
    api.poll.side_effect = [None, None, None]
    ui.poll.return_value = 1
    popen = Mock(side_effect=[api, ui])
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    response = Mock(status=200)
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(launcher, "urlopen", Mock(return_value=context))
    monkeypatch.setenv("PORT", "12345")
    assert launcher.main() == 1
    api.terminate.assert_called_once()
    api.wait.assert_called_once()
    commands = popen.call_args_list
    assert "127.0.0.1" in commands[0].args[0]
    assert "12345" in commands[1].args[0]
    assert commands[1].kwargs["env"]["NGEEBULA_API_URL"] == "http://127.0.0.1:8000"
    assert commands[1].kwargs["env"]["NGEEBULA_HOSTED"] == "1"


def test_failed_api_never_opens_public_ui(launcher, monkeypatch):
    api = Mock()
    api.poll.return_value = 1
    popen = Mock(return_value=api)
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    assert launcher.main() == 1
    assert popen.call_count == 1
