# ACP Infrastructure

Reference implementation of the Agentic Commerce Protocol (ACP) for end-to-end
agentic shopping flows.

## Project goal

Template and pattern for merchant/seller engineering teams to:

1. Integrate ACP into their commerce stack using proven service patterns
2. Deploy ACP-compatible seller and payment services
3. Connect those services to various agent experiences (including the demo agent/UI in this repo)

## What this system provides

- ACP Checkout API implementation (seller service)
- Delegate Payment API implementation (PSP service)
- Tool-using commerce agent (OpenAI Agents SDK)
- Durable catalog ingestion via Temporal workflows
- Shared ACP domain models and adapter abstractions (`acp_framework/`)

## Architecture at a glance

### System Architecture

```mermaid
flowchart TB
    %% Experience layer
    subgraph EXPERIENCE["Experience"]
        UI["Next.js UI<br/>:3000"]
    end

    %% Agent runtime
    subgraph AGENTS["Agent"]
        AGENT["Agent Service<br/>:8003"]
        MEM["mem0"]
        AGENT --- MEM
    end

    %% ACP services
    subgraph ACP["ACP Services"]
        SELLER["Seller<br/>:8001"]
        PSP["PSP<br/>:8002"]
    end

    %% Platform
    subgraph PLATFORM["Platform"]
        DB[("PostgreSQL")]
        TEMPORAL["Temporal"]
        WORKER["Worker"]
    end

    %% Framework
    FRAMEWORK["acp_framework<br/>(shared models)"]

    %% Connections
    UI --> AGENT
    AGENT --> SELLER
    AGENT --> PSP
    SELLER --> DB
    WORKER --> DB
    SELLER --> TEMPORAL
    TEMPORAL --> WORKER

    FRAMEWORK -.-> AGENT
    FRAMEWORK -.-> SELLER
    FRAMEWORK -.-> PSP

    %% Styling
    classDef experience fill:#e1f5ff,stroke:#0077b6,stroke-width:2px
    classDef agent fill:#fff3cd,stroke:#ffc107,stroke-width:2px
    classDef acp fill:#d1e7dd,stroke:#198754,stroke-width:2px
    classDef platform fill:#f8d7da,stroke:#dc3545,stroke-width:2px
    classDef framework fill:#e7e7e7,stroke:#6c757d,stroke-width:2px

    class UI experience
    class AGENT,MEM agent
    class SELLER,PSP acp
    class DB,TEMPORAL,WORKER platform
    class FRAMEWORK framework
```

### Data Flow: Purchase Journey

```mermaid
sequenceDiagram
    participant UI as UI
    participant Agent as Agent
    participant Seller as Seller
    participant PSP as PSP
    participant DB as Database

    %% Search
    Note over UI,DB: 1. Search Products
    UI->>Agent: "Show me sofas"
    Agent->>Seller: GET /products/search
    Seller->>DB: Query products
    DB-->>Seller: Results
    Seller-->>Agent: Products list
    Agent-->>UI: Display cards

    %% Create Checkout
    Note over UI,DB: 2. Create Checkout
    UI->>Agent: "Buy product 123"
    Agent->>Seller: POST /checkout_sessions
    Seller->>DB: Insert session
    DB-->>Seller: Session created
    Seller-->>Agent: Checkout session
    Agent-->>UI: Show options

    %% Select Shipping
    Note over UI,DB: 3. Select Shipping
    UI->>Agent: "Standard shipping"
    Agent->>Seller: POST /checkout_sessions/:id
    Seller->>DB: Update session
    DB-->>Seller: Updated
    Seller-->>Agent: Ready for payment
    Agent-->>UI: Show total

    %% Complete
    Note over UI,DB: 4. Complete Order
    UI->>Agent: "Complete purchase"
    Agent->>PSP: POST /delegate_payment
    PSP-->>Agent: Payment token
    Agent->>Seller: POST /:id/complete
    Seller->>DB: Create order
    DB-->>Seller: Order ID
    Seller-->>Agent: Order confirmed
    Agent-->>UI: Success!
```

### Ingestion Pipeline

```mermaid
flowchart LR
    subgraph SOURCES["Data Sources"]
        CSV[CSV Files]
        PG[PostgreSQL CDC]
        API[REST API]
        OTHER[Other Connectors]
    end

    CSV --> Workflow[Temporal<br/>Workflow]
    PG -.-> Workflow
    API -.-> Workflow
    OTHER -.-> Workflow

    Workflow --> Parse[Parse]
    Parse --> Transform[Transform]
    Transform --> QC{Quality<br/>Check}
    QC -->|Pass| DB[(Database)]
    QC -->|Fail| Reject[Reject]
    DB --> Stats[Stats API]
```

### Key Metrics & Scale

| Metric | Current | Notes |
|--------|---------|-------|
| **Products** | 42,994 | WANDS dataset (Wayfair) |
| **Search Latency** | 50-100ms | PostgreSQL FTS with ranking |
| **ACP Endpoints** | 5 | create, get, update, complete, cancel |
| **Agent Tools** | 10 | search, details, rating, compare, simulate, checkout (5) |
| **Supported Headers** | 7 | API-Version, Idempotency-Key, Request-Id, Authorization, X-OpenAI-Signature, Accept-Language, User-Agent |
| **Test Coverage** | 15/15 | All ACP sandbox tests passing |
| **Database Tables** | 7 | products, checkout_sessions, orders, acp_action_events, ingestion_runs, source_connections, source_checkpoints |
| **Ingestion Quality** | 90%+ | Min valid ratio enforced |

### Component responsibilities

| Component | Path | Responsibility |
|---|---|---|
| **ACP framework** | `acp_framework/` | Shared ACP models (Pydantic), seller adapter contract (`ACPSellerAdapter`), payment provider primitives, router factory (`create_seller_router`), agent tools factory (`create_commerce_tools`) |
| **Seller service** | `services/seller/main.py` | ACP checkout lifecycle (5 endpoints), product APIs (search, details, ratings, compare), ingestion trigger/admin endpoints, webhook emitter |
| **PSP service** | `services/psp/main.py` | Delegate payment tokenization with API-version validation, idempotency enforcement, HMAC signature checks, mock or Stripe-backed |
| **Agent service** | `services/agent/main.py` | Chat endpoint (`/chat`) over tool-enabled commerce agent (OpenAI Agents SDK), mem0 integration for cross-session memory |
| **Pipeline worker** | `services/pipeline/worker.py` | Registers and runs Temporal workflows (CSV ingestion, source adapters) + activities (parse, transform, load) |
| **UI** | `ui/` | Customer-facing Next.js chat interface with real-time checkout panel, product card rendering, API route proxying |

## Request flow

1. User sends a message in UI.
2. Agent service resolves intent and calls seller/PSP tools.
3. Seller service creates/updates/completes ACP checkout sessions.
4. PSP service issues delegated payment tokens (mock or Stripe-backed).
5. Seller persists sessions/orders and action events for traceability.

## Local development

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker Desktop (for PostgreSQL + Temporal)
- `OPENAI_API_KEY`

### Bootstrap

```bash
git clone https://github.com/shabazpatel/acp-infra.git
cd acp-infra
chmod +x setup.sh
./setup.sh
```

`setup.sh` installs `uv`, creates `.venv`, installs dependencies, copies `.env`,
and starts Docker dependencies when available.

### Environment

```bash
cp .env.example .env
```

Minimum required variable:

- `OPENAI_API_KEY`

Optional integrations:

- `MEM0_API_KEY` (agent memory)
- `STRIPE_API_KEY` (real tokenization in PSP)
- `ACP_OPENAI_SIGNATURE_SECRET` (request signature verification)

### Run services

Use separate terminals.

```bash
# Terminal 1
source .venv/bin/activate
python -m services.pipeline.worker
```

```bash
# Terminal 2
source .venv/bin/activate
uvicorn services.seller.main:app --reload --port 8001
```

```bash
# Terminal 3
source .venv/bin/activate
uvicorn services.psp.main:app --reload --port 8002
```

```bash
# Terminal 4
source .venv/bin/activate
uvicorn services.agent.main:app --reload --port 8003
```

```bash
# Terminal 5
cd ui
npm install
npm run dev
```

Access UI at `http://localhost:3000`.

## Operational endpoints

### Health

- Seller: `GET /health` on `:8001`
- PSP: `GET /health` on `:8002`
- Agent: `GET /health` on `:8003`

### Seller service

- `GET /products/search`
- `GET /products/{product_id}`
- `GET /ratings/{product_id}`
- `POST /compare`
- ACP checkout router endpoints (mounted via `create_seller_router`)
- `POST /admin/ingest/product-csv`
- `POST /admin/ingest/source`
- `GET /admin/ingest/stats`

### PSP service

- `POST /agentic_commerce/delegate_payment`

Behavioral guarantees include API version validation, optional HMAC verification,
and idempotency replay semantics.

## Testing

Run unit/integration tests:

```bash
source .venv/bin/activate
pytest
```

Run ACP sandbox contract tests:

```bash
./test_acp_sandbox.sh
```

## Extending for a merchant integration

1. Implement an `ACPSellerAdapter` for your catalog, pricing, tax, fulfillment,
   and order backends.
2. Mount the adapter using `create_seller_router(...)`.
3. Replace demo search/product endpoints with your catalog APIs.
4. Wire webhook and audit sinks to your observability stack.
5. Enforce production auth and secret management per your platform standards.

## Deployment

- Generic deployment guidance: `DEPLOY.md`
- Railway-specific assets: `deployment/railway/`

For Railway, review and align:

- `railway.toml`
- `Procfile`
- `nixpacks.toml`
- `deployment/railway/README.md`

## Repository references

- Architecture notes: `docs/architecture.md`
- Docker topology: `docker-compose.yml`
- Environment contract: `.env.example`

## License

MIT (declared in `pyproject.toml`).
