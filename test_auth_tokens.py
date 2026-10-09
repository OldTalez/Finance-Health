"""
Refresh-token lifecycle tests (T-009 batch 1, finding 2).
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from finance_app.models import RefreshToken
from finance_app.utils import JWTUtils

REFRESH_URL = '/api/v1/auth/refresh/'
LOGOUT_URL = '/api/v1/auth/logout/'
LOGIN_URL = '/api/v1/auth/login/'


def login(client, user):
    response = client.post(LOGIN_URL, {'email': user.email, 'password': 'TestPassword123!'})
    assert response.status_code == status.HTTP_200_OK
    return response.data['access_token'], response.data['refresh_token']


class TestRefreshTokenStorage:
    def test_only_hash_is_stored(self, api_client, user):
        _, refresh = login(api_client, user)
        record = RefreshToken.objects.get(user=user)
        assert record.token_hash == RefreshToken.hash_token(refresh)
        assert record.token_hash != refresh
        assert len(record.token_hash) == 64
        assert not hasattr(record, 'token')

    def test_no_raw_token_anywhere_in_row(self, api_client, user):
        _, refresh = login(api_client, user)
        values = RefreshToken.objects.filter(user=user).values()[0]
        assert all(refresh not in str(v) for v in values.values())

    def test_two_logins_same_second_give_distinct_tokens(self, user):
        _, r1, _ = JWTUtils.generate_tokens(user)
        _, r2, _ = JWTUtils.generate_tokens(user)
        assert r1 != r2
        assert RefreshToken.objects.filter(user=user).count() == 2


class TestRefreshRotation:
    def test_refresh_returns_new_pair_and_revokes_old(self, api_client, user):
        _, refresh = login(api_client, user)
        response = api_client.post(REFRESH_URL, {'refresh_token': refresh})
        assert response.status_code == status.HTTP_200_OK
        assert response.data['refresh_token'] != refresh
        old = RefreshToken.objects.get(token_hash=RefreshToken.hash_token(refresh))
        assert old.is_revoked is True

    def test_new_token_keeps_family(self, api_client, user):
        _, refresh = login(api_client, user)
        response = api_client.post(REFRESH_URL, {'refresh_token': refresh})
        old = RefreshToken.objects.get(token_hash=RefreshToken.hash_token(refresh))
        new = RefreshToken.objects.get(token_hash=RefreshToken.hash_token(response.data['refresh_token']))
        assert old.family_id == new.family_id

    def test_reuse_of_rotated_token_rejected_and_family_revoked(self, api_client, user):
        _, refresh = login(api_client, user)
        first = api_client.post(REFRESH_URL, {'refresh_token': refresh})
        assert first.status_code == status.HTTP_200_OK
        newest = first.data['refresh_token']

        # Attacker replays the old token
        replay = api_client.post(REFRESH_URL, {'refresh_token': refresh})
        assert replay.status_code == status.HTTP_401_UNAUTHORIZED

        # The legitimate newest token is now dead too (whole family revoked)
        after = api_client.post(REFRESH_URL, {'refresh_token': newest})
        assert after.status_code == status.HTTP_401_UNAUTHORIZED
        assert not RefreshToken.objects.filter(user=user, is_revoked=False).exists()

    def test_reuse_does_not_touch_other_families(self, api_client, user):
        _, refresh_a = login(api_client, user)
        _, refresh_b = login(api_client, user)
        api_client.post(REFRESH_URL, {'refresh_token': refresh_a})
        api_client.post(REFRESH_URL, {'refresh_token': refresh_a})  # replay kills family A only
        still_ok = api_client.post(REFRESH_URL, {'refresh_token': refresh_b})
        assert still_ok.status_code == status.HTTP_200_OK

    def test_revoked_token_rejected(self, api_client, user):
        _, refresh = login(api_client, user)
        RefreshToken.objects.filter(user=user).update(is_revoked=True)
        response = api_client.post(REFRESH_URL, {'refresh_token': refresh})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_expired_record_rejected(self, api_client, user):
        _, refresh = login(api_client, user)
        RefreshToken.objects.filter(user=user).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = api_client.post(REFRESH_URL, {'refresh_token': refresh})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_valid_signature_but_unknown_token_rejected(self, api_client, user):
        _, refresh = login(api_client, user)
        RefreshToken.objects.all().delete()  # signature valid, no DB record
        response = api_client.post(REFRESH_URL, {'refresh_token': refresh})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_access_token_cannot_be_used_as_refresh(self, api_client, user):
        access, _ = login(api_client, user)
        response = api_client.post(REFRESH_URL, {'refresh_token': access})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_garbage_and_non_string_rejected(self, api_client):
        assert api_client.post(REFRESH_URL, {'refresh_token': 'not-a-jwt'}).status_code == 401
        assert api_client.post(REFRESH_URL, {'refresh_token': ['x']}, format='json').status_code == 401
        assert api_client.post(REFRESH_URL, {}).status_code == 400


class TestInactiveUser:
    def test_deactivated_user_cannot_refresh(self, api_client, user):
        _, refresh = login(api_client, user)
        user.is_active = False
        user.save()
        response = api_client.post(REFRESH_URL, {'refresh_token': refresh})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_deactivated_user_access_token_rejected(self, api_client, user):
        access, _ = login(api_client, user)
        user.is_active = False
        user.save()
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        response = api_client.get('/api/v1/auth/me/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_active_user_access_token_accepted(self, api_client, user):
        access, _ = login(api_client, user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        assert api_client.get('/api/v1/auth/me/').status_code == status.HTTP_200_OK


class TestLogout:
    def test_logout_revokes_token(self, api_client, user):
        _, refresh = login(api_client, user)
        response = api_client.post(LOGOUT_URL, {'refresh_token': refresh})
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not RefreshToken.objects.filter(user=user, is_revoked=False).exists()
        after = api_client.post(REFRESH_URL, {'refresh_token': refresh})
        assert after.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_revokes_rotated_family(self, api_client, user):
        _, refresh = login(api_client, user)
        rotated = api_client.post(REFRESH_URL, {'refresh_token': refresh}).data['refresh_token']
        api_client.post(LOGOUT_URL, {'refresh_token': rotated})
        assert api_client.post(REFRESH_URL, {'refresh_token': rotated}).status_code == 401

    def test_logout_unknown_token_does_not_reveal(self, api_client, user):
        _, refresh = login(api_client, user)
        RefreshToken.objects.all().delete()
        response = api_client.post(LOGOUT_URL, {'refresh_token': refresh})
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_logout_requires_token(self, api_client):
        assert api_client.post(LOGOUT_URL, {}).status_code == status.HTTP_400_BAD_REQUEST
