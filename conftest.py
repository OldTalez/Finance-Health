"""
Pytest configuration and fixtures for Finance Platform tests
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient
from decimal import Decimal

from finance_app.models import Account, Category, Rule, Transaction, Statement

User = get_user_model()

# ============ USER & AUTH FIXTURES ============

@pytest.fixture
def api_client():
    """DRF API client"""
    return APIClient()

@pytest.fixture
def user(db):
    """Create a test user"""
    return User.objects.create_user(
        email='test@example.com',
        password='TestPassword123!',
        full_name='Test User'
    )

@pytest.fixture
def user2(db):
    """Create a second test user (for isolation testing)"""
    return User.objects.create_user(
        email='test2@example.com',
        password='TestPassword123!',
        full_name='Test User 2'
    )

@pytest.fixture
def authenticated_client(api_client, user):
    """API client authenticated as test user"""
    from finance_app.utils import JWTUtils
    access_token, refresh_token, _ = JWTUtils.generate_tokens(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
    return api_client

# ============ ACCOUNT FIXTURES ============

@pytest.fixture
def account(db, user):
    """Create a test account"""
    return Account.objects.create(
        user=user,
        name='PC Financial Mastercard',
        bank_key='PCFinancial-Mastercard',
        account_type='credit',
        currency='CAD',
        import_format='twoDateAmount',
        latest_balance=Decimal('-500.00')
    )

@pytest.fixture
def debit_account(db, user):
    """Create a debit account for testing"""
    return Account.objects.create(
        user=user,
        name='TD Chequing',
        bank_key='TD-Chequing',
        account_type='debit',
        currency='CAD',
        import_format='endAnchoredSplitCols',
        latest_balance=Decimal('3000.00')
    )

# ============ CATEGORY FIXTURES ============

@pytest.fixture
def subscriptions_category(db, user):
    """Create subscriptions category"""
    return Category.objects.create(
        user=user,
        name='Subscriptions',
        is_internal=False,
        color='#d97757'
    )

@pytest.fixture
def internal_transfer_category(db, user):
    """Create internal transfer category"""
    return Category.objects.create(
        user=user,
        name='Transfer (internal)',
        is_internal=True,
        color='#b0aea5'
    )

# ============ RULE FIXTURES ============

@pytest.fixture
def netflix_rule(db, user, subscriptions_category):
    """Create Netflix categorization rule"""
    return Rule.objects.create(
        user=user,
        category=subscriptions_category,
        pattern='netflix|spotify|disney\\+',
        pattern_type='regex',
        priority=100,
        is_active=True
    )

# ============ TRANSACTION FIXTURES ============

@pytest.fixture
def transactions(db, user, account, subscriptions_category):
    """Create multiple test transactions"""
    txs = []

    # Netflix subscription
    txs.append(Transaction.objects.create(
        user=user,
        account=account,
        category=subscriptions_category,
        date='2026-09-30',
        description='NETFLIX MONTHLY CHARGE',
        amount=Decimal('-24.99'),
        source='PDF',
        is_recurring=True,
        recurring_cadence='Monthly'
    ))

    # Starbucks (non-recurring)
    txs.append(Transaction.objects.create(
        user=user,
        account=account,
        category=subscriptions_category,
        date='2026-09-15',
        description='STARBUCKS #1234',
        amount=Decimal('-6.50'),
        source='PDF'
    ))

    # Income
    txs.append(Transaction.objects.create(
        user=user,
        account=account,
        date='2026-09-01',
        description='PAYROLL DEPOSIT',
        amount=Decimal('4500.00'),
        source='PDF'
    ))

    return txs

# ============ STATEMENT FIXTURES ============

@pytest.fixture
def statement(db, user, account):
    """Create a test statement"""
    return Statement.objects.create(
        user=user,
        account=account,
        bank_key='PCFinancial-Mastercard',
        account_type='credit',
        file_name='PC_Mastercard_2026-09.pdf',
        period_start='2026-09-01',
        period_end='2026-09-30',
        closing_balance=Decimal('-500.00'),
        statement_hash='abc123def456',
        reconciled=True,
        transaction_count=1
    )

# ============ SAMPLE DATA FIXTURES ============

@pytest.fixture
def sample_pdf_bytes():
    """Mock PDF file content"""
    # In real tests, this would be actual PDF bytes
    return b'%PDF-1.4\n%Mock PDF content'

@pytest.fixture
def sample_csv_content():
    """Mock CSV file content (KOHO format)"""
    return """Date,Transaction,Loads,Withdrawal
2026-09-30,NETFLIX MONTHLY,0,24.99
2026-09-01,PAYROLL,4500.00,0
"""

# ============ MARKERS ============

def pytest_configure(config):
    """Register custom pytest markers"""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "parsing: marks tests for parser functionality")
