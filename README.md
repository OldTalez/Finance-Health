# Finance Platform Backend — Phase 1

**Status:** Development in progress (Weeks 1–3)  
**Tech Stack:** Django 4.2 + Django REST Framework + PostgreSQL  
**Deadline:** 2026-10-24

## Project Structure

```
finance-platform-api/
├── manage.py                 # Django CLI entry point
├── requirements.txt          # Python dependencies
├── pytest.ini               # Pytest configuration
├── .env.example             # Environment variables template
├── src/
│   ├── __init__.py
│   ├── settings.py          # Django settings (DB, auth, middleware, installed apps)
│   ├── urls.py              # Root URL router
│   ├── wsgi.py              # WSGI app for production
│   ├── asgi.py              # ASGI app for async/WebSocket (future)
│   ├── apps/
│   │   ├── auth/            # User authentication
│   │   │   ├── models.py    # User model
│   │   │   ├── views.py     # Login, register, token refresh
│   │   │   ├── serializers.py
│   │   │   ├── urls.py
│   │   │   └── tests.py
│   │   ├── accounts/        # User's bank accounts
│   │   │   ├── models.py    # Account, Statement models
│   │   │   ├── views.py     # Account CRUD, listing
│   │   │   ├── serializers.py
│   │   │   ├── urls.py
│   │   │   └── tests.py
│   │   ├── transactions/    # Transaction data & queries
│   │   │   ├── models.py    # Transaction, Category, Rule models
│   │   │   ├── views.py     # Transaction GET/PATCH/DELETE, filtering
│   │   │   ├── serializers.py
│   │   │   ├── urls.py
│   │   │   └── tests.py
│   │   ├── import/          # PDF/CSV parsing & import
│   │   │   ├── parsers.py   # PDF & CSV parsing engines
│   │   │   ├── views.py     # /api/upload, file processing
│   │   │   ├── serializers.py
│   │   │   ├── urls.py
│   │   │   ├── deduplicator.py  # Statement deduplication logic
│   │   │   └── tests.py
│   │   ├── categories/      # Categorization & rules
│   │   │   ├── models.py    # Category, Rule models (shared with transactions/)
│   │   │   ├── views.py     # Rules CRUD, category listing
│   │   │   ├── categorizer.py   # Rule application engine
│   │   │   ├── urls.py
│   │   │   └── tests.py
│   │   ├── analytics/       # Dashboard, metrics, recurring detection
│   │   │   ├── views.py     # /api/dashboard, /api/analytics
│   │   │   ├── algorithms.py    # Net worth, money-left-month, outlier detection
│   │   │   ├── serializers.py
│   │   │   ├── urls.py
│   │   │   └── tests.py
│   │   └── audit/           # Audit logging
│   │       ├── models.py    # AuditLog model
│   │       ├── middleware.py    # Request logging middleware
│   │       └── views.py     # Audit log retrieval (admin only)
│   ├── middleware.py        # Auth, rate limiting, CORS
│   ├── utils/
│   │   ├── crypto.py        # AES-256-GCM encryption for sensitive fields
│   │   ├── jwt_utils.py     # JWT token generation/validation
│   │   ├── decorators.py    # @require_auth, @rate_limit
│   │   └── validators.py    # Email, password validators
│   └── tests/
│       ├── conftest.py      # Pytest fixtures
│       └── test_integration.py  # End-to-end tests
└── docs/
    ├── API_SPEC.md          # Swagger/OpenAPI spec (human-readable)
    ├── SETUP.md             # Installation & local dev setup
    ├── DEPLOYMENT.md        # Railway/Render deployment guide
    └── SECURITY.md          # Encryption, auth, PCI-DSS notes
```

## Quick Start

### 1. Clone & Install

```bash
git clone <repo-url>
cd finance-platform-api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and update:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/finance_db
SECRET_KEY=your-django-secret-key-here
DEBUG=True  # False in production
ALLOWED_HOSTS=localhost,127.0.0.1
JWT_SECRET=your-jwt-secret-key
JWT_EXPIRY_MINUTES=15
REFRESH_TOKEN_DAYS=7
```

### 3. Database Setup

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Run Locally

```bash
python manage.py runserver
# Server runs at http://localhost:8000
# API docs at http://localhost:8000/api/docs/
```

## API Endpoints (Phase 1)

### Authentication

- `POST /api/auth/register` — Create user account
- `POST /api/auth/login` — Get JWT token
- `POST /api/auth/refresh` — Refresh expired token
- `POST /api/auth/logout` — Revoke tokens (optional)
- `GET /api/auth/me` — Get current user profile

### Accounts

- `GET /api/accounts` — List user's accounts
- `POST /api/accounts` — Add new account (manual entry)
- `GET /api/accounts/{id}` — Account details
- `PATCH /api/accounts/{id}` — Update account name/metadata
- `DELETE /api/accounts/{id}` — Remove account

### Upload & Import

- `POST /api/upload` — Upload PDF/CSV statement
  - Request: multipart form (file, bank_key, account_id)
  - Response: { status, rows_processed, rows_imported, rows_deduplicated, errors }
- `GET /api/upload/history` — Import history
- `GET /api/upload/status/{task_id}` — Async import status

### Transactions

- `GET /api/transactions` — List transactions (with filters)
  - Query params: `account_id`, `category_id`, `date_from`, `date_to`, `search`, `is_recurring`, `page`, `limit`
- `PATCH /api/transactions/{id}` — Edit transaction (category, notes, flag)
- `DELETE /api/transactions/{id}` — Delete transaction
- `GET /api/transactions/export` — Export as CSV

### Categorization

- `GET /api/categories` — List categories
- `GET /api/rules` — List categorization rules
- `POST /api/rules` — Create rule
- `PATCH /api/rules/{id}` — Update rule
- `DELETE /api/rules/{id}` — Delete rule

### Dashboard & Analytics

- `GET /api/dashboard` — Main dashboard metrics
  - Returns: { money_left_this_month, net_worth, account_balances, category_breakdown, upcoming_payments }
- `GET /api/analytics/spending` — Spending trends (chart data)
- `GET /api/analytics/recurring` — Detected recurring charges
- `GET /api/analytics/outliers` — Flagged unusual transactions

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific app tests
pytest src/apps/auth/tests.py

# Watch mode (requires pytest-watch)
ptw
```

## Key Implementation Notes

### PDF Parsing

Porting Finance Tracker's global-pattern approach:
- Does NOT parse line-by-line (OCR can reorder lines)
- Scans entire text for "date date description amount" patterns
- Handles 5 different statement formats per Config.gs
- Deduplicates using statement hash (SHA-256) to prevent re-importing

### CSV Parsing

Handles KOHO, RBC, TD formats with column mapping per Config.gs.

### Deduplication

- Statements deduplicated by content hash (SHA-256 of entire statement)
- Transactions deduplicated by import_id (hash of date+description+amount)
- Prevents duplicate imports even if same file uploaded twice

### Financial Algorithms

Ported from Finance Tracker:
- **Net Worth** = sum(debit/savings balances) − sum(credit card balances)  
  Uses most-recent statement by **billing period end date**, not import order
- **Money Left This Month** = total income − total spending (excluding internal transfers)
- **Recurring Detection**:
  - Bills (Rent, Utilities, Insurance, etc.): recurring if ≥2 distinct months
  - Other categories: recurring if ≥3 occurrences within ±10% of median amount
- **Outlier Flagging**: IQR-based (configurable multiplier, 1.5x default)
- **Internal Transfers**: excluded from spending/recurring/outlier detection

### Security

- Passwords: bcrypt (12+ rounds)
- Account numbers: AES-256-GCM encrypted per-user
- Transactions: plaintext (user owns data; assume DB compromise)
- Auth: JWT with 15-min expiry + 7-day refresh tokens (rotated on use)
- Rate limiting: 5 failed logins → 15-min lockout
- Audit log: all sensitive field access

### Deployment

Target: **Railway** or **Render** (free tier)
- PostgreSQL: 5GB free
- Python runtime: included
- Environment variables: stored securely
- See `DEPLOYMENT.md` for step-by-step

## Current Status

- [x] Schema design & migration files
- [x] Django project skeleton
- [x] models.py (all tables)
- [ ] Serializers (in progress)
- [ ] Views & endpoints (in progress)
- [ ] PDF/CSV parsers (in progress)
- [ ] Auth & JWT (in progress)
- [ ] Rate limiting (in progress)
- [ ] Tests (in progress)
- [ ] Swagger/OpenAPI spec (in progress)
- [ ] Deployment setup (in progress)

## Questions for Ledger

- Confirm financial algorithms match Design Director's expectations
- Verify encryption/security spec before finalization
- Review test vectors for edge cases

---

**Next:** Implement authentication endpoints, transaction CRUD, and file upload flow.
