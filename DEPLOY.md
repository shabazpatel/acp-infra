# Deploy to Railway

## Prerequisites

1. Railway account at railway.app
2. GitHub repo connected to Railway

## Steps

### 1. Create Railway project

```bash
railway login  # Opens browser
railway init   # Creates new project
```

### 2. Add PostgreSQL

In Railway dashboard:
- Click "New" → "Database" → "PostgreSQL"
- Railway will set `DATABASE_URL` automatically

### 3. Create 3 services

**Service 1: Seller API**
- Click "New Service"
- Name: `seller`
- Settings → Variables:
  ```
  OPENAI_API_KEY=sk-...
  DATABASE_URL=${{Postgres.DATABASE_URL}}
  TEMPORAL_HOST=localhost:7233
  ACP_AUTO_INGEST_ON_STARTUP=true
  ```
- Settings → Deploy:
  - Start Command: `uvicorn services.seller.main:app --host 0.0.0.0 --port $PORT`
  - Health Check: `/health`

**Service 2: Agent API**
- Click "New Service"
- Name: `agent`
- Variables:
  ```
  OPENAI_API_KEY=sk-...
  SELLER_SERVICE_URL=${{seller.RAILWAY_PRIVATE_DOMAIN}}
  PSP_SERVICE_URL=${{psp.RAILWAY_PRIVATE_DOMAIN}}
  ```
- Start: `uvicorn services.agent.main:app --host 0.0.0.0 --port $PORT`

**Service 3: PSP**
- Click "New Service"
- Name: `psp`
- Start: `uvicorn services.psp.main:app --host 0.0.0.0 --port $PORT`

### 4. Deploy

```bash
railway up
```

Or push to GitHub (auto-deploys if connected).

### 5. Generate domain

In Railway dashboard for each service:
- Settings → Networking → Generate Domain

You'll get URLs like:
- `seller-production.up.railway.app`
- `agent-production.up.railway.app`
- `psp-production.up.railway.app`

### 6. Test

```bash
curl https://seller-production.up.railway.app/health
```

## Config files

- `railway.toml` - Railway configuration
- `Procfile` - Process definitions (Heroku-style)
- `nixpacks.toml` - Build configuration

## Notes

- Use private networking between services (`RAILWAY_PRIVATE_DOMAIN`)
- PostgreSQL included in Railway (not Temporal - use Temporal Cloud or self-host)
- Free tier: 500 hours/month, sleeps after inactivity
- Pro tier: Always-on, better resources

## Troubleshooting

Check logs: `railway logs seller`
