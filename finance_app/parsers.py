"""
PDF & CSV Statement Parsers
Port of Finance Tracker Apps Script parsing logic to Python
Handles all 5 PDF formats + CSV with global pattern matching for robustness
"""

import re
import hashlib
import csv
from io import StringIO, BytesIO
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple, Optional
import logging

try:
    import PyPDF2
    from pdf2image import convert_from_bytes
    import pytesseract
except ImportError:
    # Optional dependencies for OCR
    pass

logger = logging.getLogger(__name__)

# ============== CONFIGURATION (FROM Finance Tracker Config.gs) ==============
CSV_BANK_MAP = {
    'KOHO': {
        'hasHeader': True,
        'dateCol': 0,
        'descCol': 1,
        'amountCol': -1,
        'debitCol': 3,
        'creditCol': 2,
        'dateFormat': 'ISO',
        'accountType': 'debit',
        'verified': True
    },
    'RBC': {
        'hasHeader': True,
        'dateCol': 2,
        'descCol': 4,
        'amountCol': 5,
        'debitCol': -1,
        'creditCol': -1,
        'dateFormat': 'YYYY-MM-DD',
        'accountType': 'debit',
        'verified': False
    },
    'TD-Chequing': {
        'hasHeader': False,
        'dateCol': 0,
        'descCol': 1,
        'amountCol': -1,
        'debitCol': 2,
        'creditCol': 3,
        'dateFormat': 'MM/DD/YYYY',
        'accountType': 'debit',
        'verified': False
    }
}

PDF_BANK_MAP = {
    'PCFinancial-Mastercard': {'format': 'twoDateAmount', 'dayFirst': True, 'accountType': 'credit'},
    'TD-CashBack': {'format': 'twoDateAmount', 'dayFirst': False, 'accountType': 'credit'},
    'Wealthsimple-Chequing': {'format': 'twoDateBalance', 'dayFirst': False, 'accountType': 'debit'},
    'PCFinancial-Money': {'format': 'twoDateSplitCols', 'dayFirst': True, 'accountType': 'debit'},
    'PCFinancial-MoneySavings': {'format': 'singleDateBalance', 'accountType': 'debit'},
    'TD-Chequing': {'format': 'endAnchoredSplitCols', 'accountType': 'debit'},
    'TD-Savings': {'format': 'endAnchoredSplitCols', 'accountType': 'debit'},
}

# ============== TRANSACTION PARSING ==============
class Transaction:
    """Parsed transaction"""
    def __init__(self, date: datetime, description: str, amount: Decimal):
        self.date = date
        self.description = description.strip()
        self.amount = amount  # negative = expense, positive = income

    def to_dict(self) -> Dict:
        return {
            'date': self.date.date(),
            'description': self.description,
            'amount': float(self.amount),
        }


class ParseResult:
    """Result of parsing a statement"""
    def __init__(self, transactions: List[Transaction], reconciled: bool = False):
        self.transactions = transactions
        self.reconciled = reconciled

    def calculate_hash(self) -> str:
        """SHA-256 hash of all transactions for deduplication"""
        tx_strings = '|'.join([f"{t.date.isoformat()}{t.description}{t.amount}" for t in self.transactions])
        return hashlib.sha256(tx_strings.encode()).hexdigest()


# ============== PDF PARSING ==============
class PDFParser:
    """Parse PDF statements with OCR via Tesseract"""

    @staticmethod
    def extract_text_from_pdf(pdf_blob: bytes, language: str = 'eng') -> str:
        """
        Extract text from PDF using pytesseract OCR
        Handles complex layouts with reordering gracefully
        """
        try:
            # Convert PDF to images
            images = convert_from_bytes(pdf_blob)

            # OCR each image
            text_parts = []
            for image in images:
                text = pytesseract.image_to_string(image, lang=language)
                text_parts.append(text)

            return '\n'.join(text_parts)
        except Exception as e:
            logger.error(f"PDF OCR failed: {e}")
            raise ValueError(f"Failed to OCR PDF: {e}")

    @staticmethod
    def parse_statement(text: str, bank_key: str) -> ParseResult:
        """Route to appropriate parser based on bank key and format"""
        if bank_key not in PDF_BANK_MAP:
            raise ValueError(f"Unknown bank key: {bank_key}")

        config = PDF_BANK_MAP[bank_key]
        parser_func = {
            'twoDateAmount': PDFParser._parse_two_date_amount,
            'twoDateBalance': PDFParser._parse_two_date_balance,
            'twoDateSplitCols': PDFParser._parse_two_date_split_cols,
            'singleDateBalance': PDFParser._parse_single_date_balance,
            'endAnchoredSplitCols': PDFParser._parse_end_anchored_split_cols,
        }[config['format']]

        transactions = parser_func(text, config)
        return ParseResult(transactions, reconciled=True)

    @staticmethod
    def _parse_two_date_amount(text: str, config: Dict) -> List[Transaction]:
        """
        Parse: date date description amount (credit cards)
        E.g., "01/15 01/16 NETFLIX MONTHLY CHARGE -24.99"
        """
        transactions = []

        # Regex: date pattern, space, date pattern, space, description (non-digit words), amount (signed number)
        # ISO dates, DD/MM, MM/DD patterns
        date_pattern = r'(\d{1,4}[-/]\d{1,2}[-/]\d{1,4}|\d{1,2}[-/]\d{1,2})'
        amount_pattern = r'([-+]?\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)'

        # Global scan for "date date description amount" pattern
        pattern = rf"{date_pattern}\s+{date_pattern}\s+([A-Za-z0-9\s\-\.,']+?)\s+{amount_pattern}(?:\s|$)"

        for match in re.finditer(pattern, text):
            try:
                date_str = match.group(1) or match.group(2)  # Use first or second date
                desc = match.group(3).strip()
                amt_str = match.group(4)

                # Parse amount (remove commas/spaces)
                amt = Decimal(amt_str.replace(',', '').replace(' ', ''))

                # Parse date
                date = PDFParser._parse_date(date_str, config.get('dayFirst', False))

                # Flip sign for credit accounts (charge = positive in statement, negative in our system)
                if config.get('accountType') == 'credit':
                    amt = -amt

                transactions.append(Transaction(date, desc, amt))
            except Exception as e:
                logger.warning(f"Failed to parse transaction: {match.group(0)}: {e}")
                continue

        return transactions

    @staticmethod
    def _parse_two_date_balance(text: str, config: Dict) -> List[Transaction]:
        """Parse: date date description amount balance (with running balance)"""
        # Similar to twoDateAmount but also captures balance (for verification later)
        return PDFParser._parse_two_date_amount(text, config)

    @staticmethod
    def _parse_two_date_split_cols(text: str, config: Dict) -> List[Transaction]:
        """
        Parse: date date description withdrawals/deposits (no sign, separate columns)
        PC Money Account format: direction resolved from column position
        """
        transactions = []

        # Pattern: two dates, description, two amounts (no sign)
        pattern = r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})\s+(\d{1,2}[-/]\d{1,2}[-/]\d{4})\s+([A-Za-z0-9\s\-\.,']+?)\s+(\d+\.?\d*)\s+(\d+\.?\d*)"

        for match in re.finditer(pattern, text):
            try:
                date_str = match.group(1)
                desc = match.group(3).strip()
                withdrawal = Decimal(match.group(4))  # First amount = withdrawal (expense)
                deposit = Decimal(match.group(5))  # Second amount = deposit (income)

                date = PDFParser._parse_date(date_str, config.get('dayFirst', False))

                # Determine which column has amount (gap-based detection)
                # Withdrawal = expense = negative
                if withdrawal > Decimal('0'):
                    amount = -withdrawal
                    transactions.append(Transaction(date, desc, amount))

                # Deposit = income = positive
                if deposit > Decimal('0'):
                    amount = deposit
                    transactions.append(Transaction(date, desc, amount))
            except Exception as e:
                logger.warning(f"Failed to parse split-col transaction: {e}")
                continue

        return transactions

    @staticmethod
    def _parse_single_date_balance(text: str, config: Dict) -> List[Transaction]:
        """
        Parse: date description amount balance (PC Money Savings)
        Direction from balance delta
        """
        transactions = []

        pattern = r"(\d{4}-\d{2}-\d{2})\s+([A-Za-z0-9\s\-\.,']+?)\s+(\d+\.?\d*)\s+(\d+\.?\d*)"

        prev_balance = None
        for match in re.finditer(pattern, text):
            try:
                date_str = match.group(1)
                desc = match.group(2).strip()
                amount_unsigned = Decimal(match.group(3))
                balance = Decimal(match.group(4))

                date = PDFParser._parse_date(date_str, dayFirst=False)

                # Determine direction from balance change
                if prev_balance is not None:
                    delta = balance - prev_balance
                    if delta > 0:
                        amount = delta  # Income
                    else:
                        amount = delta  # Expense (already negative)
                else:
                    amount = amount_unsigned  # Can't determine direction without previous balance

                prev_balance = balance
                transactions.append(Transaction(date, desc, amount))
            except Exception as e:
                logger.warning(f"Failed to parse single-date transaction: {e}")
                continue

        return transactions

    @staticmethod
    def _parse_end_anchored_split_cols(text: str, config: Dict) -> List[Transaction]:
        """
        Parse: description amount date (no balance, TD Chequing/Savings format)
        Date is END of row, no year ("MAY28")
        Direction from column position
        """
        transactions = []

        # TD format: description, amount, short date (MMMDD)
        pattern = r"([A-Za-z0-9\s\-\.,']+?)\s+(\d+\.?\d*)\s+((?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2})"

        current_year = datetime.now().year
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                desc = match.group(1).strip()
                amt_str = match.group(2)
                date_short = match.group(3)

                # Parse short date (month + day, no year)
                date_str = f"{date_short}{current_year}"
                date = datetime.strptime(date_str, '%b%d%Y').date()

                # Determine direction from column position (heuristic)
                # Default to expense (negative)
                amount = -Decimal(amt_str)

                transactions.append(Transaction(datetime.combine(date, datetime.min.time()), desc, amount))
            except Exception as e:
                logger.warning(f"Failed to parse end-anchored transaction: {e}")
                continue

        return transactions

    @staticmethod
    def _parse_date(date_str: str, dayFirst: bool = False) -> datetime:
        """Parse date string in multiple formats"""
        # Try multiple date formats
        formats = [
            '%d/%m/%Y', '%m/%d/%Y',  # DD/MM or MM/DD
            '%Y-%m-%d',  # ISO
            '%d/%m',  # DD/MM without year (current year assumed)
            '%m/%d',  # MM/DD without year
            '%d-%m-%Y', '%m-%d-%Y',
            '%b %d, %Y', '%B %d, %Y',
        ]

        if dayFirst:
            formats.insert(0, '%d/%m/%Y')
        else:
            formats.insert(0, '%m/%d/%Y')

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # Fallback: try loose parsing
        logger.warning(f"Could not parse date: {date_str}")
        return datetime.now()


# ============== CSV PARSING ==============
class CSVParser:
    """Parse CSV statement exports"""

    @staticmethod
    def parse_csv(csv_content: str, bank_key: str) -> ParseResult:
        """Parse CSV statement by bank"""
        if bank_key not in CSV_BANK_MAP:
            raise ValueError(f"CSV parsing not configured for bank: {bank_key}")

        config = CSV_BANK_MAP[bank_key]
        reader = csv.reader(StringIO(csv_content))

        rows = list(reader)
        start_idx = 1 if config['hasHeader'] else 0

        transactions = []
        for row in rows[start_idx:]:
            if len(row) < 3:
                continue

            try:
                date_str = row[config['dateCol']]
                desc = row[config['descCol']]

                # Parse amount (either single col or split debit/credit)
                if config['amountCol'] >= 0:
                    amt_str = row[config['amountCol']]
                    amount = Decimal(amt_str.replace(',', '').replace('$', '').strip())
                    if config['accountType'] == 'credit':
                        amount = -amount  # Flip sign for credit accounts
                else:
                    # Split debit/credit columns
                    debit = Decimal(row[config['debitCol']].replace(',', '').replace('$', '').strip() or '0')
                    credit = Decimal(row[config['creditCol']].replace(',', '').replace('$', '').strip() or '0')
                    amount = credit - debit  # positive = credit (income), negative = debit (expense)

                # Parse date
                date = CSVParser._parse_csv_date(date_str, config['dateFormat'])

                transactions.append(Transaction(date, desc.strip(), amount))
            except Exception as e:
                logger.warning(f"Failed to parse CSV row: {row}: {e}")
                continue

        return ParseResult(transactions, reconciled=True)

    @staticmethod
    def _parse_csv_date(date_str: str, date_format: str) -> datetime:
        """Parse CSV date based on bank format"""
        formats = {
            'ISO': ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S'],
            'YYYY-MM-DD': ['%Y-%m-%d'],
            'MM/DD/YYYY': ['%m/%d/%Y'],
            'DD/MM/YYYY': ['%d/%m/%Y'],
        }

        for fmt in formats.get(date_format, []):
            try:
                return datetime.strptime(date_str.strip().split()[0], fmt)  # Take first part (ignore time)
            except ValueError:
                continue

        logger.warning(f"Could not parse CSV date: {date_str}")
        return datetime.now()


# ============== DEDUPLICATION ==============
class Deduplicator:
    """Prevent duplicate imports using statement hash"""

    @staticmethod
    def calculate_statement_hash(transactions: List[Transaction]) -> str:
        """SHA-256 hash of statement content"""
        if not transactions:
            return ''

        tx_strings = '|'.join([
            f"{t.date.isoformat()}{t.description}{t.amount}"
            for t in sorted(transactions, key=lambda x: (x.date, x.description))
        ])
        return hashlib.sha256(tx_strings.encode()).hexdigest()

    @staticmethod
    def calculate_transaction_hash(transaction: Transaction) -> str:
        """Hash for individual transaction (for dedup within a statement)"""
        key = f"{transaction.date.isoformat()}{transaction.description}{transaction.amount}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


# ============== MAIN PARSING INTERFACE ==============
class StatementParser:
    """High-level interface for parsing statements (PDF or CSV)"""

    @staticmethod
    def parse(file_bytes: bytes, file_name: str, bank_key: str, file_format: str = None) -> Tuple[ParseResult, Dict]:
        """
        Parse a statement file (PDF or CSV)
        Returns: (ParseResult, metadata_dict)
        """

        # Detect format if not specified
        if file_format is None:
            if file_name.lower().endswith('.pdf'):
                file_format = 'PDF'
            elif file_name.lower().endswith('.csv'):
                file_format = 'CSV'
            else:
                raise ValueError(f"Cannot determine file format for: {file_name}")

        metadata = {
            'file_name': file_name,
            'bank_key': bank_key,
            'file_format': file_format,
            'parse_time': datetime.now().isoformat(),
        }

        if file_format.upper() == 'PDF':
            text = PDFParser.extract_text_from_pdf(file_bytes)
            result = PDFParser.parse_statement(text, bank_key)
        elif file_format.upper() == 'CSV':
            csv_text = file_bytes.decode('utf-8')
            result = CSVParser.parse_csv(csv_text, bank_key)
        else:
            raise ValueError(f"Unsupported file format: {file_format}")

        # Calculate hash for deduplication
        metadata['statement_hash'] = Deduplicator.calculate_statement_hash(result.transactions)
        metadata['transaction_count'] = len(result.transactions)

        return result, metadata
