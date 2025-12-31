# Railway Deployment Guide - Akasha AI Mini App

**Status**: Ready for deployment
**Branch**: `feature/railway-nas-hybrid-deployment`
**Strategy**: Fast-track to public launch, database migration to NAS post-launch

---

## Overview

This guide deploys the Akasha AI Telegram Mini App to Railway with the following architecture:

```
Railway.app (FastAPI Backend + React Frontend)
    ↓
Current Host Databases (temporary, will migrate to NAS)
    └── MAG-LIB: magick_knowledge (6,377 docs, 534k chunks)
    └── BIBLIOTHEK: bibliothek_knowledge (2,701 docs, 1.8M chunks)
```

**Timeline:**
- **Phase 1 (NOW)**: Deploy to Railway pointing to current databases
- **Phase 2 (Post-launch)**: Migrate databases to NAS PostgreSQL

---

## Prerequisites

- ✅ GitHub account (linked to Railway - already done)
- ✅ OpenAI API key (configured: `sk-ikHVclNWz1q3amvp...`)
- ✅ Telegram bot credentials (DoclingKB_bot, token: `7969287253:AAEk...`)
- ✅ Docker image ready (Dockerfile in root)
- ✅ Railway project ready (you created it via dashboard)

---

## Step 1: Push Branch to GitHub

This enables Railway to auto-detect and deploy:

```bash
git push origin feature/railway-nas-hybrid-deployment
```

---

## Step 2: Configure Railway Project

**Via Railway Dashboard:**

1. **Go to**: Your Railway Project → Settings → Integrations
2. **Connect GitHub** (if not already connected):
   - Select repository: `DOCLING`
   - Select branch: `feature/railway-nas-hybrid-deployment`
   - Click "Deploy"

Railway will:
- Detect Dockerfile automatically
- Build the image
- Deploy to production

---

## Step 3: Set Environment Variables

**Via Railway Dashboard → Variables:**

Add these variables (copy from `.env.railway`):

```env
MAGLIB_HOST=127.0.0.1
MAGLIB_PORT=5432
MAGLIB_USER=docling
MAGLIB_PASSWORD=docling_secure_pwd_2024
MAGLIB_DATABASE=magick_knowledge

BIBLIOTHEK_HOST=127.0.0.1
BIBLIOTHEK_PORT=5433
BIBLIOTHEK_USER=docling
BIBLIOTHEK_PASSWORD=docling_secure_pwd_2024
BIBLIOTHEK_DATABASE=bibliothek_knowledge

OPENAI_API_KEY=sk-[REDACTED]
OPENAI_MODEL=gpt-4-mini

TELEGRAM_BOT_TOKEN=[REDACTED]
TELEGRAM_BOT_USERNAME=DoclingKB_bot

PRIVATE_MODE=false
AUTH_REQUIRED=true
MODE=saas
PORT=8200
ENVIRONMENT=production
```

---

## Step 4: Monitor Deployment

**Via Railway Dashboard:**

1. **Go to**: Deployments
2. **Watch**: Build logs in real-time
3. **Expected timeline**:
   - Build: 5-10 minutes (depends on layer caching)
   - Deployment: 1-2 minutes
   - Health check: 30 seconds

**Check Status:**
- Green checkmark ✅ = Healthy and live
- Red X ❌ = Check logs for errors

---

## Step 5: Access Your App

Once deployed, Railway provides:

```
URL: https://your-project-name.railway.app
```

Test the endpoints:

```bash
curl https://your-project-name.railway.app/health
# Should return: {"status": "healthy"}

curl https://your-project-name.railway.app/api/telegram/documents \
  -H "X-Telegram-Init-Data: ..."
```

---

## Troubleshooting

### Build Fails

**Check**: Logs in Railway dashboard
- Missing build dependency? Check Dockerfile
- GitHub branch mismatch? Verify `feature/railway-nas-hybrid-deployment` exists

### Connection to Database Fails

**Current setup**: Databases are on current host (127.0.0.1)
- Railway needs **network access** to reach your host from the internet
- **Solution**: Your current host must be accessible from Railway's servers

**If connection fails:**
1. Check firewall allows port 5432 and 5433 from outside
2. Verify PostgreSQL is listening on `0.0.0.0` not just `127.0.0.1`

```bash
# Check PostgreSQL binding
sudo pg_isready -h 0.0.0.0 -p 5432
```

### Health Check Times Out

**Likely cause**: App startup takes >10 seconds
- Increase timeout in `railway.json`

```json
"healthCheck": {
  "httpPath": "/health",
  "timeoutSeconds": 30,  // Increased from 10
  "intervalSeconds": 30,
  "successThreshold": 1,
  "failureThreshold": 3
}
```

---

## Post-Launch: Database Migration to NAS

Once the app is stable on Railway:

### 1. Set Up PostgreSQL on NAS

```bash
# On NAS - Docker container or native install
docker run -d \
  --name postgres-maglib \
  -e POSTGRES_USER=docling \
  -e POSTGRES_PASSWORD=docling_secure_pwd_2024 \
  -e POSTGRES_DB=magick_knowledge \
  -p 5432:5432 \
  -v /mnt/nvme/pgdata:/var/lib/postgresql/data \
  postgres:16-alpine
```

### 2. Migrate Data

```bash
# Backup from current host
pg_dump -h current-host-ip -U docling magick_knowledge > /tmp/maglib.sql
pg_dump -h current-host-ip -p 5433 -U docling bibliothek_knowledge > /tmp/bibliothek.sql

# Restore to NAS PostgreSQL
psql -h 192.168.1.117 -U docling magick_knowledge < /tmp/maglib.sql
psql -h 192.168.1.117 -p 5433 -U docling bibliothek_knowledge < /tmp/bibliothek.sql
```

### 3. Update Railway Variables

```env
MAGLIB_HOST=192.168.1.117
MAGLIB_PORT=5432

BIBLIOTHEK_HOST=192.168.1.117
BIBLIOTHEK_PORT=5433
```

### 4. Redeploy

Railway will automatically rebuild and deploy with new variables.

---

## Current Deployment Configuration

**Files Created:**
- `Dockerfile` - Multi-stage build for FastAPI + React
- `railway.json` - Health checks and resource configuration
- `Procfile` - Startup command for Railway
- `.dockerignore` - Excludes unnecessary files from build
- `.env.railway` - Environment variables template
- `.env.example` - Documentation for local development

**Branch**: `feature/railway-nas-hybrid-deployment`

**Next Steps**:
1. ✅ Push branch to GitHub
2. ⏳ Set up Railway project with GitHub integration
3. ⏳ Add environment variables in Railway dashboard
4. ⏳ Monitor deployment
5. ⏳ Test via Railway domain
6. ⏳ Update Telegram menu button with new URL

---

## Questions?

Check the full Railway documentation in Archon KB for advanced configuration options.
