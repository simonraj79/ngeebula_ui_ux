"""Verify React hosting launch behavior without starting live services."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / 'scripts/start_render.py'
    spec = importlib.util.spec_from_file_location('render_launcher_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module.os, 'chdir', Mock())
    return module


def test_missing_build_fails_before_start(launcher, monkeypatch):
    launch = Mock()
    monkeypatch.setattr(launcher.os, 'execvpe', launch)
    assert launcher.main() == 1
    launch.assert_not_called()


def test_single_process_binds_render_port_and_preserves_env(launcher, monkeypatch):
    (launcher.ROOT / 'web/dist').mkdir(parents=True)
    (launcher.ROOT / 'web/dist/index.html').write_text('<html>React</html>')
    monkeypatch.setenv('PORT', '12345')
    monkeypatch.setenv('EXISTING_SETTING', 'retained')
    launch = Mock()
    monkeypatch.setattr(launcher.os, 'execvpe', launch)
    assert launcher.main() == 0
    executable, command, env = launch.call_args.args
    assert command == [executable, '-m', 'uvicorn', 'backend.main:app', '--host', '0.0.0.0', '--port', '12345', '--workers', '1']
    assert env['NGEEBULA_HOSTED'] == '1'
    assert env['EXISTING_SETTING'] == 'retained'


def test_invalid_port_is_reported(launcher, monkeypatch):
    (launcher.ROOT / 'web/dist').mkdir(parents=True)
    (launcher.ROOT / 'web/dist/index.html').write_text('React')
    monkeypatch.setenv('PORT', 'not-a-port')
    launch = Mock()
    monkeypatch.setattr(launcher.os, 'execvpe', launch)
    assert launcher.main() == 1
    launch.assert_not_called()
