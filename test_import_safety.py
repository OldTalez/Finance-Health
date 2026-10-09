"""Security batch 2b: import money bugs, failed-import cleanup, regex rule validation, upload checks."""

from decimal import Decimal
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from finance_app.models import Category, ImportLog, Rule, Statement, Transaction
from finance_app.parsers import CSVParser

UPLOAD = '/api/v1/import/upload/'
KOHO_HEADER = 'date,description,credit,debit\n'


def _csv(body, name='s.csv'):
    return SimpleUploadedFile(name, (KOHO_HEADER + body).encode(), content_type='text/csv')


def _upload(client, f, **extra):
    data = {'file': f, 'bank_key': 'KOHO'}
    data.update(extra)
    return client.post(UPLOAD, data, format='multipart')


@pytest.mark.django_db
class TestImportMoney:
    def test_identical_rows_on_one_statement_are_both_kept(self, authenticated_client, user):
        body = '2026-01-05,COFFEE,,4.50\n2026-01-05,COFFEE,,4.50\n'
        r = _upload(authenticated_client, _csv(body))
        assert r.status_code == 200, r.data
        assert r.data['rows_imported'] == 2
        assert Transaction.objects.filter(user=user).count() == 2

    def test_unreadable_row_refuses_the_whole_file(self, authenticated_client, user):
        body = '2026-01-05,COFFEE,,4.50\n2026-01-06,RENT,,not-a-number\n'
        r = _upload(authenticated_client, _csv(body))
        assert r.status_code == 400
        assert 'line' in r.data['error'].lower()
        assert Transaction.objects.filter(user=user).count() == 0
        assert Statement.objects.filter(user=user).count() == 0

    def test_bad_date_is_an_error_not_today(self):
        with pytest.raises(ValueError):
            CSVParser._parse_csv_date('31-31-2026', 'ISO')

    def test_csv_parser_names_the_bad_lines(self):
        text = KOHO_HEADER + '2026-01-05,A,,1.00\nbroken\n2026-01-06,B,,x\n'
        with pytest.raises(ValueError) as e:
            CSVParser.parse_csv(text, 'KOHO')
        assert '3' in str(e.value) and '4' in str(e.value)


@pytest.mark.django_db
class TestFailedImportLeavesNothing:
    def test_crash_mid_import_can_be_retried(self, authenticated_client, user):
        body = '2026-01-05,COFFEE,,4.50\n2026-01-06,TEA,,3.00\n'
        real_create = Transaction.objects.create
        calls = {'n': 0}

        def flaky(*a, **kw):
            calls['n'] += 1
            if calls['n'] == 2:
                raise RuntimeError('boom')
            return real_create(*a, **kw)

        with mock.patch.object(Transaction.objects, 'create', side_effect=flaky):
            r = _upload(authenticated_client, _csv(body))
        assert r.status_code == 500
        assert Statement.objects.filter(user=user).count() == 0
        assert Transaction.objects.filter(user=user).count() == 0
        assert ImportLog.objects.filter(user=user, import_status='failed').count() == 1
        assert not ImportLog.objects.filter(user=user, import_status='processing').exists()

        retry = _upload(authenticated_client, _csv(body))
        assert retry.status_code == 200
        assert retry.data['rows_imported'] == 2


@pytest.mark.django_db
class TestUploadChecks:
    def test_pdf_extension_with_csv_content_is_refused(self, authenticated_client):
        f = SimpleUploadedFile('s.pdf', b'date,desc\n', content_type='application/pdf')
        assert _upload(authenticated_client, f).status_code == 400

    def test_csv_that_is_not_utf8_is_a_400_not_a_500(self, authenticated_client):
        f = SimpleUploadedFile('s.csv', b'\xff\xfe\x00bad', content_type='text/csv')
        assert _upload(authenticated_client, f).status_code == 400

    def test_unknown_bank_key_is_refused(self, authenticated_client):
        r = _upload(authenticated_client, _csv('2026-01-05,A,,1.00\n'), bank_key='NOPE')
        assert r.status_code == 400

    def test_non_numeric_account_id_is_a_400(self, authenticated_client):
        r = _upload(authenticated_client, _csv('2026-01-05,A,,1.00\n'), account_id='abc')
        assert r.status_code == 400

    def test_path_in_filename_is_dropped(self, authenticated_client, user):
        f = SimpleUploadedFile('../../etc/s.csv', (KOHO_HEADER + '2026-01-05,A,,1.00\n').encode())
        r = _upload(authenticated_client, f)
        assert r.status_code == 200
        assert r.data['file_name'] == 's.csv'


@pytest.mark.django_db
class TestRuleValidation:
    def _post(self, client, category, **kw):
        body = {'category_id': category.id, 'pattern': 'x', 'pattern_type': 'regex'}
        body.update(kw)
        return client.post('/api/v1/rules/', body, format='json')

    @pytest.fixture
    def category(self, user):
        return Category.objects.create(user=user, name='Food')

    def test_valid_regex_accepted(self, authenticated_client, category):
        assert self._post(authenticated_client, category, pattern=r'^TIM HORTONS\s+\d+').status_code == 201

    def test_invalid_regex_rejected(self, authenticated_client, category):
        assert self._post(authenticated_client, category, pattern='(unclosed').status_code == 400

    def test_nested_repeat_rejected(self, authenticated_client, category):
        assert self._post(authenticated_client, category, pattern='(a+)+$').status_code == 400

    def test_long_regex_rejected(self, authenticated_client, category):
        assert self._post(authenticated_client, category, pattern='a' * 201).status_code == 400

    def test_empty_pattern_rejected(self, authenticated_client, category):
        assert self._post(authenticated_client, category, pattern='  ').status_code == 400

    def test_contains_rule_can_use_regex_characters(self, authenticated_client, category):
        r = self._post(authenticated_client, category, pattern='(a+)+', pattern_type='contains')
        assert r.status_code == 201

    def test_partial_update_checks_the_stored_type(self, authenticated_client, category, user):
        rule = Rule.objects.create(user=user, category=category, pattern='ok', pattern_type='regex')
        r = authenticated_client.patch(f'/api/v1/rules/{rule.id}/', {'pattern': '(a+)+'}, format='json')
        assert r.status_code == 400
