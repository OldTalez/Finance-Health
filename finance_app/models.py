"""
Core models for Finance Platform
Centralized model definitions for all apps
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.validators import EmailValidator, MinLengthValidator
import hashlib
import json

# ===================== AUTH =====================
class User(AbstractUser):
    """Extended user model with finance-specific fields"""
    email = models.EmailField(unique=True, validators=[EmailValidator()])
    full_name = models.CharField(max_length=255, blank=True)
    is_email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    # Encryption key for per-user data encryption (AES-256-GCM)
    encryption_key_salt = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.email


class RefreshToken(models.Model):
    """Refresh tokens for JWT auth (for revocation/rotation)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='refresh_tokens')
    token = models.CharField(max_length=500)  # hashed token
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_revoked = models.BooleanField(default=False)

    class Meta:
        db_table = 'refresh_tokens'
        indexes = [
            models.Index(fields=['user', 'expires_at']),
        ]


# ===================== ACCOUNTS =====================
class Account(models.Model):
    """User's bank accounts (credit cards, debit accounts, savings)"""
    ACCOUNT_TYPE_CHOICES = [
        ('credit', 'Credit Card'),
        ('debit', 'Debit Account'),
        ('savings', 'Savings Account'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=255)  # e.g. "PC Financial Mastercard"
    bank_key = models.CharField(max_length=50)  # e.g. "PCFinancial-Mastercard"
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)

    # Account number encrypted at rest (AES-256-GCM)
    account_number_encrypted = models.CharField(max_length=255, blank=True)
    account_holder_name_encrypted = models.CharField(max_length=255, blank=True)

    currency = models.CharField(max_length=3, default='CAD')

    # Statement parsing configuration
    import_format = models.CharField(
        max_length=30,
        blank=True,
        choices=[
            ('twoDateAmount', 'Two Dates + Amount'),
            ('twoDateBalance', 'Two Dates + Balance'),
            ('twoDateSplitCols', 'Two Dates + Split Columns'),
            ('singleDateBalance', 'Single Date + Balance'),
            ('endAnchoredSplitCols', 'End Anchored Split Columns (TD Branch)'),
            ('CSV', 'CSV Export'),
        ]
    )

    latest_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    latest_statement_date = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts'
        unique_together = [['user', 'name']]
        indexes = [
            models.Index(fields=['user', 'bank_key']),
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.name}"


class Statement(models.Model):
    """Metadata for each imported statement (for deduplication & tracking)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='statements')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='statements')

    file_name = models.CharField(max_length=255)
    bank_key = models.CharField(max_length=50)
    account_type = models.CharField(max_length=20)

    period_start = models.DateField()
    period_end = models.DateField()

    previous_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    minimum_payment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payment_due_date = models.DateField(null=True, blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    available_credit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # SHA-256 hash of statement content for deduplication
    statement_hash = models.CharField(max_length=64, db_index=True)
    reconciled = models.BooleanField(default=False)
    transaction_count = models.IntegerField(default=0)

    imported_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'statements'
        unique_together = [['statement_hash', 'user']]  # Prevent duplicate imports
        indexes = [
            models.Index(fields=['user', 'account']),
            models.Index(fields=['period_start', 'period_end']),
            models.Index(fields=['statement_hash']),
        ]

    def __str__(self):
        return f"{self.account.name} - {self.period_end}"


# ===================== CATEGORIES & RULES =====================
class Category(models.Model):
    """Expense categories for transactions"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)

    # Mark internal transfers, credit card payments, debt payments for exclusion
    is_internal = models.BooleanField(default=False, db_index=True)

    color = models.CharField(max_length=7, default='#6a9bcc')  # hex color
    icon = models.CharField(max_length=50, blank=True)  # icon name for UI

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'categories'
        unique_together = [['user', 'name']]
        indexes = [
            models.Index(fields=['user', 'is_internal']),
        ]

    def __str__(self):
        return self.name


class Rule(models.Model):
    """Categorization rules: pattern matching for auto-categorization"""
    PATTERN_TYPE_CHOICES = [
        ('regex', 'Regular Expression'),
        ('exact', 'Exact Match'),
        ('contains', 'Contains'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rules')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='rules')

    pattern = models.CharField(max_length=500)  # regex pattern to match description
    pattern_type = models.CharField(max_length=20, choices=PATTERN_TYPE_CHOICES, default='regex')

    priority = models.IntegerField(default=0, db_index=True)  # Higher = checked first
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rules'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['priority', 'is_active']),
        ]
        ordering = ['-priority', 'created_at']

    def __str__(self):
        return f"{self.category.name}: {self.pattern}"


# ===================== TRANSACTIONS =====================
class Transaction(models.Model):
    """Individual transactions imported from statements"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    statement = models.ForeignKey(Statement, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    date = models.DateField(db_index=True)
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # negative = expense, positive = income

    source = models.CharField(max_length=50, default='PDF', choices=[('PDF', 'PDF'), ('CSV', 'CSV'), ('manual', 'Manual')])

    is_recurring = models.BooleanField(default=False, db_index=True)
    recurring_cadence = models.CharField(
        max_length=50,
        blank=True,
        choices=[('Daily', 'Daily'), ('Weekly', 'Weekly'), ('Monthly', 'Monthly'), ('Quarterly', 'Quarterly'), ('Annual', 'Annual')]
    )

    flag = models.CharField(
        max_length=50,
        blank=True,
        choices=[('outlier', 'Outlier'), ('new_merchant', 'New Merchant'), ('large_purchase', 'Large Purchase')]
    )

    # For deduplication (hash of date+description+amount from statement)
    import_id = models.CharField(max_length=255, db_index=True, blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transactions'
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'category']),
            models.Index(fields=['user', 'is_recurring']),
            models.Index(fields=['account', 'date']),
            models.Index(fields=['import_id', 'user']),  # For deduplication
        ]
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.date} - {self.description} ({self.amount})"


class RecurringCharge(models.Model):
    """Summary of detected recurring transactions"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recurring_charges')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)

    merchant = models.CharField(max_length=255, blank=True)  # For non-bill recurring
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # Median/typical amount

    cadence = models.CharField(
        max_length=50,
        choices=[('Daily', 'Daily'), ('Weekly', 'Weekly'), ('Monthly', 'Monthly'), ('Quarterly', 'Quarterly'), ('Annual', 'Annual')]
    )

    occurrences = models.IntegerField(default=1)
    last_occurrence = models.DateField()
    next_expected_date = models.DateField()

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'recurring_charges'
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"{self.merchant or self.category.name} - {self.cadence}"


# ===================== IMPORT & LOGGING =====================
class ImportLog(models.Model):
    """Track each file import for debugging and audit"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='import_logs')

    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField()
    bank_key = models.CharField(max_length=50)

    rows_processed = models.IntegerField(default=0)
    rows_imported = models.IntegerField(default=0)
    rows_deduplicated = models.IntegerField(default=0)

    error_message = models.TextField(blank=True)
    import_status = models.CharField(
        max_length=50,
        choices=[('success', 'Success'), ('partial', 'Partial'), ('failed', 'Failed')],
        default='success'
    )

    ocr_text_sample = models.TextField(blank=True)  # For OCR debugging
    imported_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'import_logs'
        indexes = [
            models.Index(fields=['user', 'imported_at']),
        ]
        ordering = ['-imported_at']

    def __str__(self):
        return f"{self.file_name} - {self.import_status}"


class AuditLog(models.Model):
    """User actions for compliance and debugging"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audit_logs')

    action = models.CharField(max_length=100)  # 'login', 'import', 'categorize', 'delete', etc
    resource_type = models.CharField(max_length=50)  # 'transaction', 'statement', 'rule', etc
    resource_id = models.IntegerField(null=True, blank=True)

    details = models.JSONField(default=dict, blank=True)  # Extra context as JSON

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_log'
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.action} - {self.created_at}"
