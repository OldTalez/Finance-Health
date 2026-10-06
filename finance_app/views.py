"""
API Views for Finance Platform
"""

from rest_framework import viewsets, status, views, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q, Sum, Case, When, DecimalField, Count
from datetime import timedelta, datetime
from decimal import Decimal
import logging

from .models import (
    User, Account, Statement, Category, Rule, Transaction,
    RecurringCharge, ImportLog, AuditLog, RefreshToken
)
from .serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer, TokenSerializer,
    AccountSerializer, TransactionSerializer, CategorySerializer, RuleSerializer,
    DashboardSerializer, RecurringChargeSerializer, ImportLogSerializer
)
from .utils import JWTUtils, AuditLogger

logger = logging.getLogger(__name__)

# ============ AUTHENTICATION VIEWS ============

class RegisterView(views.APIView):
    """User registration endpoint"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            # Log audit event
            AuditLogger.log(user, 'register', 'user', user.id, {'email': user.email})
            return Response(
                UserSerializer(user).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(views.APIView):
    """User login endpoint — returns JWT tokens"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Generate JWT tokens
            access_token, refresh_token, expires_in = JWTUtils.generate_tokens(user)

            # Log audit event
            AuditLogger.log(user, 'login', 'user', user.id, {'ip': self.get_client_ip()})

            return Response({
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_in': expires_in,
                'token_type': 'Bearer'
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

    def get_client_ip(self):
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return self.request.META.get('REMOTE_ADDR')


class RefreshTokenView(views.APIView):
    """Refresh expired access token"""
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh_token')
        if not refresh_token:
            return Response(
                {'detail': 'Refresh token required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        tokens = JWTUtils.rotate_refresh_token(refresh_token)
        if tokens is None:
            return Response(
                {'detail': 'Invalid or expired refresh token'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        access_token, new_refresh_token, expires_in = tokens
        return Response({
            'access_token': access_token,
            'refresh_token': new_refresh_token,
            'expires_in': expires_in
        }, status=status.HTTP_200_OK)


class LogoutView(views.APIView):
    """Revoke a refresh token (and its rotation family)"""
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh_token')
        if not refresh_token or not isinstance(refresh_token, str):
            return Response(
                {'detail': 'Refresh token required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Same answer whether or not the token was known: nothing to probe
        JWTUtils.revoke_refresh_token(refresh_token)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserProfileView(views.APIView):
    """Get current user profile"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============ ACCOUNT VIEWS ============

class AccountViewSet(viewsets.ModelViewSet):
    """User's bank accounts CRUD"""
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'bank_key']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return Account.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        account = serializer.save(user=self.request.user)
        AuditLogger.log(self.request.user, 'create', 'account', account.id)

    def perform_update(self, serializer):
        account = serializer.save()
        AuditLogger.log(self.request.user, 'update', 'account', account.id)

    def perform_destroy(self, instance):
        account_id = instance.id
        instance.delete()
        AuditLogger.log(self.request.user, 'delete', 'account', account_id)


# ============ TRANSACTION VIEWS ============

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


class TransactionViewSet(viewsets.ModelViewSet):
    """Transaction CRUD with filtering"""
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['description']
    ordering_fields = ['date', 'amount', 'created_at']
    ordering = ['-date']

    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user).select_related(
            'account', 'category'
        )

        # Apply filters
        account_id = self.request.query_params.get('account_id')
        if account_id:
            queryset = queryset.filter(account_id=account_id)

        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        is_recurring = self.request.query_params.get('is_recurring')
        if is_recurring:
            queryset = queryset.filter(is_recurring=is_recurring.lower() == 'true')

        flag = self.request.query_params.get('flag')
        if flag:
            queryset = queryset.filter(flag=flag)

        return queryset

    def perform_update(self, serializer):
        transaction = serializer.save()
        AuditLogger.log(
            self.request.user, 'update', 'transaction', transaction.id,
            {'category_id': transaction.category_id}
        )

    def perform_destroy(self, instance):
        tx_id = instance.id
        instance.delete()
        AuditLogger.log(self.request.user, 'delete', 'transaction', tx_id)

    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export transactions as CSV"""
        queryset = self.get_queryset()

        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transactions.csv"'

        writer = csv.writer(response)
        writer.writerow(['Date', 'Description', 'Amount', 'Account', 'Category', 'Recurring', 'Flag'])

        for tx in queryset:
            writer.writerow([
                tx.date,
                tx.description,
                tx.amount,
                tx.account.name,
                tx.category.name if tx.category else 'Uncategorized',
                'Yes' if tx.is_recurring else 'No',
                tx.flag or ''
            ])

        return response


# ============ CATEGORY VIEWS ============

class CategoryViewSet(viewsets.ModelViewSet):
    """Category CRUD"""
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        category = serializer.save(user=self.request.user)
        AuditLogger.log(self.request.user, 'create', 'category', category.id)

    def perform_destroy(self, instance):
        cat_id = instance.id
        instance.delete()
        AuditLogger.log(self.request.user, 'delete', 'category', cat_id)


# ============ RULE VIEWS ============

class RuleViewSet(viewsets.ModelViewSet):
    """Categorization rule CRUD"""
    serializer_class = RuleSerializer
    permission_classes = [IsAuthenticated]
    ordering = ['-priority', 'created_at']

    def get_queryset(self):
        return Rule.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        rule = serializer.save(user=self.request.user)
        AuditLogger.log(self.request.user, 'create', 'rule', rule.id)

    def perform_destroy(self, instance):
        rule_id = instance.id
        instance.delete()
        AuditLogger.log(self.request.user, 'delete', 'rule', rule_id)


# ============ DASHBOARD VIEWS ============

class DashboardView(views.APIView):
    """Main dashboard with key metrics"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            metrics = self.compute_dashboard_metrics(request.user)
            return Response(metrics, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Dashboard computation failed: {e}")
            return Response(
                {'detail': 'Failed to compute dashboard'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def compute_dashboard_metrics(self, user):
        """Compute dashboard metrics (net worth, money left, etc)"""

        # Get all transactions for the user
        transactions = Transaction.objects.filter(user=user).select_related('account', 'category')

        # Determine current month (most recent month with data)
        if not transactions.exists():
            return self.get_empty_dashboard(user)

        latest_date = transactions.latest('date').date
        current_month_start = latest_date.replace(day=1)
        current_month_end = (current_month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        # Filter this month's transactions
        this_month_txs = transactions.filter(
            date__gte=current_month_start,
            date__lte=current_month_end
        )

        # Calculate money left this month
        money_left = self.calculate_money_left(this_month_txs)

        # Calculate net worth
        net_worth_data = self.calculate_net_worth(user)

        # Category breakdown
        category_breakdown = self.calculate_category_breakdown(this_month_txs)

        # Account balances
        account_balances = self.get_account_balances(user)

        # Upcoming payments
        upcoming_payments = self.get_upcoming_payments(user)

        return {
            'money_left_this_month': {
                'value': str(money_left),
                'currency': 'CAD',
                'period': current_month_start.strftime('%B %Y')
            },
            'net_worth': net_worth_data,
            'account_balances': account_balances,
            'spending_by_category': category_breakdown,
            'upcoming_payments': upcoming_payments
        }

    def calculate_money_left(self, transactions):
        """Income - Spending (excluding internal transfers)"""
        # Exclude internal transfers
        real_txs = transactions.exclude(
            Q(category__is_internal=True) |
            Q(category__name__icontains='(internal)')
        )

        income = real_txs.filter(amount__gt=0).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        spending = real_txs.filter(amount__lt=0).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

        return income + spending  # spending is negative

    def calculate_net_worth(self, user):
        """Net worth = debit/savings - credit cards"""
        accounts = Account.objects.filter(user=user)
        total_assets = Decimal('0')
        total_debt = Decimal('0')

        for account in accounts:
            if account.latest_balance is None:
                continue

            if account.account_type == 'credit':
                total_debt += account.latest_balance
            else:
                total_assets += account.latest_balance

        net_worth = total_assets - total_debt

        return {
            'value': str(net_worth),
            'currency': 'CAD',
            'breakdown': {
                'debit_savings': str(total_assets),
                'credit_card_debt': str(total_debt)
            }
        }

    def calculate_category_breakdown(self, transactions):
        """Spending by category (real spending only)"""
        real_txs = transactions.exclude(
            Q(category__is_internal=True) |
            Q(category__name__icontains='(internal)')
        ).filter(amount__lt=0)

        totals = real_txs.values('category__name').annotate(
            total=Sum('amount')
        ).order_by('-total')

        # Calculate percentages
        grand_total = abs(sum([t['total'] for t in totals]) or Decimal('0'))

        results = []
        for item in totals:
            amount = abs(item['total'])
            percentage = (amount / grand_total * 100) if grand_total > 0 else 0
            results.append({
                'category_name': item['category__name'],
                'total': str(amount),
                'percentage': f"{percentage:.1f}"
            })

        return results

    def get_account_balances(self, user):
        """Latest balance per account"""
        accounts = Account.objects.filter(user=user, latest_balance__isnull=False)
        return [
            {
                'account_id': a.id,
                'name': a.name,
                'balance': str(a.latest_balance),
                'as_of_date': a.latest_statement_date
            }
            for a in accounts.order_by('-latest_balance')
        ]

    def get_upcoming_payments(self, user):
        """Upcoming credit card payments"""
        accounts = Account.objects.filter(
            user=user,
            account_type='credit'
        ).filter(
            statements__payment_due_date__isnull=False,
            statements__minimum_payment__isnull=False
        ).distinct()

        payments = []
        for account in accounts:
            latest_stmt = account.statements.order_by('-period_end').first()
            if latest_stmt and latest_stmt.payment_due_date > timezone.now().date():
                payments.append({
                    'category_name': 'Credit Card Payment',
                    'amount': str(latest_stmt.minimum_payment),
                    'expected_date': latest_stmt.payment_due_date,
                    'recurring_cadence': 'Monthly'
                })

        return sorted(payments, key=lambda x: x['expected_date'])

    def get_empty_dashboard(self, user):
        """Return empty dashboard for new users"""
        return {
            'money_left_this_month': {'value': '0.00', 'currency': 'CAD', 'period': 'N/A'},
            'net_worth': {'value': '0.00', 'currency': 'CAD', 'breakdown': {}},
            'account_balances': [],
            'spending_by_category': [],
            'upcoming_payments': []
        }


# ============ IMPORT/UPLOAD VIEWS ============

class ImportStatusView(views.APIView):
    """Check async import status"""
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        # TODO: Implement async task tracking
        return Response({'status': 'not_implemented'}, status=status.HTTP_501_NOT_IMPLEMENTED)


class ImportHistoryView(views.APIView):
    """List past imports"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        imports = ImportLog.objects.filter(user=request.user).order_by('-imported_at')[:20]
        data = {
            'count': len(imports),
            'results': [
                {
                    'import_log_id': im.id,
                    'file_name': im.file_name,
                    'bank_key': im.bank_key,
                    'rows_processed': im.rows_processed,
                    'rows_imported': im.rows_imported,
                    'rows_deduplicated': im.rows_deduplicated,
                    'import_status': im.import_status,
                    'imported_at': im.imported_at
                }
                for im in imports
            ]
        }
        return Response(data)
