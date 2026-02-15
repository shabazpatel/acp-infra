# Architecture Summary

## 📊 Quick Reference

### System Overview
- **Total Services**: 4 (Seller, PSP, Agent, Worker)
- **Infrastructure**: PostgreSQL + Temporal.io
- **UI**: Next.js React app
- **Protocol**: Agentic Commerce Protocol (ACP) v2026-01-30
- **Scale**: 42,994 products, sub-100ms search

### Service Map

```
Port 3000 → UI (Next.js)
Port 8001 → Seller (FastAPI) - ACP Checkout + Products
Port 8002 → PSP (FastAPI) - Delegate Payment
Port 8003 → Agent (FastAPI) - Chat Interface
Port 5432 → PostgreSQL - Data Store
Port 7233 → Temporal - Workflow Engine
```

## 🔄 Data Flow Patterns

### Pattern 1: Product Search
```
User → UI → Agent → Seller → PostgreSQL
                              ↓
                         FTS Index (50-100ms)
                              ↓
                         Ranked Results
```

### Pattern 2: Checkout Flow
```
User Intent → Agent (parse) → create_checkout tool
                                    ↓
                              Seller Service
                                    ↓
                              Validate Products
                                    ↓
                              Calculate Totals (subtotal + tax + shipping)
                                    ↓
                              Store Session (PostgreSQL)
                                    ↓
                              Return CheckoutSession
```

### Pattern 3: Payment Processing
```
complete_checkout → Agent → PSP (tokenize)
                             ↓
                        Mock Token: vt_mock_xxx
                             ↓
                        Agent → Seller (complete with token)
                                    ↓
                               Create Order
                                    ↓
                               Emit Webhooks
                                    ↓
                               Log ACP Event
```

### Pattern 4: Catalog Ingestion
```
CSV File → Temporal Workflow → Parse Activity
                                    ↓
                              Transform Activity
                                    ↓
                              Quality Checks (90%+ valid)
                                    ↓
                              Bulk INSERT → PostgreSQL
                                    ↓
                              Update Ingestion Stats
```

## 📦 Database Design

### Core Tables

**products** (42,994 rows)
- Primary catalog table
- Full-text search indexed
- Ratings stored in `attributes` JSONB

**checkout_sessions**
- Tracks ACP session lifecycle
- Stores full session state in `session_data`
- Status: not_ready → ready → completed

**orders**
- Created on checkout completion
- Links to checkout_session
- Stores payment token reference

**acp_action_events**
- Audit trail for all ACP operations
- Intent → Action → Verification → Execution pattern
- Searchable by session, actor, intent type

## 🔧 Framework Design

### acp_framework Package

**Core Abstractions:**

1. **ACPSellerAdapter** (Abstract Base Class)
   - `on_create_session()`
   - `on_get_session()`
   - `on_update_session()`
   - `on_complete_session()`
   - `on_cancel_session()`

2. **create_seller_router()** (Factory)
   - Auto-generates 5 FastAPI routes
   - Handles headers (API-Version, Idempotency-Key, etc.)
   - Enforces HMAC signature verification
   - Manages idempotency store

3. **create_commerce_tools()** (Agent Tools)
   - Returns 10 @function_tool decorated functions
   - Used by OpenAI Agents SDK
   - Wraps HTTP calls to seller/PSP

### Extension Pattern

```python
# Merchant implements:
class MySellerAdapter(ACPSellerAdapter):
    async def on_create_session(self, request):
        # Your catalog logic
        return CheckoutSession(...)

# Framework provides:
router = create_seller_router(MySellerAdapter())
app.include_router(router)
```

## 🎯 Key Features

### 1. Idempotency
- Payload hash stored per idempotency key
- Duplicate requests return cached response
- Mismatched payload → 409 Conflict

### 2. Memory (mem0)
- Cross-session customer context
- Stores: preferences, addresses, purchase history
- Retrieves relevant memories for each chat

### 3. Full-Text Search
- PostgreSQL `ts_vector` + `ts_rank`
- Multi-field: name + description + category
- Stemming + ranking for relevance

### 4. Audit Trail
- Every ACP action logged
- Intent + Action + Verification + Execution
- Queryable for compliance/debugging

### 5. Quality Gates (Ingestion)
- Min 90% valid rows required
- Max 5000 skipped rows
- Atomicity via Temporal workflows

## 📈 Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Product Search | 50-100ms | PostgreSQL FTS |
| Create Checkout | 100-200ms | DB insert + calculations |
| Complete Checkout | 150-300ms | Transaction with 4 table writes |
| Agent Response | 2-5s | OpenAI API + tool calls |
| Bulk Ingestion | 30-60s | 42K products via Temporal |

## 🔐 Security Features

1. **API Version Validation**
   - Required header: `API-Version: 2026-01-30`
   - Rejects unsupported versions

2. **HMAC Signature Verification**
   - Optional `X-OpenAI-Signature` header
   - SHA-256 HMAC of request body
   - Configurable secret

3. **Bearer Token Auth**
   - Required on all endpoints
   - Format: `Authorization: Bearer <token>`

4. **PCI Scope Reduction**
   - Delegate payment API
   - No direct card data handling
   - PSP tokenizes before seller sees data

## 🎨 UI Architecture

### Components

**Chat Panel** (Left)
- Message history with role badges
- Product card renderer (detects markdown format)
- Typing indicator
- Auto-scroll

**Checkout Panel** (Right)
- Session status timeline
- Line items with pricing
- Fulfillment options
- Order confirmation

### State Management

```typescript
messages: Message[]           // Chat history
checkout: CheckoutData | null // Active session
isLoading: boolean           // Request in flight
```

### API Routes

```
/api/chat → POST → Agent Service :8003
/api/seller/checkout_sessions/:id → GET → Seller :8001
```

## 🚀 Deployment Architecture

### Railway (Production)
```
railway.toml → Service definitions
Procfile → Start commands
nixpacks.toml → Build config
```

**Services Deployed:**
- seller-service
- psp-service
- agent-service
- pipeline-worker
- ui

**Shared Resources:**
- PostgreSQL (Railway plugin)
- Temporal Cloud (external)

### Environment Variables (Required)
```
OPENAI_API_KEY
DATABASE_URL
TEMPORAL_HOST
SELLER_SERVICE_URL
PSP_SERVICE_URL
```

## 📚 Further Reading

- **README.md** - Main documentation with diagrams
- **CLAUDE.md** - Developer guide for Claude Code
- **deployment/acp-conformance-report.md** - Spec compliance
- **TEST_RESULTS.md** - Certification test results
- **QUICK_START.md** - Setup and usage guide
