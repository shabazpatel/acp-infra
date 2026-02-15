# Deploy to Railway

## Quick Start (Web Dashboard)

### 1. Push to GitHub

```bash
git add .
git commit -m "Deploy config"
git push origin main
```

### 2. Railway Dashboard

Go to https://railway.app/dashboard

- New Project → Deploy from GitHub repo
- Select your repo
- Railway detects `railway.toml` automatically

### 3. Add PostgreSQL

- Click "New" → Database → PostgreSQL
- Railway sets `DATABASE_URL` automatically

### 4. Configure Services

Railway creates seller service. Add these variables:

**Seller**:
```
OPENAI_API_KEY=sk-...
DATABASE_URL=${{Postgres.DATABASE_URL}}
TEMPORAL_HOST=localhost:7233
ACP_AUTO_INGEST_ON_STARTUP=true
```

**Agent** (New → Empty Service → GitHub repo):
```
OPENAI_API_KEY=sk-...
SELLER_SERVICE_URL=http://${{seller.RAILWAY_PRIVATE_DOMAIN}}
PSP_SERVICE_URL=http://${{psp.RAILWAY_PRIVATE_DOMAIN}}
```
Start: `uvicorn services.agent.main:app --host 0.0.0.0 --port $PORT`

**PSP** (New → Empty Service → GitHub repo):
Start: `uvicorn services.psp.main:app --host 0.0.0.0 --port $PORT`

### 5. Generate Domains

Settings → Networking → Generate Domain for each service

### 6. Test

```bash
curl https://seller-production.up.railway.app/health
```

## Troubleshooting CLI Timeouts

If `railway up` times out, use web dashboard (above) or:

```bash
railway up --detach  # Non-blocking deploy
```

Check deployment status in dashboard.

## Files

- `railway.toml` - Config
- `nixpacks.toml` - Build
- `Procfile` - Process definitions
