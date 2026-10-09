"""railway.toml shape checks (T-009 batch 1, item 7). Cannot prove Railway behaviour, only the file."""

import tomllib
from pathlib import Path

CONFIG = tomllib.loads((Path(__file__).resolve().parent / 'railway.toml').read_text(encoding='utf-8'))


def test_start_command_only_starts_the_server():
    start = CONFIG['deploy']['startCommand']
    assert start.startswith('gunicorn')
    assert 'migrate' not in start and 'collectstatic' not in start


def test_collectstatic_in_build_and_migrate_in_predeploy():
    assert 'collectstatic' in CONFIG['build']['buildCommand']
    assert any('migrate' in c for c in CONFIG['deploy']['preDeployCommand'])


def test_collectstatic_does_not_clear_on_start():
    assert '--clear' not in CONFIG['build']['buildCommand']
