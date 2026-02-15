# Railway Deployment

## Setup

```bash
railway login
railway init
railway add --plugin postgresql
```

## Configure

Required env vars:
```
OPENAI_API_KEY=sk-...
DATABASE_URL=${{Postgres.DATABASE_URL}}
TEMPORAL_HOST=localhost:7233  # or Temporal Cloud URL
```

## Deploy services

Create 4 services with these start commands:

**Seller**:
```
uvicorn services.seller.main:app --host 0.0.0.0 --port $PORT
```

**Agent**:
```
uvicorn services.agent.main:app --host 0.0.0.0 --port $PORT
```
Set: `SELLER_SERVICE_URL=${{Seller.RAILWAY_PRIVATE_DOMAIN}}`

**PSP**:
```
uvicorn services.psp.main:app --host 0.0.0.0 --port $PORT
```

**UI** (optional):
```
cd ui && npm run build && npm start
```
Set: `AGENT_SERVICE_URL=${{Agent.RAILWAY_PRIVATE_DOMAIN}}`

## Deploy

```bash
railway up
```

## Monitor

Health checks at `/{service}/health`. View logs: `railway logs`.
