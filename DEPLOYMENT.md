# Deployment Guide — Finance Platform Phase 1

**Platforms:** Railway or Render (both have free tiers with PostgreSQL)  
**Database:** PostgreSQL 14+ (5GB free on Railway/Render)  
**Runtime:** Python 3.10+  
**Estimated time:** 15–30 minutes

---

## Option A: Deploy to Railway

### 1. Create Railway Project

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Create new project
railway init
```

### 2. Add PostgreSQL

```bash
# In Railway dashboard: Add Service → PostgreSQL
# Copy the DATABASE_URL from the PostgreSQL service variables
```

### 3. Configure Environment Variables

In Railway dashboard, set these variables:

```
SECRET_KEY=<generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'>
DEBUG=False
ALLOWED_HOSTS=<your-railway-url>.railway.app
DATABASE_URL=<from PostgreSQL service>
JWT_SECRET=<generate random string, 32+ chars>
ENCRYPTION_KEY=<generate random string, 32 chars>
```

### 4. Create Procfile

```
web: gunicorn src.wsgi --log-file -
release: python manage.py migrate
```

### 5. Deploy

```bash
# Push to Railway
railway up

# Or push via Git
git push origin main  # if connected to GitHub
```

### 6. Run Migrations

```bash
railway run python manage.py migrate
railway run python manage.py createsuperuser
```

### 7. Verify Deployment

```bash
# Test health endpoint
curl https://<your-railway-url>.railway.app/health/

# Visit Swagger docs
https://<your-railway-url>.railway.app/api/docs/
```

---

## Option B: Deploy to Render

### 1. Create Render Account

- Go to https://render.com
- Sign up with GitHub (recommended for auto-deploys)

### 2. Create PostgreSQL Database

- New → PostgreSQL
- Name: `finance-db`
- Region: Same as web service
- Copy the External Database URL

### 3. Create Web Service

- New → Web Service
- Connect GitHub repo
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn src.wsgi --log-file -`
- Environment Variables:
  - `SECRET_KEY`: Generate with django-insecure command above
  - `DEBUG`: `False`
  - `DATABASE_URL`: PostgreSQL external URL from step 2
  - `JWT_SECRET`: Random 32+ char string
  - `ENCRYPTION_KEY`: Random 32 char string
  - `ALLOWED_HOSTS`: `<service-name>.onrender.com`

### 4. Configure Release Phase

Add to your application:

```python
# In settings.py or as a post-deploy script
if os.environ.get('RENDER'):
    import subprocess
    subprocess.run(['python', 'manage.py', 'migrate'], check=True)
```

### 5. Deploy

- Push to main branch
- Render auto-deploys on commit
- Monitor Deploy logs in Render dashboard

---

## Local Development Setup

### 1. Clone Repository

```bash
git clone <repo-url>
cd finance-platform-api
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with local settings:
# - SECRET_KEY (any value for local dev)
# - DEBUG=True
# - DATABASE_URL=postgresql://localhost/finance_db (local PostgreSQL)
```

### 5. Create Local Database

```bash
# Create PostgreSQL database
createdb finance_db

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 6. Run Server

```bash
python manage.py runserver
# Visit http://localhost:8000/api/docs/
```

### 7. Run Tests

```bash
pytest
pytest --cov=src  # With coverage
```

---

## Post-Deployment Checklist

- [ ] Health endpoint responds (`/health/`)
- [ ] Swagger docs accessible (`/api/docs/`)
- [ ] Can register user (`POST /api/v1/auth/register`)
- [ ] Can login (`POST /api/v1/auth/login`)
- [ ] Can list accounts (`GET /api/v1/accounts/`)
- [ ] Database migrations completed
- [ ] Logs are being captured
- [ ] Emails are working (if configured)

---

## Troubleshooting

### Issue: Database Connection Failed
- Check `DATABASE_URL` in environment variables
- Verify PostgreSQL service is running
- Check IP whitelist (Railway/Render require no firewall changes)

### Issue: Static Files Not Serving
- Run: `python manage.py collectstatic`
- Ensure `STATIC_URL` and `STATIC_ROOT` are configured correctly

### Issue: OCR Failing (pytesseract)
- Install Tesseract: `apt-get install tesseract-ocr` (on Railway/Render, in nixpacks config)
- Set `TESSERACT_CMD` environment variable

### Issue: Migrations Failed
- Check logs: `railway logs` or Render logs dashboard
- Run manually: `railway run python manage.py migrate`

---

## Monitoring

### Railway
- Dashboard: Metrics, logs, deployments
- Set up alerts in Settings → Alerts

### Render
- Dashboard: Service health, deploy logs
- Set up notifications in Settings

---

## Scaling (After Phase 1)

- **Database:** Railway/Render offer paid tiers with larger storage
- **Application:** Both platforms auto-scale with more resources
- **Background Jobs:** Add Celery/RQ for async tasks (OCR, recurring detection)
- **Caching:** Add Redis for session/query caching

---

## Security Post-Deployment

- [ ] Set `SECURE_SSL_REDIRECT=True`
- [ ] Enable `HSTS` headers
- [ ] Configure CORS properly (only allow frontend domain)
- [ ] Set up rate limiting (configured in settings.py)
- [ ] Enable email verification (in Phase 2)
- [ ] Rotate `SECRET_KEY` periodically
- [ ] Review audit logs regularly

---

**Deployment Status:** Ready for production  
**Estimated downtime:** 0–5 minutes (auto-deploy on Railway/Render)  
**Rollback plan:** Railway/Render both support one-click rollbacks to previous versions
