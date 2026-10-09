# Finance Health — Backend

Private personal-finance API: budgeting, forecasting and investing tools, built so a small group of invited members can each see only their own data.

**Status:** Django backend only. The Next.js frontend is planned but does not exist yet.
**Stack:** Django 5.2, Django REST Framework, PostgreSQL (Railway), SQLite for tests.

## Branches and deploys

| Branch | Deploys to | Rules |
|---|---|---|
| `staging` | Railway staging | Work lands here first (via PR). |
| `main` | Railway production | Protected. Pull request only, from `staging`. |

CI (`.github/workflows/ci.yml`, on pull requests to `staging` and `main`) runs the tests on SQLite, applies the migrations to a real PostgreSQL 16, and runs `pip-audit` on the dependencies. A known-vulnerable dependency fails the audit check.

## What is in the repo

```
manage.py, settings.py, urls.py, wsgi.py   Django project (flat layout, no src/ folder)
finance_app/                               the one app: models, views, serializers,
                                           parsers.py (PDF/CSV), upload_views.py, utils.py,
                                           management/commands/create_invite.py
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
python manage.py create_invite --label "me"   # prints a one-time sign-up code
python manage.py runserver      # http://localhost:8000
```

Swagger UI is at `/api/docs/`, the schema at `/api/schema/`, and a health check at `/health/`.

`SECRET_KEY`, `JWT_SECRET` and `ENCRYPTION_KEY` have no defaults: the app refuses to start without them. Make each one different (and `ENCRYPTION_KEY` at least 32 characters). Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

The safe settings are the default when a variable is unset (`DEBUG` off, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` on). For local work only, put `DEBUG=True` and those three flags as `False` in your own `.env`, plus either `DATABASE_URL` or the `DB_*` values for a local PostgreSQL. Never commit `.env`, and never put real keys, emails or account details in `.env.example`.

## Tests

```bash
pip install -r requirements-test.txt
python -m pytest -q
```

Tests run on SQLite with `--nomigrations` and use their own fake keys (`test_settings.py`), so they neither need your `.env` nor exercise the migrations. CI covers the migrations on PostgreSQL.

## Deploying (Railway)

Railway builds with nixpacks and is configured by `railway.toml`: `collectstatic` runs at build, `migrate` runs as a pre-deploy step (if it fails, the deploy stops and the old version keeps running), then gunicorn starts. `railway.toml` is what Railway follows; the `Procfile` is left over and is not what drives deploys here. Environment variables are set in the Railway dashboard, never in the repo. Click-by-click steps are in [DEPLOYMENT.md](DEPLOYMENT.md).

Production variables to check in Railway: `SECRET_KEY`, `JWT_SECRET` and `ENCRYPTION_KEY` (all set, all different), `DEBUG=False`, `NUM_PROXIES=1`, the three secure flags `True`, and `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` limited to your own domains. Never use "Add Public Access" on the PostgreSQL service. Losing `ENCRYPTION_KEY` makes encrypted account numbers unreadable, so keep a copy somewhere private.

### Inviting a member

Sign-up needs a single-use code. Create one with `python manage.py create_invite --label "name" --days 7` (in Railway, run it from the service's shell or `railway run`). The code is printed once and only its hash is stored. The member sends it as `invite_code` in `POST /api/v1/auth/register/`.

## API (all under `/api/v1/`)

- Auth: `POST auth/register/` (needs `invite_code`), `auth/login/`, `auth/refresh/`, `auth/logout/`; `GET auth/me/`
- Resources: `accounts/`, `transactions/` (plus `transactions/export/`), `categories/`, `rules/` (standard list/create/detail/update/delete)
- Import: `POST import/upload/` (multipart: file, bank_key, account_id), `GET import/history/`, `GET import/status/<task_id>/`
- Dashboard: `GET analytics/dashboard/`

[API-SPEC.md](API-SPEC.md) and `/api/docs/` are the detailed references. Planned but not built: the `analytics/spending`, `recurring` and `outliers` endpoints.

## How it works

- **Imports:** PDF statements are matched by scanning the whole text for "date, date, description, amount" patterns (OCR can reorder lines); CSV uses per-bank column mappings. Statements are de-duplicated by SHA-256 hash and transactions by a hash of date, description and amount.
- **Money rules** (net worth, money left this month, recurring and outlier detection, internal transfers) are defined in [FINANCIAL-DEFINITIONS.md](FINANCIAL-DEFINITIONS.md). Nothing here is personalised investment advice.

## Security: current state

- Each member only sees their own rows (per-user filtering on every query set, covered by `test_isolation.py`).
- Account numbers are encrypted at rest with AES-256-GCM (random nonce per value, key from `ENCRYPTION_KEY`).
- Sign-up is invite-only with single-use, expiring codes.
- Login locks out after 5 failed attempts for 15 minutes (`LOGIN_LOCKOUT_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`).
- Access tokens last 15 minutes. Refresh tokens last 7 days, are stored hashed, rotate on use, and are revoked on logout.
- Passwords use Django's default hasher (PBKDF2), not bcrypt.
- The app will not start without its three secrets, and `DEBUG`, secure cookies and SSL redirect are safe by default.

Known gaps are tracked in the security review; nothing here replaces a professional audit before real members' data goes in.

## Not in this README on purpose

Real emails, passwords, keys, account numbers, balances and pay figures live only in Railway variables and private notes.
