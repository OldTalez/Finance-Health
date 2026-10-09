"""
File upload and statement import handling
"""

from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
import logging
import os

from .models import Account, Statement, Transaction, Category, ImportLog, AuditLog
from .parsers import StatementParser, Deduplicator, CSV_BANK_MAP, PDF_BANK_MAP
from .utils import AuditLogger

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
KNOWN_BANK_KEYS = set(CSV_BANK_MAP) | set(PDF_BANK_MAP)

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
        import_log = None

        # Validate inputs
        if not bank_key:
            return Response(
                {'error': 'bank_key is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Declared size is only a quick first check; the bytes read below are what count
        if file_obj.size > MAX_UPLOAD_BYTES:
            return Response(
                {'error': 'File too large (max 10MB)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file type: the extension, then the content itself
        file_name = os.path.basename(file_obj.name or '')[:255]
        if not (file_name.lower().endswith('.pdf') or file_name.lower().endswith('.csv')):
            return Response(
                {'error': 'Only PDF and CSV files are supported'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if bank_key not in KNOWN_BANK_KEYS:
            return Response({'error': 'Unknown bank_key'}, status=status.HTTP_400_BAD_REQUEST)

        if account_id not in (None, ''):
            try:
                account_id = int(account_id)
            except (TypeError, ValueError):
                return Response({'error': 'account_id must be a number'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            account_id = None

        file_bytes = file_obj.read(MAX_UPLOAD_BYTES + 1)
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            return Response({'error': 'File too large (max 10MB)'}, status=status.HTTP_400_BAD_REQUEST)
        if file_name.lower().endswith('.pdf'):
            if not file_bytes.startswith(b'%PDF-'):
                return Response({'error': 'File is not a valid PDF'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if b'\x00' in file_bytes:
                return Response({'error': 'File is not a valid CSV'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                return Response({'error': 'CSV must be UTF-8 text'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Parse the file
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

            if not parse_result.transactions:
                raise ValueError('No transactions found in the file; nothing was imported')

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

            # Statement, transactions and their audit rows commit together or not at all, so a
            # failed import cannot leave a statement behind that blocks re-uploading the file.
            imported_count = 0
            deduped_count = 0
            errors = []

            with transaction.atomic():
                statement = Statement.objects.create(
                    user=request.user,
                    account=account,
                    bank_key=bank_key,
                    account_type=metadata.get('account_type', 'debit'),
                    file_name=file_name,
                    statement_hash=statement_hash,
                    period_start=min(t.date for t in parse_result.transactions).date(),
                    period_end=max(t.date for t in parse_result.transactions).date(),
                    transaction_count=len(parse_result.transactions),
                    reconciled=parse_result.reconciled
                )

                # Two identical rows on one statement (same day, text and amount) are two real
                # transactions, so the hash carries an occurrence number instead of dropping them.
                seen = {}
                for parsed_tx in parse_result.transactions:
                    base_hash = Deduplicator.calculate_transaction_hash(parsed_tx)
                    seen[base_hash] = seen.get(base_hash, 0) + 1
                    tx_hash = base_hash if seen[base_hash] == 1 else f"{base_hash}-{seen[base_hash]}"

                    if Transaction.objects.filter(
                        user=request.user,
                        import_id=tx_hash,
                        statement=statement
                    ).exists():
                        deduped_count += 1
                        continue

                    category = self.categorize_transaction(request.user, parsed_tx.description)

                    # Any failure here aborts the whole import: a half-imported statement
                    # silently misstates the balance.
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

                    AuditLogger.log(
                        request.user,
                        'import_transaction',
                        'transaction',
                        tx.id,
                        {'import_file': file_name}
                    )

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
            self._record_failure(request.user, import_log, file_name, file_obj.size, bank_key, str(e))

            return Response({
                'error': str(e),
                'file_name': file_name
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Unexpected error
            logger.error(f"Upload failed: {e}")
            self._record_failure(
                request.user, import_log, file_name, file_obj.size, bank_key, 'Internal error'
            )

            return Response({
                'error': 'Failed to process file',
                'file_name': file_name
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @staticmethod
    def _record_failure(user, import_log, file_name, file_size, bank_key, message):
        if import_log is not None:
            import_log.import_status = 'failed'
            import_log.error_message = message
            import_log.save()
        else:
            ImportLog.objects.create(
                user=user, file_name=file_name, file_size=file_size,
                bank_key=bank_key, import_status='failed', error_message=message
            )

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
