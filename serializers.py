"""
DRF Serializers for Finance Platform API
"""

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
import re

from .models import (
    User, RefreshToken, Account, Statement, Category, Rule,
    Transaction, RecurringCharge, ImportLog, AuditLog
)

# ============ AUTH SERIALIZERS ============

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'is_email_verified', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_email_verified']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=12)
    password_confirm = serializers.CharField(write_only=True, min_length=12)

    class Meta:
        model = User
        fields = ['email', 'password', 'password_confirm', 'full_name']

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_password(self, value):
        # Password must contain uppercase, lowercase, number, special char
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError("Password must contain uppercase letter.")
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError("Password must contain lowercase letter.")
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain number.")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise serializers.ValidationError("Password must contain special character.")
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        data['user'] = user
        return data


class TokenSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    expires_in = serializers.IntegerField()
    token_type = serializers.CharField()


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


# ============ ACCOUNT SERIALIZERS ============

class AccountSerializer(serializers.ModelSerializer):
    transaction_count = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            'id', 'name', 'bank_key', 'account_type', 'currency',
            'import_format', 'latest_balance', 'latest_statement_date',
            'is_active', 'transaction_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'latest_balance', 'latest_statement_date', 'created_at', 'updated_at']

    def get_transaction_count(self, obj):
        return obj.transactions.count()


# ============ STATEMENT SERIALIZERS ============

class StatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Statement
        fields = [
            'id', 'account_id', 'file_name', 'bank_key', 'period_start', 'period_end',
            'closing_balance', 'transaction_count', 'reconciled', 'imported_at'
        ]
        read_only_fields = ['id', 'imported_at']


# ============ CATEGORY SERIALIZERS ============

class CategorySerializer(serializers.ModelSerializer):
    rule_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'is_internal', 'color', 'icon', 'rule_count', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_rule_count(self, obj):
        return obj.rules.filter(is_active=True).count()


# ============ RULE SERIALIZERS ============

class RuleSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Rule
        fields = [
            'id', 'category_id', 'category_name', 'pattern', 'pattern_type',
            'priority', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ============ TRANSACTION SERIALIZERS ============

class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'date', 'description', 'amount', 'account_id', 'category_id',
            'category_name', 'source', 'is_recurring', 'recurring_cadence', 'flag',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'source', 'created_at', 'updated_at']


class TransactionFilterSerializer(serializers.Serializer):
    """Serializer for transaction filtering parameters"""
    account_id = serializers.IntegerField(required=False)
    category_id = serializers.IntegerField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    search = serializers.CharField(required=False, max_length=255)
    is_recurring = serializers.BooleanField(required=False)
    flag = serializers.CharField(required=False, max_length=50)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


# ============ RECURRING CHARGE SERIALIZERS ============

class RecurringChargeSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = RecurringCharge
        fields = [
            'id', 'category_id', 'category_name', 'merchant', 'amount', 'cadence',
            'occurrences', 'last_occurrence', 'next_expected_date', 'is_active'
        ]
        read_only_fields = ['id', 'last_occurrence', 'next_expected_date']


# ============ IMPORT LOG SERIALIZERS ============

class ImportLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportLog
        fields = [
            'id', 'file_name', 'file_size', 'bank_key', 'rows_processed',
            'rows_imported', 'rows_deduplicated', 'import_status', 'imported_at'
        ]
        read_only_fields = ['id', 'imported_at']


# ============ DASHBOARD SERIALIZERS ============

class MoneyLeftThisMonthSerializer(serializers.Serializer):
    value = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    period = serializers.CharField()


class NetWorthSerializer(serializers.Serializer):
    value = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    breakdown = serializers.DictField()


class AccountBalanceSerializer(serializers.Serializer):
    account_id = serializers.IntegerField()
    name = serializers.CharField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    as_of_date = serializers.DateField()


class CategoryBreakdownSerializer(serializers.Serializer):
    category_id = serializers.IntegerField()
    category_name = serializers.CharField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    percentage = serializers.DecimalField(max_digits=5, decimal_places=1)


class UpcomingPaymentSerializer(serializers.Serializer):
    category_name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    expected_date = serializers.DateField()
    recurring_cadence = serializers.CharField()


class DashboardSerializer(serializers.Serializer):
    money_left_this_month = MoneyLeftThisMonthSerializer()
    net_worth = NetWorthSerializer()
    account_balances = AccountBalanceSerializer(many=True)
    spending_by_category = CategoryBreakdownSerializer(many=True)
    upcoming_payments = UpcomingPaymentSerializer(many=True)


# ============ AUDIT LOG SERIALIZERS ============

class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'action', 'resource_type', 'resource_id', 'details', 'created_at']
        read_only_fields = ['id', 'created_at']
