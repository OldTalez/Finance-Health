"""
Invite-only registration (T-009 batch 1, item 3b, Board ruling "invite only").
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.contrib.messages import get_messages
from django.utils import timezone
from rest_framework import status

from finance_app.models import InviteCode

User = get_user_model()
pytestmark = pytest.mark.django_db
REGISTER_URL = '/api/v1/auth/register/'


def payload(code=None, email='newmember@example.com'):
    data = {
        'email': email,
        'password': 'SecurePass123!',
        'password_confirm': 'SecurePass123!',
        'full_name': 'New Member',
    }
    if code is not None:
        data['invite_code'] = code
    return data


class TestRegisterNeedsInvite:
    def test_register_without_code_fails(self, api_client):
        response = api_client.post(REGISTER_URL, payload())
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not User.objects.filter(email='newmember@example.com').exists()

    def test_register_with_unknown_code_fails(self, api_client):
        response = api_client.post(REGISTER_URL, payload('not-a-real-code'))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not User.objects.filter(email='newmember@example.com').exists()

    def test_valid_code_succeeds_once(self, api_client, invite_code):
        first = api_client.post(REGISTER_URL, payload(invite_code))
        assert first.status_code == status.HTTP_201_CREATED
        user = User.objects.get(email='newmember@example.com')
        invite = InviteCode.objects.get()
        assert invite.used_at is not None
        assert invite.used_by_id == user.id

    def test_reused_code_fails(self, api_client, invite_code):
        assert api_client.post(REGISTER_URL, payload(invite_code)).status_code == 201
        second = api_client.post(REGISTER_URL, payload(invite_code, email='second@example.com'))
        assert second.status_code == status.HTTP_400_BAD_REQUEST
        assert not User.objects.filter(email='second@example.com').exists()

    def test_expired_code_fails(self, api_client):
        invite, code = InviteCode.issue(label='old', days=1)
        InviteCode.objects.filter(pk=invite.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        response = api_client.post(REGISTER_URL, payload(code))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unexpired_code_with_expiry_succeeds(self, api_client):
        _, code = InviteCode.issue(label='soon', days=1)
        assert api_client.post(REGISTER_URL, payload(code)).status_code == 201

    def test_missing_used_and_expired_give_identical_response(self, api_client, invite_code):
        api_client.post(REGISTER_URL, payload(invite_code))  # use it up
        _, expired = InviteCode.issue(days=1)
        InviteCode.objects.filter(code_hash=InviteCode.hash_code(expired)).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        bodies = [
            api_client.post(REGISTER_URL, payload(code, email=f'x{i}@example.com')).data
            for i, code in enumerate([None, 'bogus', invite_code, expired])
        ]
        assert all(body == bodies[0] for body in bodies)

    def test_non_string_code_is_rejected_not_500(self, api_client):
        response = api_client.post(REGISTER_URL, {**payload(), 'invite_code': ['a']}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bad_password_does_not_burn_the_invite(self, api_client, invite_code):
        bad = {**payload(invite_code), 'password': 'weak', 'password_confirm': 'weak'}
        assert api_client.post(REGISTER_URL, bad).status_code == 400
        assert api_client.post(REGISTER_URL, payload(invite_code)).status_code == 201

    def test_duplicate_email_message_is_generic_and_keeps_invite(self, api_client, user, invite_code):
        response = api_client.post(REGISTER_URL, payload(invite_code, email=user.email))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already registered' not in str(response.data).lower()
        assert InviteCode.objects.get().used_at is None


class TestInviteStorage:
    def test_only_hash_stored(self):
        invite, code = InviteCode.issue(label='check')
        assert code not in invite.code_hash
        assert invite.code_hash == InviteCode.hash_code(code)
        assert all(code not in str(v) for v in InviteCode.objects.values()[0].values())

    def test_claim_is_single_use(self):
        _, code = InviteCode.issue()
        assert InviteCode.claim(code) is not None
        assert InviteCode.claim(code) is None


class TestIssuing:
    def test_management_command_prints_working_code(self, api_client):
        out = StringIO()
        call_command('create_invite', '--label', 'first admin step', '--days', '3', stdout=out)
        printed = out.getvalue()
        code = printed.split('(shown once): ')[1].splitlines()[0].strip()
        assert api_client.post(REGISTER_URL, payload(code)).status_code == 201

    def test_admin_add_creates_invite_and_shows_code_once(self, client, db):
        admin_user = User.objects.create_superuser(
            email='boss@example.com', password='AdminPass123!xyz'
        )
        client.force_login(admin_user)
        response = client.post('/admin/finance_app/invitecode/add/', {'label': 'Family member'})
        assert response.status_code == 302
        invite = InviteCode.objects.get()
        assert invite.label == 'Family member'
        shown = [m.message for m in get_messages(response.wsgi_request)]
        code_messages = [m for m in shown if 'shown only once' in m]
        assert len(code_messages) == 1
        code = code_messages[0].split(': ')[-1]
        assert InviteCode.hash_code(code) == invite.code_hash
