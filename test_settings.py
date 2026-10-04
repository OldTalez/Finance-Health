"""
Test settings for Finance Platform API
Override production settings for testing with SQLite
"""

from settings import *

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

# Test-specific settings
DEBUG = True
ALLOWED_HOSTS = ['*']
