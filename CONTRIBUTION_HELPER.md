# Contribution Helper Guide

Welcome! This guide explains how the ACP Infrastructure codebase works so you can contribute effectively. For setup instructions, see the [README](README.md).

## Table of Contents
1. [The Big Picture](#the-big-picture)
2. [How ACP Works](#how-acp-works)
3. [Code Structure](#code-structure)
4. [Key Workflows](#key-workflows)
5. [Database Flow](#database-flow)
6. [Where to Start Contributing](#where-to-start-contributing)

---

## The Big Picture

### What Problem Does This Solve?

Imagine you're chatting with an AI assistant and say: *"Buy me a coffee maker under $50"*

**Without ACP:** The AI can only recommend products - you still have to manually checkout.

**With ACP:** The AI can:
1. Search for products
2. Show you options
3. Add to cart
4. Select shipping
5. Complete purchase
6. **All through conversation**

### The Protocol

ACP (Agentic Commerce Protocol) is like a "language" that:
- **Agents** (AI assistants) speak to shop
- **Sellers** (merchants) understand to process orders

Think of it like credit cards - Visa/Mastercard set a standard, any bank can issue cards, any merchant can accept them.

---

## How ACP Works

### The 4-Step Purchase Flow

```
1. SEARCH              2. CREATE CHECKOUT       3. SELECT SHIPPING      4. COMPLETE
   Products               Cart + Address           Choose method          Pay + Order
   ↓                      ↓                        ↓                      ↓
   Agent talks           Agent creates            Agent updates          Agent pays
   to Seller            session                  session                via PSP
```

### Status Progression

```
not_ready_for_payment → ready_for_payment → completed
       ↑                       ↑                  ↑
   Missing address/      Has address +       Payment processed
   shipping option      shipping selected    + order created
```

---

## Code Structure

### Layer 1: Framework (`acp_framework/`)

This is the **reusable library** any merchant can use.

#### `models.py` - Data Structures
```python
# What a checkout session looks like
class CheckoutSession:
    id: str                    # "cs_abc123"
    status: CheckoutStatus     # not_ready/ready/completed
    line_items: list          # Products in cart
    totals: list              # Subtotal, tax, shipping
    fulfillment_options: list # Shipping choices
```

**Why it matters:** These match the ACP spec exactly. Any agent speaking ACP can understand these.

**When to contribute here:**
- Adding new ACP protocol fields
- Extending checkout session capabilities
- Adding new payment methods or fulfillment types

#### `seller.py` - Adapter Pattern
```python
class ACPSellerAdapter(ABC):
    @abstractmethod
    async def on_create_session(request) -> CheckoutSession:
        # Merchant implements their catalog logic here
        ...

    @abstractmethod
    async def on_complete_session(session_id, request) -> Order:
        # Merchant implements their payment logic here
        ...
```

**The Magic:** `create_seller_router(adapter)` auto-generates 5 FastAPI endpoints:
```
POST   /checkout_sessions           → calls on_create_session()
GET    /checkout_sessions/{id}      → calls on_get_session()
POST   /checkout_sessions/{id}      → calls on_update_session()
POST   /checkout_sessions/{id}/complete → calls on_complete_session()
POST   /checkout_sessions/{id}/cancel   → calls on_cancel_session()
```

**Why it matters:** Merchants write business logic, framework handles HTTP, headers, validation, signatures.

**When to contribute here:**
- Adding middleware (rate limiting, auth, logging)
- Improving error handling
- Adding webhook capabilities
- Enhancing security (signature verification)

#### `agent.py` - Agent Tools
```python
@function_tool
async def search_products(query: str):
    # Calls GET /products/search
    ...

@function_tool
async def create_checkout(items, address):
    # Calls POST /checkout_sessions
    ...
```

**Why it matters:** These become "skills" the AI agent can use. OpenAI's Agents SDK automatically calls them.

**When to contribute here:**
- Adding new agent capabilities (order tracking, returns, recommendations)
- Improving tool descriptions for better agent understanding
- Adding error handling and retry logic
- Making tools more robust

---

### Layer 2: Services (`services/`)

These are **working implementations** showing how to use the framework.

#### `services/seller/` - Demo Merchant

##### `main.py` - The Adapter Implementation
```python
class WayfairSellerAdapter(ACPSellerAdapter):
    async def on_create_session(self, request):
        # 1. Lookup products in database
        products = await db.query(ProductRow).filter(...)

        # 2. Calculate totals
        subtotal = sum(product.price * qty)
        tax = subtotal * 0.08

        # 3. Return checkout session
        return CheckoutSession(
            id=f"cs_{uuid.uuid4()}",
            status=CheckoutStatus.NOT_READY_FOR_PAYMENT,
            line_items=[...],
            totals=[...]
        )
```

**Real Code Flow:**
1. Agent calls `POST /checkout_sessions`
2. Framework validates request
3. Framework calls `on_create_session()`
4. Your code runs
5. Framework validates response
6. Framework returns JSON to agent

**When to contribute here:**
- Improving tax calculation logic
- Adding discount/promo code support
- Implementing real fulfillment cost APIs
- Adding inventory management

##### `database.py` - Data Persistence
```python
class ProductRow(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    name = Column(String)
    price_cents = Column(Integer)
    in_stock = Column(Boolean)
    search_vector = Column(TSVECTOR)  # For full-text search
```

**Why these tables:**
- `products` - Catalog (42,994 items)
- `checkout_sessions` - Active carts
- `orders` - Completed purchases
- `acp_action_events` - Audit trail

**When to contribute here:**
- Adding database indexes for performance
- Adding new tables (reviews, wishlists, etc.)
- Implementing data retention policies
- Adding database migrations

##### `search.py` - Product Search
```python
async def search_products(query: str, limit: int = 10):
    # Uses PostgreSQL full-text search
    sql = """
        SELECT * FROM products
        WHERE to_tsvector('english', name || ' ' || description)
              @@ plainto_tsquery('english', :query)
        ORDER BY ts_rank(...) DESC
        LIMIT :limit
    """
```

**Why it's fast:** PostgreSQL indexes let us search 42K products in 50-100ms.

**When to contribute here:**
- Improving search relevance (BM25, semantic search)
- Adding faceted search (category filters, price ranges)
- Implementing autocomplete
- Adding spell correction

#### `services/psp/` - Payment Service

```python
@app.post("/agentic_commerce/delegate_payment")
async def delegate_payment(request: DelegatePaymentRequest):
    # 1. Validate card (mock or real Stripe)
    # 2. Create token with spending limit
    return {
        "id": "vt_mock_abc123",
        "created": datetime.now()
    }
```

**Why separate:** Keeps payment logic isolated. Can be mock for testing or real Stripe for production.

**When to contribute here:**
- Adding support for other payment providers (PayPal, Square)
- Implementing 3D Secure
- Adding fraud detection
- Improving tokenization security

#### `services/agent/` - AI Agent

```python
async def run_agent_with_memory(user_message: str):
    # 1. Retrieve memories (past conversations)
    memories = memory.search(user_message, user_id=user_id)

    # 2. Add context to input
    context = f"Customer previously: {memories}\nCustomer says: {user_message}"

    # 3. Run agent (OpenAI decides which tools to call)
    result = await Runner.run(agent, input=context)

    # 4. Store interaction
    memory.add(user_message, response)
```

**The Flow:**
```
User: "Show me sofas"
  ↓
Agent decides: "I should use search_products tool"
  ↓
Agent calls: search_products("sofa")
  ↓
Tool makes HTTP: GET http://seller:8001/products/search?q=sofa
  ↓
Seller returns: [...product list...]
  ↓
Agent formats: "Here are 5 sofas: ..."
  ↓
User sees: Product cards in UI
```

**When to contribute here:**
- Improving agent instructions for better behavior
- Enhancing memory retrieval logic
- Adding personalization features
- Implementing conversation analytics

#### `services/pipeline/` - Data Ingestion

```python
@workflow.defn
class IngestWANDSWorkflow:
    @workflow.run
    async def run(self):
        # 1. Parse CSV
        rows = await workflow.execute_activity(parse_wands_csv)

        # 2. Transform data
        products = await workflow.execute_activity(transform_products, rows)

        # 3. Bulk insert
        await workflow.execute_activity(load_to_database, products)
```

**Why Temporal:** If ingestion fails halfway, it retries from last checkpoint. No duplicate data.

**When to contribute here:**
- Adding new source adapters (Shopify, WooCommerce, BigCommerce)
- Implementing delta/incremental ingestion
- Adding data quality monitoring
- Implementing real-time CDC

---

## Key Workflows

### Workflow 1: Product Search

```
UI → Agent Service → Seller Service → PostgreSQL
                                          ↓
                                    FTS Query (50ms)
                                          ↓
                                    Ranked Results
                                          ↓
← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
```

**Code Path:**
```python
# 1. UI calls agent
POST /chat {"message": "Show me sofas"}

# 2. Agent uses tool
await search_products("sofa")

# 3. Tool calls seller
GET http://seller:8001/products/search?q=sofa

# 4. Seller queries DB
await search_products(db, query="sofa", limit=10)

# 5. PostgreSQL FTS
SELECT * FROM products
WHERE to_tsvector(...) @@ plainto_tsquery('sofa')
ORDER BY ts_rank(...) DESC
LIMIT 10

# 6. Results flow back up
```

**Contribution opportunities:**
- Improve search ranking algorithm
- Add filters (price, category, rating)
- Implement faceted search
- Add autocomplete suggestions

### Workflow 2: Complete Purchase

```
1. CREATE CHECKOUT
   POST /checkout_sessions
   ↓
   Store in checkout_sessions table
   Status: not_ready_for_payment

2. UPDATE CHECKOUT (select shipping)
   POST /checkout_sessions/{id}
   ↓
   Update fulfillment_option_id
   Recalculate totals
   Status: ready_for_payment

3. TOKENIZE PAYMENT
   POST /agentic_commerce/delegate_payment
   ↓
   PSP returns: vt_mock_xyz

4. COMPLETE CHECKOUT
   POST /checkout_sessions/{id}/complete
   ↓
   BEGIN TRANSACTION
     INSERT INTO orders (...)
     UPDATE checkout_sessions SET status='completed'
     INSERT INTO acp_action_events (...)
   COMMIT
   ↓
   Status: completed
```

**Code for Step 4:**
```python
async def on_complete_session(self, session_id, request):
    async with async_session() as db:
        # Get session
        session_row = await db.get(CheckoutSessionRow, session_id)

        # Validate payment token
        if not request.payment_data or not request.payment_data.token:
            raise ACPSellerError("payment_required")

        # Create order
        order = OrderRow(
            id=f"order_{uuid.uuid4().hex[:12]}",
            checkout_session_id=session_id,
            payment_token=request.payment_data.token,
            total_cents=calculate_total(session_row),
        )
        db.add(order)

        # Update session status
        session_row.status = "completed"

        # Log event
        event = ACPActionEventRow(
            intent_type="PURCHASE",
            status="succeeded",
            ...
        )
        db.add(event)

        await db.commit()

        # Emit webhook
        await _emit_order_event("order.created", {...})

        return CheckoutSessionWithOrder(
            ...session_data...,
            order=Order(id=order.id)
        )
```

**Contribution opportunities:**
- Add idempotency handling
- Implement order webhooks
- Add post-purchase flows (email confirmation, tracking)
- Implement order status updates

### Workflow 3: Catalog Ingestion

```
CSV File → Temporal Workflow → Parse Activity
                                    ↓
                              Transform Activity
                                    ↓
                              Quality Check
                                    ↓
                           ┌────────┴────────┐
                          Pass            Fail
                           ↓                ↓
                    Bulk INSERT      Reject + Log
                           ↓
                    Update Stats
```

**Quality Gates:**
```python
def quality_check(products):
    valid = [p for p in products if p.get("id") and p.get("name")]
    invalid = len(products) - len(valid)

    if invalid > MAX_SKIPPED_ROWS:
        raise Exception("Too many invalid rows")

    if len(valid) / len(products) < MIN_VALID_RATIO:
        raise Exception("Valid ratio too low")

    return valid
```

**Contribution opportunities:**
- Add new source connectors (API integrations)
- Implement incremental ingestion
- Add schema validation
- Improve error handling and reporting

---

## Database Flow

### Schema Relationships

```
ProductRow (42,994 rows)
  ↓ referenced by
CheckoutSessionRow (active carts)
  ↓ creates
OrderRow (completed purchases)

Everything logged in:
ACPActionEventRow (audit trail)
```

### Transaction Pattern

```python
async with async_session() as db:
    try:
        # Multiple operations
        db.add(order)
        session.status = "completed"
        db.add(audit_log)

        await db.commit()  # All or nothing
    except Exception:
        await db.rollback()  # Undo everything
        raise
```

**Why it matters:** If payment succeeds but order creation fails, we rollback - no lost money, no orphaned payments.

**Contribution opportunities:**
- Add database indexes for performance
- Implement connection pooling
- Add query optimization
- Implement archival strategies

---

## Where to Start Contributing

### 🟢 Good First Issues

**1. Improve Search Results**
- **File**: `services/seller/search.py`
- **Task**: Add category filtering or price range support
- **Difficulty**: Easy
- **Impact**: Better product discovery

**2. Enhance Agent Responses**
- **File**: `services/agent/commerce_agent.py`
- **Task**: Improve agent instructions for clearer communication
- **Difficulty**: Easy
- **Impact**: Better user experience

**3. Add UI Features**
- **File**: `ui/src/app/page.tsx`
- **Task**: Add product images, ratings display, or loading states
- **Difficulty**: Easy
- **Impact**: Better visual experience

**4. Add Tests**
- **File**: `tests/test_*.py`
- **Task**: Add unit tests for checkout flow or search
- **Difficulty**: Easy
- **Impact**: Better code quality

### 🟡 Intermediate Contributions

**1. Add Order Tracking**
- **Files**: `acp_framework/agent.py`, `services/seller/main.py`
- **Task**: Implement `get_order_status` tool and endpoint
- **Difficulty**: Medium
- **Impact**: New feature

**2. Implement Autocomplete**
- **Files**: `services/seller/search.py`, `ui/src/app/page.tsx`
- **Task**: Add search suggestions as user types
- **Difficulty**: Medium
- **Impact**: Better UX

**3. Add Shopify Source Adapter**
- **Files**: `services/pipeline/sources/shopify_source.py`
- **Task**: Create new source adapter for Shopify API
- **Difficulty**: Medium
- **Impact**: New integration

**4. Implement Rate Limiting**
- **Files**: `acp_framework/seller.py`
- **Task**: Add rate limiting middleware
- **Difficulty**: Medium
- **Impact**: Production readiness

### 🔴 Advanced Contributions

**1. Real-time CDC**
- **Files**: `services/pipeline/`
- **Task**: Implement PostgreSQL logical replication for catalog sync
- **Difficulty**: Hard
- **Impact**: Real-time data

**2. Multi-tenant Support**
- **Files**: `acp_framework/seller.py`, `services/seller/database.py`
- **Task**: Add tenant isolation and routing
- **Difficulty**: Hard
- **Impact**: Scalability

**3. Semantic Search**
- **Files**: `services/seller/search.py`
- **Task**: Implement vector embeddings for semantic search
- **Difficulty**: Hard
- **Impact**: Better search

**4. Agent Personalization**
- **Files**: `services/agent/commerce_agent.py`
- **Task**: Implement purchase history-based recommendations
- **Difficulty**: Hard
- **Impact**: Better recommendations

---

## Summary: How It All Connects

### For a Merchant Integrating ACP

**Install the framework:**

```bash
# Option 1: Install directly from GitHub
pip install git+https://github.com/shabazpatel/acp-infra.git

# Option 2: Install locally in editable mode (for development)
git clone https://github.com/shabazpatel/acp-infra.git
cd acp-infra
pip install -e .
```

**Use in your project:**

```python
# Import framework components
from acp_framework import ACPSellerAdapter, create_seller_router, CheckoutSession

# Implement your adapter
class MyShopAdapter(ACPSellerAdapter):
    async def on_create_session(self, request):
        # Your code: lookup products, calculate totals
        return CheckoutSession(...)

# Add to FastAPI app
app.include_router(create_seller_router(MyShopAdapter()))

# Done! You're now ACP-compliant
```

**Future:** Once stable, we'll publish to PyPI:
```bash
pip install acp-framework  # Coming soon!
```

### For an Agent Developer

```bash
# Install the framework
pip install git+https://github.com/shabazpatel/acp-infra.git
```

```python
# Use pre-built tools
from acp_framework import create_commerce_tools
from agents import Agent

tools = create_commerce_tools(seller_url="https://merchant.com")

# Create agent
agent = Agent(
    name="Shopper",
    instructions="Help users buy products",
    tools=tools
)

# Run
result = await Runner.run(agent, input=user_message)

# Agent automatically uses tools as needed
```

### Key Takeaways

1. **Framework = Reusable** - Any merchant can use it
2. **Services = Examples** - Shows how to implement
3. **Adapter Pattern = Flexibility** - You write business logic, framework handles protocol
4. **Tools = Agent Skills** - Agent learns what it can do
5. **Database = State** - Products, carts, orders, audit trail

---

## Getting Help

### Setup & Running
- See [README.md](README.md) for installation and running services
- See [DEPLOY.md](DEPLOY.md) for deployment guides

### Contributing Process
- See [README.md#Contributing](README.md#contributing) for PR workflow
- Look for `good-first-issue` labels on GitHub
- Join discussions for questions

### Community
- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and ideas
- **Pull Requests**: Code contributions

**Welcome to ACP Infrastructure! We're excited to have you contribute.** 🎉