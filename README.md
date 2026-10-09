# Finance Health — Backend

Private personal-finance API: budgeting, forecasting and investing tools, built so a small group of invited members can each see only their own data.

**Status:** Django backend only. The Next.js frontend is planned but does not exist yet.
**Stack:** Django 5.2, Django REST Framework, PostgreSQL (Railway), SQLite for tests.

## Branches and deploys

| Branch | Deploys to | Rules |
|---|---|---|
| `staging` | Railway staging | Work lands here first (via PR). |
| `main` | Railway production | Protected. Pull request only, from `staging`. |

CI (`.github/workflows/ci.yml`, on `staging`) runs the tests on SQLite, applies the migrations to a real PostgreSQL 16, and runs a report-only `pip audit`.

## What is in the repo

```
manage.py, settings.py, urls.py, wsgi.py   Django project (flat layout, no src/ folder)
finance_app/                               the one app: models, views, serializers,
                                           parsers.py (PDF/CSV), upload_views.py, utils.py
test_api.py, conftest.py, test_settings.py tests (pytest, SQLite)
railway.toml                               how Railway builds and starts the app
schema.sql                                 reference schema (Django migrations are the source of truth)
.env.example                               environment variable template
```

Other documents: [API-SPEC.md](API-SPEC.md), [DEPLOYMENT.md](DEPLOYMENT.md), [FINANCIAL-DEFINITIONS.md](FINANCIAL-DEFINITIONS.md), [PHASE-1-STATUS.md](PHASE-1-STATUS.md), [IMPLEMENTATION-PROGRESS.md](IMPLEMENTATION-PROGRESS.md).

## Run it locally

```bash
git clone <repo-url> && cd Finance-Health
python -m venv venv
source venv/bin/activate        # Windows PowerShell: venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env            # then edit it (see below)
python manage.py migrate
python manage.py runserver      # http://localhost:8000
```

Swagger UI is at `/api/docs/`, the schema at `/api/schema/`, and a health check at `/health/`.

For local work, set in `.env`: `DEBUG=True`, `SECRET_KEY` to any random string, and either `DATABASE_URL` or the `DB_*` values for a local PostgreSQL. The `.env.example` defaults are production-style (`DEBUG=False`, secure cookies, SSL redirect), so change them for localhost or login cookies and redirects will misbehave. Never commit `.env`, and never put real keys, emails or account details in `.env.example`.

## Tests

```bash
pip install -r requirements-test.txt
python -m pytest -q
```

Tests run on SQLite with `--nomigrations`, so they do not exercise the migrations. CI covers that on PostgreSQL.

## Deploying (Railway)

Railway builds with nixpacks and starts the app using `startCommand` in `railway.toml` (collectstatic, migrate, then gunicorn). That file is what Railway uses; the `Procfile` is not what drives deploys here. Environment variables are set in the Railway dashboard, never in the repo. Click-by-click steps are in [DEPLOYMENT.md](DEPLOYMENT.md).

Production settings to check in Railway: `DEBUG=False`, a strong `SECRET_KEY`, `JWT_SECRET` and `ENCRYPTION_KEY`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` set to `True`, and `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` limited to your own domains. Never use "Add Public Access" on the PostgreSQL service.

## API (all under `/api/v1/`)

- Auth: `POST auth/register/`, `auth/login/`, `auth/refresh/`; `GET auth/me/`
- Resources: `accounts/`, `transactions/` (plus `transactions/export/`), `categories/`, `rules/` (standard list/create/detail/update/delete)
- Import: `POST import/upload/` (multipart: file, bank_key, account_id), `GET import/history/`, `GET import/status/<task_id>/`
- Dashboard: `GET analytics/dashboard/`

[API-SPEC.md](API-SPEC.md) and `/api/docs/` are the detailed references. Planned but not built: logout, and the `analytics/spending`, `recurring` and `outliers` endpoints.

## How it works

- **Imports:** PDF statements are matched by scanning the whole text for "date, date, description, amount" patterns (OCR can reorder lines); CSV uses per-bank column mappings. Statements are de-duplicated by SHA-256 hash and transactions by a hash of date, description and amount.
- **Money rules** (net worth, money left this month, recurring and outlier detection, internal transfers) are defined in [FINANCIAL-DEFINITIONS.md](FINANCIAL-DEFINITIONS.md). Nothing here is personalised investment advice.

## Security: current state

Be honest about what exists today:

- Each member only sees their own rows (per-user filtering on every query set).
- Passwords use Django's default hasher, not bcrypt. Access tokens last 15 minutes; refresh tokens last 7 days and rotate on use.
- Field-level encryption of account numbers is **not implemented yet**: `EncryptionUtils` in `finance_app/utils.py` returns the text unchanged.
- The "5 failed logins, 15-minute lockout" rate (`auth_failed`) is defined in `settings.py` but nothing enforces it yet.
- `POST auth/register/` is currently open to anyone. The plan is invite-only sign-up through a `create_invite` management command, which is not in the code yet.

These gaps are tracked in the security review and in the next hardening batch.

## Not in this README on purpose

Real emails, passwords, keys, account numbers, balances and pay figures live only in Railway variables and private notes.
