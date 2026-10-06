"""
Login/register throttling and per-account lockout (T-009 batch 1, finding 3).
"""

from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle

from finance_app.models import LoginFailure

LOGIN_URL = '/api/v1/auth/login/'
REGISTER_URL = '/api/v1/auth/register/'


def bad_login(client, email='victim@example.com', **extra):
    return client.post(LOGIN_URL, {'email': email, 'password': 'WrongPassword123!'}, **extra)


class TestConfiguration:
    def test_num_proxies_defaults_to_one(self):
        assert settings.REST_FRAMEWORK['NUM_PROXIES'] == 1

    def test_login_and_register_scopes_have_rates(self):
        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        assert rates['login'] and rates['register']
        # DRF only reads the first character of the period, so '15m' would crash
        for rate in rates.values():
            num, period = rate.split('/')
            assert num.isdigit() and period[0] in 'smhd' and not period[0].isdigit()


class TestScopedThrottle:
    def test_login_throttled_per_client_address(self, api_client, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'login', '3/hour')
        codes = [
            bad_login(api_client, email=f'nobody{i}@example.com').status_code
            for i in range(5)
        ]
        assert codes[:3] == [401, 401, 401]
        assert codes[3:] == [429, 429]

    def test_register_throttled(self, api_client, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'register', '2/hour')
        codes = [api_client.post(REGISTER_URL, {}).status_code for _ in range(4)]
        assert codes[2:] == [429, 429]

    def test_spoofed_forwarded_for_does_not_bypass(self, api_client, monkeypatch):
        """Client-supplied left-hand X-Forwarded-For entries must not change the throttle key."""
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'login', '3/hour')
        codes = []
        for i in range(5):
            # Last entry is what the (single) trusted proxy appended; the rest is attacker noise
            response = bad_login(
                api_client, email=f'nobody{i}@example.com',
                HTTP_X_FORWARDED_FOR=f'10.9.8.{i}, 203.0.113.7',
            )
            codes.append(response.status_code)
        assert codes[3:] == [429, 429]

    def test_different_proxy_appended_address_is_a_different_client(self, api_client, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'login', '2/hour')
        for _ in range(3):
            bad_login(api_client, email='a@example.com', HTTP_X_FORWARDED_FOR='203.0.113.7')
        other = bad_login(api_client, email='b@example.com', HTTP_X_FORWARDED_FOR='203.0.113.8')
        assert other.status_code == status.HTTP_401_UNAUTHORIZED


class TestAccountLockout:
    def test_locks_after_repeated_failures_even_with_correct_password(self, api_client, user):
        for _ in range(settings.LOGIN_LOCKOUT_ATTEMPTS):
            assert api_client.post(
                LOGIN_URL, {'email': user.email, 'password': 'WrongPassword123!'}
            ).status_code == 401
        correct = api_client.post(LOGIN_URL, {'email': user.email, 'password': 'TestPassword123!'})
        assert correct.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_other_accounts_unaffected(self, api_client, user, user2):
        for _ in range(settings.LOGIN_LOCKOUT_ATTEMPTS):
            api_client.post(LOGIN_URL, {'email': user.email, 'password': 'WrongPassword123!'})
        ok = api_client.post(LOGIN_URL, {'email': user2.email, 'password': 'TestPassword123!'})
        assert ok.status_code == status.HTTP_200_OK

    def test_fewer_failures_do_not_lock(self, api_client, user):
        for _ in range(settings.LOGIN_LOCKOUT_ATTEMPTS - 1):
            api_client.post(LOGIN_URL, {'email': user.email, 'password': 'WrongPassword123!'})
        ok = api_client.post(LOGIN_URL, {'email': user.email, 'password': 'TestPassword123!'})
        assert ok.status_code == status.HTTP_200_OK

    def test_success_clears_failures(self, api_client, user):
        for _ in range(settings.LOGIN_LOCKOUT_ATTEMPTS - 1):
            api_client.post(LOGIN_URL, {'email': user.email, 'password': 'WrongPassword123!'})
        api_client.post(LOGIN_URL, {'email': user.email, 'password': 'TestPassword123!'})
        assert not LoginFailure.objects.filter(email=user.email).exists()

    def test_lockout_expires(self, api_client, user):
        for _ in range(settings.LOGIN_LOCKOUT_ATTEMPTS):
            api_client.post(LOGIN_URL, {'email': user.email, 'password': 'WrongPassword123!'})
        LoginFailure.objects.update(
            created_at=timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES + 1)
        )
        ok = api_client.post(LOGIN_URL, {'email': user.email, 'password': 'TestPassword123!'})
        assert ok.status_code == status.HTTP_200_OK

    def test_email_case_does_not_bypass(self, api_client, user):
        for _ in range(settings.LOGIN_LOCKOUT_ATTEMPTS):
            api_client.post(LOGIN_URL, {'email': user.email.upper(), 'password': 'WrongPassword123!'})
        ok = api_client.post(LOGIN_URL, {'email': user.email, 'password': 'TestPassword123!'})
        assert ok.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_unknown_and_known_email_behave_the_same(self, api_client, user):
        """Lockout must not reveal whether an account exists."""
        for email in (user.email, 'ghost@example.com'):
            codes = [
                api_client.post(LOGIN_URL, {'email': email, 'password': 'WrongPassword123!'}).status_code
                for _ in range(settings.LOGIN_LOCKOUT_ATTEMPTS + 1)
            ]
            assert codes == [401] * settings.LOGIN_LOCKOUT_ATTEMPTS + [429]
