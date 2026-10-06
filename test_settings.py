"""
Test settings for Finance Platform API
Override production settings for testing with SQLite
"""

import os

# Obviously fake values, for tests only. assigned (not setdefault) so a developer's real environment is never used by tests.
os.environ['SECRET_KEY'] = 'test-only-secret-key-not-for-real-use-0001'
os.environ['JWT_SECRET'] = 'test-only-jwt-secret-not-for-real-use-0002'
os.environ['ENCRYPTION_KEY'] = 'test-only-encryption-key-not-real-0003'

from settings import *  # noqa: E402,F401,F403

# Use SQLite for tests (no external database needed)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # In-memory database for fast tests
    }
}

# Disable migrations for tests (use syncdb instead)
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()

# Disable password validation for faster test user creation
AUTH_PASSWORD_VALIDATORS = []

# Use simple password hasher for tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable CSRF for API tests
CSRF_TRUSTED_ORIGINS = ['*']

# Test-specific settings (the test client speaks plain HTTP)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
DEBUG = True
ALLOWED_HOSTS = ['*']
