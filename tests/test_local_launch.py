"""Local launcher configuration tests: no credential lookup or model requests."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_footie_local as launch


@pytest.fixture
def isolated_launch(tmp_path, monkeypatch):
    # The launcher writes environment defaults directly; contain every mutation.
    monkeypatch.setattr(launch.os, 'environ', dict(launch.os.environ))
    for name in ('AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_DEPLOYMENT', 'AZURE_OPENAI_API_KEY',
                 'AZURE_OPENAI_AUTH_MODE', 'AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID',
                 'AZURE_CLIENT_ID', 'COUNTERPRESS_MODEL_API_KEY', 'COUNTERPRESS_ASSISTANT_MODEL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setitem(sys.modules, 'uvicorn', SimpleNamespace(run=lambda *a, **kw: calls.append((a, kw))))
    monkeypatch.setattr(sys, 'argv', ['run_footie_local.py', '--azure', '--port', '8020'])
    return calls


def test_injected_alias_launches_without_dotenv_and_prints_no_values(isolated_launch, monkeypatch, capsys):
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT', 'https://fixture.openai.azure.com')
    monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT', 'fixture-model')
    monkeypatch.setenv('COUNTERPRESS_MODEL_API_KEY', 'test-only-not-a-real-key')
    launch.main()
    assert len(isolated_launch) == 1
    assert isolated_launch[0][1]['port'] == 8020
    assert launch.os.environ['AZURE_OPENAI_API_KEY'] == 'test-only-not-a-real-key'
    assert not Path('.env').exists()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''


def test_explicit_environment_wins_over_alias_and_dotenv(isolated_launch, monkeypatch):
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT', 'https://fixture.openai.azure.com')
    monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT', 'injected-model')
    monkeypatch.setenv('AZURE_OPENAI_API_KEY', 'explicit-test-value')
    monkeypatch.setenv('COUNTERPRESS_MODEL_API_KEY', 'alias-test-value')
    Path('.env').write_text('AZURE_OPENAI_API_KEY="file-test-value"\nAZURE_OPENAI_DEPLOYMENT="file-model"\n')
    launch.main()
    assert launch.os.environ['AZURE_OPENAI_API_KEY'] == 'explicit-test-value'
    assert launch.os.environ['AZURE_OPENAI_DEPLOYMENT'] == 'injected-model'
    assert len(isolated_launch) == 1


def test_existing_dotenv_setup_still_works_and_ignores_unrelated_settings(isolated_launch):
    Path('.env').write_text('export AZURE_OPENAI_ENDPOINT="https://fixture.openai.azure.com"\nAZURE_OPENAI_DEPLOYMENT="file-model"\nAZURE_OPENAI_API_KEY="file-test-value"\nUNRELATED_SETTING="not-loaded"\n')
    launch.main()
    assert len(isolated_launch) == 1
    assert 'UNRELATED_SETTING' not in launch.os.environ


def test_missing_configuration_stops_before_startup_with_sanitized_message(isolated_launch, capsys):
    with pytest.raises(SystemExit, match='Local Azure configuration is missing'):
        launch.main()
    assert isolated_launch == []
    assert capsys.readouterr().out == ''


def test_invalid_local_quotes_do_not_expose_file_values(isolated_launch, capsys):
    Path('.env').write_text('AZURE_OPENAI_API_KEY="test-sensitive-canary\n')
    with pytest.raises(SystemExit) as exc:
        launch.main()
    assert str(exc.value) == 'Invalid quoting in local model settings.'
    assert 'canary' not in str(exc.value)
    assert isolated_launch == []
    assert 'canary' not in capsys.readouterr().out


def test_injected_managed_identity_configuration_needs_no_key_or_dotenv(isolated_launch, monkeypatch):
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT', 'https://fixture.openai.azure.com')
    monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT', 'fixture-model')
    monkeypatch.setenv('AZURE_OPENAI_AUTH_MODE', 'managed_identity')
    launch.main()
    assert len(isolated_launch) == 1
    assert 'AZURE_OPENAI_API_KEY' not in launch.os.environ
