# Finance Platform API Specification — Phase 1

**Version:** 1.0.0  
**Base URL:** `http://localhost:8000/api/v1` (local) | `https://api.finance-platform.com` (production)  
**Authentication:** JWT Bearer token in `Authorization` header  
**Content-Type:** `application/json`  
**Status:** In development

---

## Authentication Endpoints

### POST /auth/register

Create a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "full_name": "Kennedy"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "Kennedy",
  "is_email_verified": false,
  "created_at": "2026-10-03T12:00:00Z"
}
```

**Errors:**
- 400: Email already exists, password too weak, missing fields
- 422: Invalid email format

---

### POST /auth/login

Authenticate and get JWT tokens.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "expires_in": 900,
  "token_type": "Bearer"
}
```

**Rate Limiting:** 5 failed attempts = 15-min lockout  
**Errors:**
- 401: Invalid credentials
- 429: Too many login attempts

---

### POST /auth/refresh

Refresh expired access token using refresh token.

**Request:**
```json
{
  "refresh_token": "eyJhbGc..."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "expires_in": 900
}
```

**Errors:**
- 401: Refresh token invalid or expired

---

### POST /auth/logout

Revoke refresh tokens (optional, for security).

**Request:**
```json
{
  "refresh_token": "eyJhbGc..."
}
```

**Response (204 No Content)**

---

### GET /auth/me

Get current user profile.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "Kennedy",
  "is_email_verified": true,
  "created_at": "2026-10-03T12:00:00Z"
}
```

---

## Account Management Endpoints

### GET /accounts

List all user's accounts.

**Query Parameters:**
- `is_active` (bool): Filter by active status

**Response (200 OK):**
```json
{
  "count": 8,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "PC Financial Mastercard",
      "bank_key": "PCFinancial-Mastercard",
      "account_type": "credit",
      "currency": "CAD",
      "latest_balance": -500.00,
      "latest_statement_date": "2026-09-30",
      "is_active": true,
      "created_at": "2026-10-03T12:00:00Z"
    }
  ]
}
```

---

### POST /accounts

Add a new account (manual entry).

**Request:**
```json
{
  "name": "TD Chequing",
  "bank_key": "TD-Chequing",
  "account_type": "debit",
  "currency": "CAD"
}
```

**Response (201 Created):**
```json
{
  "id": 2,
  "name": "TD Chequing",
  "bank_key": "TD-Chequing",
  "account_type": "debit",
  "currency": "CAD",
  "latest_balance": null,
  "latest_statement_date": null,
  "is_active": true,
  "created_at": "2026-10-03T12:00:00Z"
}
```

---

### GET /accounts/{id}

Get account details.

**Response (200 OK):**
```json
{
  "id": 1,
  "name": "PC Financial Mastercard",
  "bank_key": "PCFinancial-Mastercard",
  "account_type": "credit",
  "currency": "CAD",
  "latest_balance": -500.00,
  "latest_statement_date": "2026-09-30",
  "transaction_count": 215,
  "is_active": true,
  "created_at": "2026-10-03T12:00:00Z"
}
```

---

### PATCH /accounts/{id}

Update account (name, active status).

**Request:**
```json
{
  "name": "PC Mastercard (Updated)",
  "is_active": true
}
```

**Response (200 OK):** Updated account object

---

### DELETE /accounts/{id}

Remove account (soft delete via is_active=false).

**Response (204 No Content)**

---

## Transaction Endpoints

### GET /transactions

List transactions with filtering & pagination.

**Query Parameters:**
- `account_id` (int): Filter by account
- `category_id` (int): Filter by category
- `date_from` (YYYY-MM-DD): Date range start
- `date_to` (YYYY-MM-DD): Date range end
- `search` (str): Search in description
- `is_recurring` (bool): Filter recurring only
- `flag` (str): Filter by flag (outlier, large_purchase, etc)
- `page` (int): Page number (default: 1)
- `page_size` (int): Items per page (default: 50)

**Response (200 OK):**
```json
{
  "count": 403,
  "next": "http://localhost:8000/api/v1/transactions/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1001,
      "date": "2026-09-30",
      "description": "NETFLIX MONTHLY CHARGE",
      "amount": -24.99,
      "account_id": 1,
      "category_id": 5,
      "category_name": "Subscriptions",
      "source": "PDF",
      "is_recurring": true,
      "recurring_cadence": "Monthly",
      "flag": null,
      "notes": "",
      "created_at": "2026-10-02T15:30:00Z"
    }
  ]
}
```

---

### PATCH /transactions/{id}

Update transaction (category, notes, flag).

**Request:**
```json
{
  "category_id": 5,
  "notes": "Netflix subscription",
  "flag": null
}
```

**Response (200 OK):** Updated transaction object

---

### DELETE /transactions/{id}

Delete transaction.

**Response (204 No Content)**

---

### GET /transactions/export

Export transactions as CSV.

**Query Parameters:** Same as `/transactions` GET  
**Response:** CSV file download

---

## File Upload & Import Endpoints

### POST /import/upload

Upload a PDF or CSV statement.

**Request (multipart/form-data):**
```
file: <binary PDF or CSV>
bank_key: "PCFinancial-Mastercard"
account_id: 1 (optional, auto-detect if not provided)
```

**Response (202 Accepted):**
```json
{
  "import_task_id": "imp_abc123xyz",
  "status": "processing",
  "file_name": "PC_Financial_Mastercard_2026-09.pdf",
  "rows_processed": 0,
  "rows_imported": 0,
  "rows_deduplicated": 0,
  "errors": [],
  "created_at": "2026-10-03T12:00:00Z"
}
```

**Async Behavior:** Returns immediately; client polls `/import/status/{task_id}` for completion.

---

### GET /import/status/{task_id}

Check async import progress.

**Response (200 OK):**
```json
{
  "import_task_id": "imp_abc123xyz",
  "status": "completed",
  "file_name": "PC_Financial_Mastercard_2026-09.pdf",
  "rows_processed": 42,
  "rows_imported": 40,
  "rows_deduplicated": 2,
  "errors": [],
  "completed_at": "2026-10-03T12:05:00Z"
}
```

**Status values:** `processing`, `completed`, `failed`, `partial`

---

### GET /import/history

List past imports.

**Query Parameters:**
- `page` (int): Page number
- `page_size` (int): Items per page

**Response (200 OK):**
```json
{
  "count": 12,
  "results": [
    {
      "import_log_id": 1,
      "file_name": "PC_Financial_Mastercard_2026-09.pdf",
      "bank_key": "PCFinancial-Mastercard",
      "rows_processed": 42,
      "rows_imported": 40,
      "rows_deduplicated": 2,
      "import_status": "success",
      "imported_at": "2026-10-03T12:05:00Z"
    }
  ]
}
```

---

## Categorization Endpoints

### GET /categories

List all categories.

**Response (200 OK):**
```json
{
  "results": [
    {
      "id": 1,
      "name": "Food Delivery",
      "is_internal": false,
      "color": "#d97757",
      "icon": "pizza",
      "rule_count": 2
    }
  ]
}
```

---

### GET /categories?is_internal=true

List only internal transfer categories.

---

### POST /categories

Create a custom category.

**Request:**
```json
{
  "name": "Pet Care",
  "color": "#788c5d",
  "icon": "paw",
  "is_internal": false
}
```

**Response (201 Created):** Category object

---

### GET /rules

List categorization rules.

**Response (200 OK):**
```json
{
  "results": [
    {
      "id": 1,
      "category_id": 5,
      "category_name": "Subscriptions",
      "pattern": "netflix|spotify|disney\\+|crave",
      "pattern_type": "regex",
      "priority": 100,
      "is_active": true,
      "created_at": "2026-10-03T12:00:00Z"
    }
  ]
}
```

---

### POST /rules

Create a new categorization rule.

**Request:**
```json
{
  "category_id": 5,
  "pattern": "hbo|max|apple tv",
  "pattern_type": "regex",
  "priority": 95,
  "is_active": true
}
```

**Response (201 Created):** Rule object

---

### PATCH /rules/{id}

Update rule.

**Request:**
```json
{
  "priority": 90,
  "is_active": false
}
```

**Response (200 OK):** Updated rule object

---

### DELETE /rules/{id}

Delete rule.

**Response (204 No Content)**

---

## Dashboard & Analytics Endpoints

### GET /analytics/dashboard

Main dashboard with key metrics.

**Response (200 OK):**
```json
{
  "money_left_this_month": {
    "value": 2145.67,
    "currency": "CAD",
    "period": "September 2026"
  },
  "net_worth": {
    "value": 15234.50,
    "currency": "CAD",
    "breakdown": {
      "debit_savings": 8500.00,
      "credit_card_debt": -6765.50
    }
  },
  "account_balances": [
    {
      "account_id": 1,
      "name": "PC Financial Mastercard",
      "balance": -500.00,
      "as_of_date": "2026-09-30"
    }
  ],
  "spending_by_category": [
    {
      "category_id": 5,
      "category_name": "Subscriptions",
      "total": -49.98,
      "percentage": 2.3
    }
  ],
  "upcoming_payments": [
    {
      "category_name": "Rent",
      "amount": -1200.00,
      "expected_date": "2026-10-05",
      "recurring_cadence": "Monthly"
    }
  ]
}
```

---

### GET /analytics/spending

Spending trends chart data.

**Query Parameters:**
- `period` (str): "week", "month", "quarter", "year" (default: "month")
- `date_from`, `date_to`: Date range

**Response (200 OK):**
```json
{
  "period": "month",
  "data": [
    {"date": "2026-09-01", "amount": -450.00},
    {"date": "2026-09-02", "amount": -75.50},
    {"date": "2026-09-03", "amount": -1200.00}
  ],
  "total": -5234.50,
  "average_per_day": -174.48
}
```

---

### GET /analytics/recurring

Detected recurring charges.

**Response (200 OK):**
```json
{
  "results": [
    {
      "id": 1,
      "category_name": "Subscriptions",
      "merchant": "Netflix",
      "amount": -24.99,
      "cadence": "Monthly",
      "occurrences": 4,
      "last_occurrence": "2026-09-30",
      "next_expected_date": "2026-10-30",
      "is_active": true
    }
  ]
}
```

---

### GET /analytics/outliers

Flagged unusual transactions.

**Response (200 OK):**
```json
{
  "results": [
    {
      "id": 1005,
      "date": "2026-09-15",
      "description": "AMAZON PURCHASE",
      "amount": -850.00,
      "category_name": "Shopping",
      "flag": "outlier",
      "reason": "3.2x median for category",
      "similar_transaction_median": 265.00
    }
  ]
}
```

---

## Error Responses

All errors follow this format:

**400 Bad Request:**
```json
{
  "errors": [
    {
      "field": "password",
      "message": "Password must be at least 12 characters"
    }
  ]
}
```

**401 Unauthorized:**
```json
{
  "detail": "Invalid or missing authentication token"
}
```

**404 Not Found:**
```json
{
  "detail": "Transaction not found"
}
```

**429 Too Many Requests:**
```json
{
  "detail": "Rate limit exceeded. Try again in 15 minutes."
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Internal server error. Please try again later."
}
```

---

## Rate Limiting

- **Anonymous:** 100 requests/hour
- **Authenticated:** 1000 requests/hour
- **Auth endpoints:** 5 failed logins = 15-min lockout

---

## Pagination

All list endpoints return paginated responses:

```json
{
  "count": 403,
  "next": "http://localhost:8000/api/v1/endpoint/?page=2",
  "previous": null,
  "results": [...]
}
```

**Default:** 50 items per page. Override with `?page_size=100`

---

## Testing the API

### Using cURL

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123!","full_name":"Kennedy"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123!"}'

# Get current user (replace TOKEN with access_token)
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/v1/auth/me

# List accounts
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/v1/accounts/
```

### Using Swagger UI

Visit `http://localhost:8000/api/docs/` (after server starts)

---

## Implementation Priority

1. ✅ Auth endpoints (register, login, token refresh)
2. ✅ Account CRUD endpoints
3. ✅ Transaction listing & filtering
4. ✅ File upload & import
5. ✅ Categories & rules CRUD
6. Dashboard API (in progress)
7. Analytics (spending, recurring, outliers)
8. Export endpoints

---

**API Documentation:** Last updated 2026-10-03
