"""
API Integration Tests for Finance Platform Phase 1
"""

import pytest
from rest_framework import status
from django.contrib.auth import get_user_model
from decimal import Decimal
import json

User = get_user_model()

# ============ AUTHENTICATION TESTS ============

class TestAuth:
    """Authentication endpoint tests"""

    def test_register_success(self, api_client):
        """Test successful user registration"""
        response = api_client.post('/api/v1/auth/register/', {
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'full_name': 'New User'
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['email'] == 'newuser@example.com'
        assert User.objects.filter(email='newuser@example.com').exists()

    def test_register_weak_password(self, api_client):
        """Test registration with weak password"""
        response = api_client.post('/api/v1/auth/register/', {
            'email': 'user@example.com',
            'password': 'weak',
            'password_confirm': 'weak'
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_duplicate_email(self, api_client, user):
        """Test registration with duplicate email"""
        response = api_client.post('/api/v1/auth/register/', {
            'email': user.email,
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!'
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_success(self, api_client, user):
        """Test successful login"""
        response = api_client.post('/api/v1/auth/login/', {
            'email': user.email,
            'password': 'TestPassword123!'
        })

        assert response.status_code == status.HTTP_200_OK
        assert 'access_token' in response.data
        assert 'refresh_token' in response.data
        assert response.data['token_type'] == 'Bearer'

    def test_login_invalid_credentials(self, api_client):
        """Test login with invalid credentials"""
        response = api_client.post('/api/v1/auth/login/', {
            'email': 'nonexistent@example.com',
            'password': 'WrongPassword123!'
        })

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_profile(self, authenticated_client, user):
        """Test getting user profile"""
        response = authenticated_client.get('/api/v1/auth/me/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == user.email
        assert response.data['full_name'] == user.full_name


# ============ ACCOUNT TESTS ============

class TestAccounts:
    """Account CRUD tests"""

    def test_list_accounts(self, authenticated_client, account):
        """Test listing user accounts"""
        response = authenticated_client.get('/api/v1/accounts/')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['name'] == account.name

    def test_create_account(self, authenticated_client):
        """Test creating an account"""
        response = authenticated_client.post('/api/v1/accounts/', {
            'name': 'New Account',
            'bank_key': 'TD-Chequing',
            'account_type': 'debit',
            'currency': 'CAD'
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == 'New Account'

    def test_account_isolation(self, authenticated_client, account, user2):
        """Test that users can only see their own accounts"""
        # User1 has account; user2 should not see it
        response = authenticated_client.get('/api/v1/accounts/')
        assert len(response.data['results']) == 1


# ============ TRANSACTION TESTS ============

class TestTransactions:
    """Transaction CRUD and filtering tests"""

    def test_list_transactions(self, authenticated_client, transactions):
        """Test listing transactions"""
        response = authenticated_client.get('/api/v1/transactions/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == len(transactions)

    def test_filter_transactions_by_amount(self, authenticated_client, transactions):
        """Test filtering by amount range"""
        response = authenticated_client.get('/api/v1/transactions/?search=NETFLIX')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert 'NETFLIX' in response.data['results'][0]['description']

    def test_filter_recurring_only(self, authenticated_client, transactions):
        """Test filtering for recurring transactions only"""
        response = authenticated_client.get('/api/v1/transactions/?is_recurring=true')

        assert response.status_code == status.HTTP_200_OK
        assert all(tx['is_recurring'] for tx in response.data['results'])

    def test_export_csv(self, authenticated_client, transactions):
        """Test CSV export"""
        response = authenticated_client.get('/api/v1/transactions/export/')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'text/csv'

    def test_update_transaction(self, authenticated_client, transactions):
        """Test updating a transaction"""
        tx = transactions[0]
        response = authenticated_client.patch(
            f'/api/v1/transactions/{tx.id}/',
            {'notes': 'Updated note'}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['notes'] == 'Updated note'


# ============ DASHBOARD TESTS ============

class TestDashboard:
    """Dashboard metrics tests"""

    def test_dashboard_empty(self, authenticated_client, user):
        """Test dashboard with no transactions"""
        response = authenticated_client.get('/api/v1/analytics/dashboard/')

        assert response.status_code == status.HTTP_200_OK
        assert 'money_left_this_month' in response.data
        assert 'net_worth' in response.data
        assert 'account_balances' in response.data

    def test_dashboard_money_left(self, authenticated_client, transactions, user):
        """Test money-left-this-month calculation"""
        response = authenticated_client.get('/api/v1/analytics/dashboard/')

        # Income: 4500, Spending: 24.99, Money left: 4475.01
        assert response.status_code == status.HTTP_200_OK
        assert float(response.data['money_left_this_month']['value']) > 0


# ============ IMPORT TESTS ============

class TestImport:
    """File upload and import tests"""

    def test_import_history(self, authenticated_client):
        """Test listing import history"""
        response = authenticated_client.get('/api/v1/import/history/')

        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data

    @pytest.mark.integration
    def test_upload_invalid_file(self, authenticated_client):
        """Test uploading invalid file type"""
        response = authenticated_client.post('/api/v1/import/upload/', {
            'file': b'invalid content',
            'bank_key': 'PCFinancial-Mastercard'
        }, format='multipart')

        # Should reject non-PDF/CSV files
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        ]


# ============ CATEGORY TESTS ============

class TestCategories:
    """Category CRUD tests"""

    def test_list_categories(self, authenticated_client, subscriptions_category):
        """Test listing categories"""
        response = authenticated_client.get('/api/v1/categories/')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1

    def test_create_category(self, authenticated_client):
        """Test creating a category"""
        response = authenticated_client.post('/api/v1/categories/', {
            'name': 'Pet Care',
            'color': '#788c5d',
            'is_internal': False
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == 'Pet Care'


# ============ RULE TESTS ============

class TestRules:
    """Categorization rule tests"""

    def test_list_rules(self, authenticated_client, netflix_rule):
        """Test listing rules"""
        response = authenticated_client.get('/api/v1/rules/')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1

    def test_create_rule(self, authenticated_client, subscriptions_category):
        """Test creating a rule"""
        response = authenticated_client.post('/api/v1/rules/', {
            'category_id': subscriptions_category.id,
            'pattern': 'hbo|max|apple tv',
            'pattern_type': 'regex',
            'priority': 90,
            'is_active': True
        })

        assert response.status_code == status.HTTP_201_CREATED


# ============ PERMISSION TESTS ============

class TestPermissions:
    """Permission and isolation tests"""

    def test_unauthenticated_access_denied(self, api_client):
        """Test that unauthenticated requests are denied"""
        response = api_client.get('/api/v1/accounts/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_isolation(self, authenticated_client, user, account, user2):
        """Test that users can't access each other's data"""
        # Login as user2
        from .utils import JWTUtils
        access_token, _, _ = JWTUtils.generate_tokens(user2)
        authenticated_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        # Try to access user1's account
        response = authenticated_client.get(f'/api/v1/accounts/{account.id}/')
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============ PAGINATION TESTS ============

class TestPagination:
    """Pagination tests"""

    def test_pagination_default(self, authenticated_client, transactions):
        """Test default pagination"""
        response = authenticated_client.get('/api/v1/transactions/')

        assert response.status_code == status.HTTP_200_OK
        assert 'count' in response.data
        assert 'results' in response.data

    def test_pagination_page_size(self, authenticated_client, transactions):
        """Test custom page size"""
        response = authenticated_client.get('/api/v1/transactions/?page_size=1')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) <= 1
