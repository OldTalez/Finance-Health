"""railway.toml shape checks (T-009 batch 1, item 7). Cannot prove Railway behaviour, only the file."""

import tomllib
from pathlib import Path

CONFIG = tomllib.loads((Path(__file__).resolve().parent / 'railway.toml').read_text(encoding='utf-8'))


def test_start_command_migrates_then_starts_the_server():
    # Pre-deploy did not apply migrations on staging (2026-10-09), so migrate runs at start.
    start = CONFIG['deploy']['startCommand']
    assert start.index('migrate') < start.index('gunicorn')
    assert '&&' in start and 'collectstatic' not in start


def test_collectstatic_in_build_and_no_predeploy_step():
    assert 'collectstatic' in CONFIG['build']['buildCommand']
    assert 'preDeployCommand' not in CONFIG['deploy']


def test_collectstatic_does_not_clear_on_start():
    assert '--clear' not in CONFIG['build']['buildCommand']
