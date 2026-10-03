"""
File upload and statement import handling
"""

from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
import logging

from models import Account, Statement, Transaction, Category, ImportLog, AuditLog
from parsers import StatementParser, Deduplicator
from utils import AuditLogger

logger = logging.getLogger(__name__)

# ============ FILE UPLOAD VIEW ============

class UploadView(views.APIView):
    """Handle file upload and statement import"""
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        """Upload and parse a statement file"""

        # Validate request
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_obj = request.FILES['file']
        bank_key = request.data.get('bank_key')
        account_id = request.data.get('account_id')

        # Validate inputs
        if not bank_key:
            return Response(
                {'error': 'bank_key is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file size (10MB max)
        if file_obj.size > 10485760:  # 10MB
            return Response(
                {'error': 'File too large (max 10MB)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file type
        file_name = file_obj.name
        if not (file_name.lower().endswith('.pdf') or file_name.lower().endswith('.csv')):
            return Response(
                {'error': 'Only PDF and CSV files are supported'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Parse the file
            file_bytes = file_obj.read()
            parse_result, metadata = StatementParser.parse(
                file_bytes,
                file_name,
                bank_key
            )

            # Log the import attempt
            import_log = ImportLog.objects.create(
                user=request.user,
                file_name=file_name,
                file_size=file_obj.size,
                bank_key=bank_key,
                rows_processed=len(parse_result.transactions),
                import_status='processing'
            )

            # Check for duplicates (statement-level)
            statement_hash = metadata['statement_hash']
            if Statement.objects.filter(user=request.user, statement_hash=statement_hash).exists():
                import_log.rows_deduplicated = len(parse_result.transactions)
                import_log.import_status = 'partial'
                import_log.error_message = 'Statement already imported (duplicate detected)'
                import_log.save()

                AuditLogger.log(
                    request.user,
                    'import_duplicate',
                    'statement',
                    None,
                    {'file_name': file_name, 'bank_key': bank_key}
                )

                return Response({
                    'status': 'duplicate',
                    'file_name': file_name,
                    'rows_processed': len(parse_result.transactions),
                    'rows_imported': 0,
                    'rows_deduplicated': len(parse_result.transactions),
                    'message': 'Statement has already been imported'
                }, status=status.HTTP_200_OK)

            # Get or create account
            if account_id:
                try:
                    account = Account.objects.get(id=account_id, user=request.user)
                except Account.DoesNotExist:
                    return Response(
                        {'error': f'Account {account_id} not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                # Create account if it doesn't exist
                account, created = Account.objects.get_or_create(
                    user=request.user,
                    bank_key=bank_key,
                    defaults={
                        'name': bank_key,
                        'account_type': metadata.get('account_type', 'debit')
                    }
                )

            # Create statement record
            statement = Statement.objects.create(
                user=request.user,
                account=account,
                bank_key=bank_key,
                account_type=metadata.get('account_type', 'debit'),
                file_name=file_name,
                statement_hash=statement_hash,
                transaction_count=len(parse_result.transactions),
                reconciled=parse_result.reconciled
            )

            # Categorize and import transactions
            imported_count = 0
            deduped_count = 0
            errors = []

            with transaction.atomic():
                for parsed_tx in parse_result.transactions:
                    try:
                        # Check for transaction-level duplicates
                        tx_hash = Deduplicator.calculate_transaction_hash(parsed_tx)
                        if Transaction.objects.filter(
                            user=request.user,
                            import_id=tx_hash,
                            statement=statement
                        ).exists():
                            deduped_count += 1
                            continue

                        # Categorize transaction
                        category = self.categorize_transaction(request.user, parsed_tx.description)

                        # Create transaction
                        tx = Transaction.objects.create(
                            user=request.user,
                            account=account,
                            statement=statement,
                            category=category,
                            date=parsed_tx.date,
                            description=parsed_tx.description,
                            amount=parsed_tx.amount,
                            source=metadata['file_format'],
                            import_id=tx_hash
                        )
                        imported_count += 1

                        # Log audit
                        AuditLogger.log(
                            request.user,
                            'import_transaction',
                            'transaction',
                            tx.id,
                            {'import_file': file_name}
                        )

                    except Exception as e:
                        logger.error(f"Failed to import transaction: {e}")
                        errors.append(str(e))
                        continue

            # Update account's latest balance and statement date
            account.latest_balance = statement.closing_balance or account.latest_balance
            account.latest_statement_date = statement.period_end or account.latest_statement_date
            account.save()

            # Update import log
            import_log.rows_imported = imported_count
            import_log.rows_deduplicated = deduped_count
            import_log.import_status = 'success'
            if errors:
                import_log.error_message = ' | '.join(errors[:5])  # Store first 5 errors
            import_log.save()

            # Log successful import
            AuditLogger.log(
                request.user,
                'import_statement',
                'statement',
                statement.id,
                {
                    'file_name': file_name,
                    'bank_key': bank_key,
                    'rows_imported': imported_count
                }
            )

            return Response({
                'status': 'success',
                'file_name': file_name,
                'rows_processed': len(parse_result.transactions),
                'rows_imported': imported_count,
                'rows_deduplicated': deduped_count,
                'errors': errors if errors else None
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            # Parser error
            import_log = ImportLog.objects.create(
                user=request.user,
                file_name=file_name,
                file_size=file_obj.size,
                bank_key=bank_key,
                import_status='failed',
                error_message=str(e)
            )

            return Response({
                'error': str(e),
                'file_name': file_name
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Unexpected error
            logger.error(f"Upload failed: {e}")
            import_log = ImportLog.objects.create(
                user=request.user,
                file_name=file_name,
                file_size=file_obj.size,
                bank_key=bank_key,
                import_status='failed',
                error_message=f'Internal error: {str(e)}'
            )

            return Response({
                'error': 'Failed to process file',
                'file_name': file_name
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def categorize_transaction(self, user, description):
        """Auto-categorize a transaction based on rules"""
        import re

        # Get active rules, ordered by priority
        rules = list(
            user.rules.filter(is_active=True).order_by('-priority')
        )

        for rule in rules:
            try:
                if rule.pattern_type == 'regex':
                    if re.search(rule.pattern, description, re.IGNORECASE):
                        return rule.category

                elif rule.pattern_type == 'exact':
                    if rule.pattern.lower() == description.lower():
                        return rule.category

                elif rule.pattern_type == 'contains':
                    if rule.pattern.lower() in description.lower():
                        return rule.category

            except Exception as e:
                logger.warning(f"Rule matching failed for rule {rule.id}: {e}")
                continue

        # Default category if no rules match
        default_category, created = Category.objects.get_or_create(
            user=user,
            name='Uncategorized',
            defaults={'is_internal': False}
        )
        return default_category
