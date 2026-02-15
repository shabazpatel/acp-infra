# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ACP Framework is a Python implementation of the Agentic Commerce Protocol (ACP), an open standard for AI agents to conduct purchases programmatically. The codebase provides:
- A reusable framework (`acp_framework/`) for implementing ACP sellers and agents
- Reference implementations in `services/` (seller, agent, PSP, pipeline)
- A demo using the Wayfair WANDS dataset (42,994 products)

## Development Commands

### Initial Setup
```bash
./setup.sh                    # One-command setup: installs uv, creates venv, installs deps, starts Docker
source .venv/bin/activate     # Activate virtual environment
```

### Running Services
```bash
# Start infrastructure (Postgres + Temporal)
docker compose up -d

# Run Temporal worker (for ETL/pipeline workflows)
python -m services.pipeline.worker

# Start individual services
uvicorn services.seller.main:app --port 8001       # Seller service (ACP checkout endpoints)
uvicorn services.psp.main:app --port 8002          # Payment service provider (delegate payment)
uvicorn services.agent.main:app --port 8003        # Agent service (OpenAI Agents SDK)

# Start UI
cd ui && npm install && npm run dev
```

### Testing & Quality
```bash
# Run tests
pytest                        # All tests
pytest tests/test_acp_contracts.py    # Specific test file
pytest -v                     # Verbose mode
pytest -k "test_name"         # Run specific test by name

# Linting
ruff check .                  # Check code
ruff check . --fix            # Auto-fix issues
ruff format .                 # Format code
```

### Data Ingestion
```bash
# Trigger WANDS product catalog ingestion
curl -X POST http://localhost:8001/admin/ingest/product-csv

# Check ingestion stats
curl http://localhost:8001/admin/ingest/stats
```

## Architecture

### ACP Protocol Flow
```
User (UI) → Agent Service → Seller Service → PSP Service
              ↓ (mem0)        ↓ (Postgres)    ↓ (Stripe/mock)
         Conversation       Products/        Payment
           Memory          Checkout           Tokens
```

### Core Framework Pattern (`acp_framework/`)

The framework uses an **adapter pattern** to make any merchant ACP-compliant:

1. **Models** (`models.py`): Pydantic models matching the ACP spec (2026-01-30)
   - `CheckoutSession`, `LineItem`, `Total`, `Order`
   - `PaymentHandler`, `Capabilities`, `FulfillmentOption`
   - Delegate payment models: `DelegatePaymentRequest`, `Allowance`

2. **Seller Adapter** (`seller.py`): Abstract base class + router factory
   ```python
   class ACPSellerAdapter(abc.ABC):
       async def on_create_session(...)
       async def on_get_session(...)
       async def on_update_session(...)
       async def on_complete_session(...)
       async def on_cancel_session(...)

   router = create_seller_router(adapter)  # Auto-generates 5 ACP endpoints
   ```
   - Implements request validation (API-Version, signatures, idempotency)
   - Handles HMAC signature verification (X-OpenAI-Signature)
   - Provides idempotency store for duplicate request detection

3. **Agent Tools** (`agent.py`): Function decorators for OpenAI Agents SDK
   ```python
   tools = create_commerce_tools(seller_url="http://localhost:8001")
   agent = Agent(name="shopper", tools=tools, instructions="...")
   ```
   - Exposes ACP checkout operations as agent tools
   - Includes search, compare, simulate, create/update/complete checkout

### Service Architecture

**Seller Service** (`services/seller/`)
- Implements `ACPSellerAdapter` for Wayfair demo catalog
- Database schema in `database.py`:
  - `products` table with full-text search vector
  - `checkout_sessions` storing ACP checkout state
  - `orders` for completed purchases
  - `acp_action_events` audit log (Intent → Action → Verification → Execution)
  - `ingestion_runs` for ETL statistics
- Search implementation in `search.py` (text search + filtering)
- Emits order webhooks with HMAC signatures

**Agent Service** (`services/agent/`)
- Wraps OpenAI Agents SDK with mem0 for conversation memory
- Simple REST API: `/chat` endpoint takes message + user_id/session_id
- Extracts checkout session IDs from agent responses

**PSP Service** (`services/psp/`)
- Mock implementation of Delegate Payment API
- Issues payment tokens with allowance constraints
- Can be configured to use real Stripe via `STRIPE_API_KEY`

**Pipeline Service** (`services/pipeline/`)
- Temporal.io workflows for durable ETL
- `IngestWANDSWorkflow`: CSV parsing → transform → bulk load
- `IngestCatalogSourceWorkflow`: Pluggable source adapters (csv, postgres_cdc scaffold)
- Activities in `activities.py`: atomic data transformation steps

### Database Model Relationships

```
ProductRow (id, name, price_cents, attributes, search_vector)
    ↓ referenced by
CheckoutSessionRow (id, status, items[{id, quantity}], session_data)
    ↓ one-to-one
OrderRow (id, checkout_session_id, payment_token, total_cents)

IngestionRunRow (id, source, total_rows, valid_rows, status)
    ↓ tracks
ProductRow bulk inserts

ACPActionEventRow (id, session_id, intent_type, status)
    ↓ audits
All ACP operations (search, compare, purchase)
```

### ACP Contract System

The codebase implements an audit trail following: **Intent → Action → Verification → Execution**

```python
ACPActionEvent(
    intent=ACPIntent(type="search|compare|purchase", user_utterance="..."),
    action=ACPAction(input={...}, idempotency_key="..."),
    verification=ACPVerification(schema_valid=True, approved=True),
    execution=ACPExecution(status="succeeded|failed", result_ref="...")
)
```

Logged in `acp_action_events` table for compliance and debugging.

### Key Design Patterns

1. **Adapter Pattern**: `ACPSellerAdapter` abstracts ACP compliance from business logic
2. **Factory Pattern**: `create_seller_router()` generates FastAPI routes automatically
3. **Decorator Pattern**: `@function_tool` wraps async functions for agent use
4. **Repository Pattern**: Database access via SQLAlchemy async sessions
5. **Workflow Orchestration**: Temporal.io for durable, retryable ETL

## Configuration

Environment variables (see `.env.example`):
- `OPENAI_API_KEY`: Required for agent service
- `DATABASE_URL`: Postgres connection (default: localhost:5432)
- `TEMPORAL_HOST`: Temporal server (default: localhost:7233)
- `STRIPE_API_KEY`: Optional, enables real Stripe delegate payment
- `MEM0_API_KEY`: Optional, uses local mem0 if not set
- `ACP_OPENAI_SIGNATURE_SECRET`: HMAC secret for request signatures
- `ACP_AUTO_INGEST_ON_STARTUP`: Auto-run ingestion on seller startup (default: true)

## Extending the Framework

### Adding a New Seller

```python
from acp_framework.seller import ACPSellerAdapter, create_seller_router

class MySellerAdapter(ACPSellerAdapter):
    async def on_create_session(self, request):
        # Your catalog lookup logic
        # Calculate totals, tax, shipping
        return CheckoutSession(...)

    async def on_complete_session(self, session_id, request):
        # Process payment via PSP
        # Create order record
        return CheckoutSessionWithOrder(order=Order(...))

app.include_router(create_seller_router(MySellerAdapter()))
```

### Adding Agent Tools

```python
from agents import function_tool

@function_tool
async def custom_tool(param: str) -> dict:
    """Description for the agent."""
    # Your logic here
    return {"result": "..."}

tools = create_commerce_tools(...) + [custom_tool]
```

### Adding Pipeline Sources

Implement a new source adapter in `services/pipeline/sources.py` following the pattern:
```python
def ingest_from_custom_source(config: dict) -> list[dict]:
    # Return list of raw product dicts
    return [{"id": ..., "name": ..., "price_cents": ...}]
```

Register in `ingest_catalog_source()` activity.

## Important Technical Details

- **Monetary amounts**: All prices in smallest currency unit (cents for USD)
- **Idempotency**: Seller router stores payload hashes, returns 409 on mismatch
- **API versioning**: Header `API-Version: 2026-01-30` required on all requests
- **Fulfillment status flow**: `not_ready_for_payment` → `ready_for_payment` → `completed`
- **Session readiness**: Requires fulfillment_address AND fulfillment_option_id
- **Tax calculation**: Simplified 8% flat rate in demo (see `TAX_RATE` in `services/seller/main.py`)
- **Search vector**: `ProductRow.search_vector` concatenates name + description + category for text search
- **Temporal task queue**: `acp-pipeline` (configurable via `TEMPORAL_TASK_QUEUE`)

## Database Operations

Tables are auto-created via `init_db()` on startup. For production:
```bash
# Generate migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head
```

## Temporal Workflows

Access Temporal Web UI at `http://localhost:8233` to monitor workflows.

Trigger workflows programmatically:
```python
from temporalio.client import Client
from services.pipeline.workflows import IngestWANDSWorkflow

client = await Client.connect("localhost:7233")
result = await client.execute_workflow(
    IngestWANDSWorkflow.run,
    id="workflow-id",
    task_queue="acp-pipeline"
)
```

## Service Dependencies

```
services/seller/    → acp_framework, Postgres, Temporal client
services/agent/     → acp_framework, OpenAI SDK, mem0
services/psp/       → acp_framework, Stripe (optional)
services/pipeline/  → Postgres, Temporal worker
```

All services are independently deployable FastAPI apps with `/health` endpoints.