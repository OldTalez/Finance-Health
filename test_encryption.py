"""
AES-256-GCM field encryption tests (T-009 batch 1, finding 5).

Only obviously fake values are used.
"""

import pytest
from django.db import connection
from django.test import override_settings

from finance_app.models import Account
from finance_app.utils import EncryptionUtils

FAKE_NUMBER = '0000-FAKE-1234'
FAKE_NAME = 'Fake Holder Name'


class TestEncryptionUtils:
    def test_round_trip(self):
        token = EncryptionUtils.encrypt(FAKE_NUMBER)
        assert EncryptionUtils.decrypt(token) == FAKE_NUMBER

    def test_round_trip_unicode_and_long(self):
        value = 'Zoë ' * 200
        assert EncryptionUtils.decrypt(EncryptionUtils.encrypt(value)) == value

    def test_ciphertext_is_not_plaintext(self):
        token = EncryptionUtils.encrypt(FAKE_NUMBER)
        assert token != FAKE_NUMBER
        assert FAKE_NUMBER not in token
        assert token.startswith('v1:')

    def test_random_nonce_gives_different_ciphertext_each_time(self):
        tokens = {EncryptionUtils.encrypt(FAKE_NUMBER) for _ in range(20)}
        assert len(tokens) == 20

    def test_empty_stays_empty(self):
        assert EncryptionUtils.encrypt('') == ''
        assert EncryptionUtils.decrypt('') == ''

    def test_tampered_ciphertext_fails(self):
        token = EncryptionUtils.encrypt(FAKE_NUMBER)
        body = token[3:]
        # flip one character in the middle of the payload
        i = len(body) // 2
        flipped = body[:i] + ('A' if body[i] != 'A' else 'B') + body[i + 1:]
        with pytest.raises(ValueError):
            EncryptionUtils.decrypt('v1:' + flipped)

    def test_truncated_ciphertext_fails(self):
        token = EncryptionUtils.encrypt(FAKE_NUMBER)
        with pytest.raises(ValueError):
            EncryptionUtils.decrypt(token[:-6])

    def test_unprefixed_input_is_never_returned_as_plaintext(self):
        with pytest.raises(ValueError):
            EncryptionUtils.decrypt(FAKE_NUMBER)

    def test_wrong_key_fails(self):
        token = EncryptionUtils.encrypt(FAKE_NUMBER)
        with override_settings(ENCRYPTION_KEY='a-completely-different-fake-key-0000000'):
            with pytest.raises(ValueError):
                EncryptionUtils.decrypt(token)

    def test_context_is_bound(self):
        token = EncryptionUtils.encrypt(FAKE_NUMBER, context='accounts.account_number')
        assert EncryptionUtils.decrypt(token, context='accounts.account_number') == FAKE_NUMBER
        with pytest.raises(ValueError):
            EncryptionUtils.decrypt(token, context='accounts.account_holder_name')
        with pytest.raises(ValueError):
            EncryptionUtils.decrypt(token)


@pytest.mark.django_db
class TestAccountFields:
    def make_account(self, user):
        account = Account(user=user, name='Fake Account', bank_key='TD-Chequing', account_type='debit')
        account.set_account_number(FAKE_NUMBER)
        account.set_account_holder_name(FAKE_NAME)
        account.save()
        return account

    def test_stored_database_value_is_not_plaintext(self, user):
        account = self.make_account(user)
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT account_number_encrypted, account_holder_name_encrypted FROM accounts WHERE id = %s',
                [account.id],
            )
            raw_number, raw_name = cursor.fetchone()
        assert raw_number.startswith('v1:') and FAKE_NUMBER not in raw_number
        assert raw_name.startswith('v1:') and FAKE_NAME not in raw_name

    def test_round_trip_through_database(self, user):
        account = self.make_account(user)
        fresh = Account.objects.get(pk=account.pk)
        assert fresh.get_account_number() == FAKE_NUMBER
        assert fresh.get_account_holder_name() == FAKE_NAME

    def test_swapping_values_between_fields_is_detected(self, user):
        account = self.make_account(user)
        account.account_number_encrypted = account.account_holder_name_encrypted
        with pytest.raises(ValueError):
            account.get_account_number()

    def test_api_never_exposes_encrypted_columns(self, authenticated_client, user):
        self.make_account(user)
        response = authenticated_client.get('/api/v1/accounts/')
        body = str(response.data)
        assert 'encrypted' not in body and FAKE_NUMBER not in body and 'v1:' not in body
