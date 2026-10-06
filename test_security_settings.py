"""
Settings safety tests (T-009 batch 1, findings 1 and 6).

Each case imports settings.py in a fresh interpreter with a controlled
environment, because settings are evaluated once at import time.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent

FAKE_SECRETS = {
    'SECRET_KEY': 'unit-test-secret-key-not-real-aaaaaaaaaaaa',
    'JWT_SECRET': 'unit-test-jwt-secret-not-real-bbbbbbbbbbbb',
    'ENCRYPTION_KEY': 'unit-test-encryption-key-not-real-cccccc',
}
CONTROLLED = list(FAKE_SECRETS) + [
    'DEBUG', 'SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE',
    'NUM_PROXIES', 'DATABASE_URL', 'DJANGO_SETTINGS_MODULE',
]


def run_settings(extra_env=None, drop=(), code='import settings'):
    env = {k: v for k, v in os.environ.items() if k not in CONTROLLED}
    env.update(FAKE_SECRETS)
    for name in drop:
        env.pop(name, None)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, '-c', code], cwd=REPO, env=env,
        capture_output=True, text=True, timeout=60,
    )


class TestSecretsRequired:
    def test_boots_with_all_secrets(self):
        assert run_settings().returncode == 0

    @pytest.mark.parametrize('missing', ['SECRET_KEY', 'JWT_SECRET', 'ENCRYPTION_KEY'])
    def test_refuses_to_start_without_secret(self, missing):
        result = run_settings(drop=[missing])
        assert result.returncode != 0
        assert missing in result.stderr

    def test_jwt_secret_does_not_fall_back_to_secret_key(self):
        result = run_settings(drop=['JWT_SECRET'])
        assert result.returncode != 0

    def test_empty_secret_rejected(self):
        assert run_settings(extra_env={'ENCRYPTION_KEY': '   '}).returncode != 0

    def test_short_encryption_key_rejected(self):
        assert run_settings(extra_env={'ENCRYPTION_KEY': 'short'}).returncode != 0

    def test_no_insecure_default_strings_in_source(self):
        source = (REPO / 'settings.py').read_text()
        assert 'dev-key-change-in-production' not in source
        assert 'dev-encryption-key-change-in-production' not in source
