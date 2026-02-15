# ACP Framework

Python implementation of the [Agentic Commerce Protocol](https://www.agenticcommerce.dev/docs).

## What it does

Provides reusable components for merchants to integrate with AI shopping agents:

- **acp_framework/** - Core protocol models and adapters
- **services/seller/** - Reference checkout API implementation
- **services/agent/** - OpenAI Agents SDK wrapper with commerce tools
- **services/psp/** - Delegate payment mock (Stripe-compatible)
- **services/pipeline/** - Temporal workflows for catalog ingestion

## Quick start

```bash
./setup.sh
source .venv/bin/activate

# Start infrastructure
docker compose up -d

# Start services
uvicorn services.seller.main:app --port 8001 &
uvicorn services.psp.main:app --port 8002 &
uvicorn services.agent.main:app --port 8003 &

# Start UI (optional)
cd ui && npm install && npm run dev
```

Requires `.env` with `OPENAI_API_KEY`.

## For sellers

### Option 1: Use the adapter

```python
from acp_framework.seller import ACPSellerAdapter, create_seller_router
from acp_framework.models import CheckoutSession

class MyAdapter(ACPSellerAdapter):
    async def on_create_session(self, request):
        # Your product lookup and pricing logic
        return CheckoutSession(...)

    async def on_complete_session(self, session_id, request):
        # Your payment and order creation logic
        return CheckoutSessionWithOrder(...)

    # Implement other 3 methods: on_get_session, on_update_session, on_cancel_session

app.include_router(create_seller_router(MyAdapter()))
```

Gets you:
- ACP protocol compliance
- Request validation (API-Version, signatures, idempotency)
- HMAC verification
- Automatic error responses

### Option 2: Implement endpoints manually

See `services/seller/main.py` for reference. Required endpoints:

```
POST   /checkout_sessions           Create session
GET    /checkout_sessions/{id}      Get session
POST   /checkout_sessions/{id}      Update session
POST   /checkout_sessions/{id}/complete   Complete order
POST   /checkout_sessions/{id}/cancel     Cancel session
```

All requests require:
```
Authorization: Bearer <token>
API-Version: 2026-01-30
Content-Type: application/json
```

## Data pipeline

Product ingestion via Temporal workflows. Supports pluggable source adapters:

```python
# services/pipeline/sources.py

class MySourceAdapter(SourceAdapter):
    async def snapshot_rows(self) -> list[dict[str, str]]:
        # Return list of dicts with keys:
        # product_id, product_name, product_description,
        # product_class, price_cents
        pass
```

Register and trigger:

```python
def build_source_adapter(source_type: str, config: dict):
    if source_type == "my_source":
        return MySourceAdapter(config)
```

```bash
curl -X POST http://localhost:8001/admin/ingest/source \
  -H "Content-Type: application/json" \
  -d '{"source_type":"my_source","source_config":{...}}'
```

Monitor via `/admin/ingest/stats`.

## Testing

```bash
pytest                      # Unit tests
./test_acp_sandbox.sh      # ACP certification (15 tests)
```

## Architecture

```
┌──────┐     ┌────────┐     ┌────────┐     ┌─────┐
│  UI  │────▶│ Agent  │────▶│ Seller │────▶│ PSP │
└──────┘     └────────┘     └────────┘     └─────┘
               │  ▲             │
               │  │             │
               ▼  │             ▼
            ┌──────────┐   ┌─────────┐
            │   mem0   │   │Postgres │
            └──────────┘   └─────────┘
                               ▲
                               │
                          ┌──────────┐
                          │ Temporal │
                          │  Worker  │
                          └──────────┘
```

- **Agent**: GPT-4o-mini with 10 commerce tools, 2.4s avg response
- **Seller**: FastAPI + Postgres, full-text search on 40k+ products
- **PSP**: Mock delegate payment (Stripe API compatible)
- **Pipeline**: Temporal for durable ETL

## Deployment

Railway:
```bash
railway add --plugin postgresql
railway add --template temporal
railway variables set OPENAI_API_KEY=sk-...
railway up
```

See `deployment/railway/README.md` for details.

## Docs

- `docs/architecture.md` - Detailed architecture
- `deployment/railway/README.md` - Railway deployment
- [ACP Spec](https://www.agenticcommerce.dev/docs/commerce/specs/checkout)

## Demo

Includes Wayfair WANDS dataset (42,994 products) for testing. Auto-ingests on startup if `ACP_AUTO_INGEST_ON_STARTUP=true`.

Visit http://localhost:3000 after starting services.

## License

MIT
