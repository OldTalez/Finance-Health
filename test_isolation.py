"""
Cross-user isolation tests (T-009 batch 1, finding 4).

User A owns the data; user B is authenticated and tries to reach it.
"""

import pytest
from rest_framework import status

from finance_app.models import Category, Rule, Account, Transaction
from finance_app.utils import JWTUtils

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_b(api_client, user2):
    access, _, _ = JWTUtils.generate_tokens(user2)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    return api_client


@pytest.fixture
def b_category(user2):
    return Category.objects.create(user=user2, name='B Groceries')


class TestRuleCategoryScoping:
    def test_create_rule_with_foreign_category_rejected(self, client_b, subscriptions_category, user2):
        response = client_b.post('/api/v1/rules/', {
            'category_id': subscriptions_category.id,  # belongs to user A
            'pattern': 'anything', 'pattern_type': 'contains',
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'category_id' in response.data
        assert not Rule.objects.filter(user=user2).exists()

    def test_create_rule_with_unknown_category_rejected(self, client_b):
        response = client_b.post('/api/v1/rules/', {
            'category_id': 999999, 'pattern': 'x', 'pattern_type': 'contains',
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_foreign_and_unknown_give_same_error(self, client_b, subscriptions_category):
        foreign = client_b.post('/api/v1/rules/', {
            'category_id': subscriptions_category.id, 'pattern': 'x', 'pattern_type': 'contains'})
        unknown = client_b.post('/api/v1/rules/', {
            'category_id': 999999, 'pattern': 'x', 'pattern_type': 'contains'})
        assert foreign.data == unknown.data

    def test_create_rule_with_own_category_ok(self, client_b, b_category, user2):
        response = client_b.post('/api/v1/rules/', {
            'category_id': b_category.id, 'pattern': 'milk', 'pattern_type': 'contains',
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert Rule.objects.get(user=user2).category_id == b_category.id

    def test_patch_own_rule_to_foreign_category_rejected(self, client_b, user2, b_category, subscriptions_category):
        rule = Rule.objects.create(user=user2, category=b_category, pattern='milk', pattern_type='contains')
        response = client_b.patch(f'/api/v1/rules/{rule.id}/', {'category_id': subscriptions_category.id})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        rule.refresh_from_db()
        assert rule.category_id == b_category.id

    def test_patch_own_rule_to_own_other_category_ok(self, client_b, user2, b_category):
        other = Category.objects.create(user=user2, name='B Other')
        rule = Rule.objects.create(user=user2, category=b_category, pattern='milk', pattern_type='contains')
        response = client_b.patch(f'/api/v1/rules/{rule.id}/', {'category_id': other.id})
        assert response.status_code == status.HTTP_200_OK
        rule.refresh_from_db()
        assert rule.category_id == other.id

    def test_patch_other_fields_without_category_still_works(self, client_b, user2, b_category):
        rule = Rule.objects.create(user=user2, category=b_category, pattern='milk', pattern_type='contains')
        response = client_b.patch(f'/api/v1/rules/{rule.id}/', {'priority': 5})
        assert response.status_code == status.HTTP_200_OK

    def test_put_with_foreign_category_rejected(self, client_b, user2, b_category, subscriptions_category):
        rule = Rule.objects.create(user=user2, category=b_category, pattern='milk', pattern_type='contains')
        response = client_b.put(f'/api/v1/rules/{rule.id}/', {
            'category_id': subscriptions_category.id, 'pattern': 'milk', 'pattern_type': 'contains'})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_foreign_category_name_never_appears_in_b_rules(self, client_b, user2, subscriptions_category):
        response = client_b.get('/api/v1/rules/')
        assert subscriptions_category.name not in str(response.data)


class TestObjectsOfAnotherUser:
    """B cannot read, update or delete A's objects by id: every endpoint returns 404."""

    @pytest.fixture
    def targets(self, account, subscriptions_category, netflix_rule, transactions):
        return {
            'accounts': account.id,
            'categories': subscriptions_category.id,
            'rules': netflix_rule.id,
            'transactions': transactions[0].id,
        }

    @pytest.mark.parametrize('resource', ['accounts', 'categories', 'rules', 'transactions'])
    def test_read_update_delete_all_404(self, client_b, targets, resource):
        url = f'/api/v1/{resource}/{targets[resource]}/'
        assert client_b.get(url).status_code == status.HTTP_404_NOT_FOUND
        assert client_b.patch(url, {'notes': 'x', 'name': 'x', 'priority': 1}).status_code == status.HTTP_404_NOT_FOUND
        assert client_b.delete(url).status_code == status.HTTP_404_NOT_FOUND

    def test_objects_survive_attempted_delete(self, client_b, targets):
        for resource in ('accounts', 'categories', 'rules', 'transactions'):
            client_b.delete(f'/api/v1/{resource}/{targets[resource]}/')
        assert Account.objects.filter(id=targets['accounts']).exists()
        assert Category.objects.filter(id=targets['categories']).exists()
        assert Rule.objects.filter(id=targets['rules']).exists()
        assert Transaction.objects.filter(id=targets['transactions']).exists()

    @pytest.mark.parametrize('resource', ['accounts', 'categories', 'rules', 'transactions'])
    def test_lists_are_empty_for_b(self, client_b, targets, resource):
        response = client_b.get(f'/api/v1/{resource}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 0

    def test_export_contains_only_own_rows(self, client_b, transactions):
        response = client_b.get('/api/v1/transactions/export/')
        assert response.status_code == status.HTTP_200_OK
        assert b'NETFLIX' not in response.content

    def test_dashboard_has_no_a_data(self, client_b, transactions):
        response = client_b.get('/api/v1/analytics/dashboard/')
        assert response.status_code == status.HTTP_200_OK
        assert 'Subscriptions' not in str(response.data)
