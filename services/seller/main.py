"""
Seller Service — FastAPI app implementing ACP Checkout endpoints.

This is the Wayfair demo seller backed by the WANDS product catalog.
Any merchant can follow this pattern to become ACP-compliant.
"""

from __future__ import annotations

import logging
import math
import os
import uuid
import hashlib
import hmac
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from acp_framework.models import (
    ACPAction,
    ACPActionEvent,
    ACPActor,
    ACPExecution,
    ACPExecutionStatus,
    ACPIntent,
    ACPIntentType,
    ACPVerification,
    Capabilities,
    CheckoutSession,
    CheckoutSessionCompleteRequest,
    CheckoutSessionCreateRequest,
    CheckoutSessionUpdateRequest,
    CheckoutSessionWithOrder,
    CheckoutStatus,
    CompareProductsRequest,
    CompareProductsResponse,
    ComparedProduct,
    ExtensionDeclaration,
    FulfillmentOptionShipping,
    FulfillmentType,
    LineItem,
    Link,
    LinkType,
    MessageInfo,
    Order,
    Payment,
    PaymentData,
    PaymentHandler,
    PaymentHandlerConfig,
    PaymentProvider,
    ProductInfo,
    ProductRatingSummary,
    PurchaseSimulateRequest,
    PurchaseSimulateResponse,
    Total,
    TotalType,
)
from acp_framework.seller import ACPSellerAdapter, ACPSellerError, create_seller_router
from services.seller.database import (
    ACPActionEventRow,
    CheckoutSessionRow,
    IngestionRunRow,
    OrderRow,
    ProductRow,
    async_session,
    get_session,
    init_db,
)
from services.seller.search import search_products


# ── Tax rate (simplified — 8% flat) ─────────────────────────────────────
TAX_RATE = 0.08
MERCHANT_ID = "wayfair_demo"
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "acp-pipeline")
AUTO_INGEST_ON_STARTUP = os.getenv("ACP_AUTO_INGEST_ON_STARTUP", "true").lower() == "true"
ORDER_WEBHOOK_URL = os.getenv("ACP_ORDER_WEBHOOK_URL", "")
ORDER_WEBHOOK_SECRET = os.getenv("ACP_ORDER_WEBHOOK_SECRET", "")

logger = logging.getLogger(__name__)


async def _emit_order_event(event_type: str, payload: dict[str, Any]) -> None:
    if not ORDER_WEBHOOK_URL:
        return

    body = {"type": event_type, "payload": payload}
    serialized = json.dumps(body, separators=(",", ":"), sort_keys=True)
    headers = {"Content-Type": "application/json"}
    if ORDER_WEBHOOK_SECRET:
        digest = hmac.new(
            ORDER_WEBHOOK_SECRET.encode("utf-8"),
            serialized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["X-Webhook-Signature"] = digest

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(ORDER_WEBHOOK_URL, content=serialized, headers=headers)
    except Exception as exc:
        logger.warning("Failed to emit %s webhook: %s", event_type, exc)


async def _trigger_temporal_product_csv_ingestion() -> str:
    """Trigger Temporal workflow that ingests WANDS product.csv into catalog tables."""
    from temporalio.client import Client

    from services.pipeline.workflows import IngestWANDSWorkflow

    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"wands-ingestion-{uuid.uuid4().hex[:10]}"
    return await client.execute_workflow(
        IngestWANDSWorkflow.run,
        id=workflow_id,
        task_queue=TEMPORAL_TASK_QUEUE,
    )


async def _trigger_temporal_source_ingestion(
    *,
    source_type: str,
    source_config: dict[str, Any] | None = None,
) -> str:
    """Trigger Temporal workflow for source-adapter based ingestion."""
    from temporalio.client import Client

    from services.pipeline.workflows import IngestCatalogSourceWorkflow

    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"source-ingestion-{source_type}-{uuid.uuid4().hex[:10]}"
    return await client.execute_workflow(
        IngestCatalogSourceWorkflow.run,
        args=[source_type, source_config or {}],
        id=workflow_id,
        task_queue=TEMPORAL_TASK_QUEUE,
    )


class IngestSourceRequest(BaseModel):
    source_type: str = Field(default="csv")
    source_config: dict[str, Any] = Field(default_factory=dict)


def _rating_from_product(row: ProductRow) -> Optional[ProductRatingSummary]:
    attrs = row.attributes or {}
    avg_raw = attrs.get("average_rating") or attrs.get("rating")
    count_raw = attrs.get("rating_count") or attrs.get("ratings_count")
    dist_raw = attrs.get("rating_distribution") or attrs.get("distribution")

    if avg_raw in (None, "") or count_raw in (None, ""):
        return None

    try:
        average_rating = float(avg_raw)
        rating_count = int(count_raw)
    except (TypeError, ValueError):
        return None

    distribution: dict[str, int] = {}
    if isinstance(dist_raw, dict):
        for key, value in dist_raw.items():
            try:
                distribution[str(key)] = int(value)
            except (TypeError, ValueError):
                continue

    return ProductRatingSummary(
        product_id=row.id,
        average_rating=average_rating,
        rating_count=rating_count,
        distribution=distribution,
    )


def _product_info_from_row(row: ProductRow) -> ProductInfo:
    return ProductInfo(
        id=row.id,
        name=row.name,
        description=row.description or "",
        category=row.category or "",
        price=row.price_cents,
        currency=row.currency or "usd",
        image_url=row.image_url or "",
        in_stock=row.in_stock if row.in_stock is not None else True,
        attributes=row.attributes or {},
    )


async def _log_acp_action(
    db: AsyncSession,
    *,
    session_id: str,
    intent_type: ACPIntentType,
    input_payload: dict,
    idempotency_key: str,
    status: ACPExecutionStatus,
    result_ref: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    event = ACPActionEvent(
        action_id=f"act_{uuid.uuid4().hex[:12]}",
        timestamp=datetime.now(timezone.utc),
        session_id=session_id,
        actor=ACPActor(type="agent", id="commerce-assistant"),
        intent=ACPIntent(
            type=intent_type,
            confidence=1.0,
            user_utterance=f"{intent_type.value} via API",
        ),
        action=ACPAction(
            type=intent_type,
            input=input_payload,
            idempotency_key=idempotency_key,
        ),
        verification=ACPVerification(
            schema_valid=True,
            approved=(status == ACPExecutionStatus.SUCCEEDED),
            fail_reasons=[] if status == ACPExecutionStatus.SUCCEEDED else [error or "failed"],
        ),
        execution=ACPExecution(
            status=status,
            service="seller",
            latency_ms=0,
            result_ref=result_ref,
            error=error,
        ),
    )
    db.add(
        ACPActionEventRow(
            id=event.action_id,
            session_id=event.session_id,
            actor_type=event.actor.type,
            actor_id=event.actor.id,
            intent_type=event.intent.type.value,
            idempotency_key=event.action.idempotency_key,
            status=event.execution.status.value,
            event_data=event.model_dump(mode="json"),
        )
    )


# ── Seller Adapter Implementation ────────────────────────────────────────

class WayfairSellerAdapter(ACPSellerAdapter):
    """ACP seller adapter backed by the WANDS product catalog."""

    def _get_capabilities(self) -> Capabilities:
        return Capabilities(
            payment=Payment(
                handlers=[
                    PaymentHandler(
                        id="card_tokenized",
                        name="dev.acp.tokenized.card",
                        version="2026-01-30",
                        spec="https://acp.dev/handlers/tokenized.card",
                        requires_delegate_payment=True,
                        requires_pci_compliance=False,
                        psp="stripe",
                        config=PaymentHandlerConfig(
                            merchant_id=MERCHANT_ID,
                            accepted_brands=["visa", "mastercard", "amex", "discover"],
                            supports_3ds=True,
                        ),
                    )
                ]
            ),
            extensions=[ExtensionDeclaration(name="discount", extends=[])],
        )

    def _get_fulfillment_options(self) -> list:
        return [
            FulfillmentOptionShipping(
                type=FulfillmentType.SHIPPING,
                id="ship_std",
                title="Standard Shipping",
                subtitle="5-7 business days",
                carrier="UPS",
                subtotal=799,
                tax=math.ceil(799 * TAX_RATE),
                total=799 + math.ceil(799 * TAX_RATE),
            ),
            FulfillmentOptionShipping(
                type=FulfillmentType.SHIPPING,
                id="ship_exp",
                title="Express Shipping",
                subtitle="2-3 business days",
                carrier="FedEx",
                subtotal=1499,
                tax=math.ceil(1499 * TAX_RATE),
                total=1499 + math.ceil(1499 * TAX_RATE),
            ),
        ]

    async def _build_session(
        self,
        session_id: str,
        items: list,
        status: CheckoutStatus,
        buyer: Optional[dict] = None,
        fulfillment_address: Optional[dict] = None,
        fulfillment_option_id: Optional[str] = None,
    ) -> CheckoutSession:
        """Build a CheckoutSession by looking up products and calculating totals."""
        line_items = []
        subtotal = 0

        async with async_session() as db:
            for item_data in items:
                product = await db.get(ProductRow, item_data["id"])
                if not product:
                    raise ACPSellerError(
                        status_code=409,
                        error_type="invalid_request",
                        code="out_of_stock",
                        message=f"Product {item_data['id']} is not available",
                        param="$.items",
                    )

                if not product.in_stock:
                    raise ACPSellerError(
                        status_code=409,
                        error_type="invalid_request",
                        code="out_of_stock",
                        message=f"Product {item_data['id']} is out of stock",
                        param="$.items",
                    )

                qty = item_data.get("quantity", 1)
                base = product.price_cents * qty
                tax = math.ceil(base * TAX_RATE)
                line_items.append(
                    LineItem(
                        id=f"li_{product.id}",
                        item={"id": product.id, "quantity": qty},
                        base_amount=base,
                        discount=0,
                        subtotal=base,
                        tax=tax,
                        total=base + tax,
                    )
                )
                subtotal += base

        tax_total = math.ceil(subtotal * TAX_RATE)

        # Calculate fulfillment cost
        fulfillment_total = 0
        fulfillment_options = self._get_fulfillment_options()
        if fulfillment_option_id:
            for opt in fulfillment_options:
                if opt.id == fulfillment_option_id:
                    fulfillment_total = opt.total
                    break

        grand_total = subtotal + tax_total + fulfillment_total

        totals = [
            Total(type=TotalType.ITEMS_BASE_AMOUNT, display_text="Item(s) total", amount=subtotal),
            Total(type=TotalType.SUBTOTAL, display_text="Subtotal", amount=subtotal),
            Total(type=TotalType.TAX, display_text="Tax", amount=tax_total),
        ]
        if fulfillment_total:
            totals.append(
                Total(type=TotalType.FULFILLMENT, display_text="Shipping", amount=fulfillment_total)
            )
        totals.append(Total(type=TotalType.TOTAL, display_text="Total", amount=grand_total))

        from acp_framework.models import Address, Buyer

        return CheckoutSession(
            id=session_id,
            buyer=Buyer(**buyer) if buyer else None,
            payment_provider=PaymentProvider(provider="stripe", supported_payment_methods=["card"]),
            capabilities=self._get_capabilities(),
            status=status,
            currency="usd",
            line_items=line_items,
            fulfillment_address=Address(**fulfillment_address) if fulfillment_address else None,
            fulfillment_options=fulfillment_options,
            fulfillment_option_id=fulfillment_option_id,
            totals=totals,
            messages=[
                MessageInfo(type="info", code="checkout_state", content="Checkout session updated")
            ],
            links=[
                Link(type=LinkType.TERMS_OF_USE, url="https://example.com/terms"),
                Link(type=LinkType.PRIVACY_POLICY, url="https://example.com/privacy"),
            ],
        )

    async def on_create_session(self, request: CheckoutSessionCreateRequest) -> CheckoutSession:
        session_id = f"cs_{uuid.uuid4().hex[:12]}"
        items = [i.model_dump() for i in request.items]

        # Determine initial status
        has_address = request.fulfillment_address is not None
        status = (
            CheckoutStatus.READY_FOR_PAYMENT if has_address
            else CheckoutStatus.NOT_READY_FOR_PAYMENT
        )

        session = await self._build_session(
            session_id=session_id,
            items=items,
            status=status,
            buyer=request.buyer.model_dump() if request.buyer else None,
            fulfillment_address=(
                request.fulfillment_address.model_dump() if request.fulfillment_address else None
            ),
        )

        # Persist
        async with async_session() as db:
            row = CheckoutSessionRow(
                id=session_id,
                status=session.status.value,
                buyer=session.buyer.model_dump() if session.buyer else {},
                items=items,
                fulfillment_address=(
                    session.fulfillment_address.model_dump()
                    if session.fulfillment_address else None
                ),
                session_data=session.model_dump(),
            )
            db.add(row)
            await db.commit()

        return session

    async def on_get_session(self, session_id: str) -> CheckoutSession:
        async with async_session() as db:
            row = await db.get(CheckoutSessionRow, session_id)
            if not row:
                raise ACPSellerError(404, "not_found", "session_not_found", "Session not found")
            return CheckoutSession(**row.session_data)

    async def on_update_session(
        self, session_id: str, request: CheckoutSessionUpdateRequest
    ) -> CheckoutSession:
        async with async_session() as db:
            row = await db.get(CheckoutSessionRow, session_id)
            if not row:
                raise ACPSellerError(404, "not_found", "session_not_found", "Session not found")

            if row.status in ("completed", "canceled"):
                raise ACPSellerError(
                    409, "conflict", "session_terminal", "Session is already terminal"
                )

            items = (
                [i.model_dump() for i in request.items] if request.items else row.items
            )
            fulfillment_address = (
                request.fulfillment_address.model_dump()
                if request.fulfillment_address
                else row.fulfillment_address
            )
            fulfillment_option_id = request.fulfillment_option_id or row.fulfillment_option_id
            buyer = request.buyer.model_dump() if request.buyer else row.buyer

            # Determine status
            has_address = fulfillment_address is not None
            has_fulfillment = fulfillment_option_id is not None
            status = (
                CheckoutStatus.READY_FOR_PAYMENT
                if has_address and has_fulfillment
                else CheckoutStatus.NOT_READY_FOR_PAYMENT
            )

            session = await self._build_session(
                session_id=session_id,
                items=items,
                status=status,
                buyer=buyer,
                fulfillment_address=fulfillment_address,
                fulfillment_option_id=fulfillment_option_id,
            )

            row.status = session.status.value
            row.items = items
            row.buyer = buyer
            row.fulfillment_address = fulfillment_address
            row.fulfillment_option_id = fulfillment_option_id
            row.session_data = session.model_dump()
            await db.commit()

        return session

    async def on_complete_session(
        self, session_id: str, request: CheckoutSessionCompleteRequest
    ) -> CheckoutSessionWithOrder:
        async with async_session() as db:
            row = await db.get(CheckoutSessionRow, session_id)
            if not row:
                raise ACPSellerError(404, "not_found", "session_not_found", "Session not found")

            if row.status != "ready_for_payment":
                raise ACPSellerError(
                    409, "conflict", "not_ready",
                    f"Session is '{row.status}', must be 'ready_for_payment'"
                )

            if request.payment_data.token == "decline_token":
                raise ACPSellerError(
                    402,
                    "invalid_request",
                    "payment_declined",
                    "Payment was declined by issuer",
                    "$.payment_data.token",
                )

            # Create order
            order_id = f"order_{uuid.uuid4().hex[:12]}"
            session_data = row.session_data

            # Find total
            grand_total = 0
            for t in session_data.get("totals", []):
                if t.get("type") == "total":
                    grand_total = t.get("amount", 0)
                    break

            order_row = OrderRow(
                id=order_id,
                checkout_session_id=session_id,
                payment_token=request.payment_data.token,
                total_cents=grand_total,
                status="created",
                order_data={"payment_provider": request.payment_data.provider},
            )
            db.add(order_row)

            row.status = "completed"
            session_data["status"] = "completed"
            row.session_data = session_data
            await db.commit()

            await _emit_order_event(
                "order_created",
                {
                    "order_id": order_id,
                    "checkout_session_id": session_id,
                    "status": "created",
                    "total_cents": grand_total,
                    "currency": "usd",
                },
            )

            await _emit_order_event(
                "order_updated",
                {
                    "order_id": order_id,
                    "checkout_session_id": session_id,
                    "status": "confirmed",
                    "total_cents": grand_total,
                    "currency": "usd",
                },
            )

        return CheckoutSessionWithOrder(
            **{k: v for k, v in session_data.items() if k != "status"},
            status=CheckoutStatus.COMPLETED,
            order=Order(
                id=order_id,
                checkout_session_id=session_id,
                permalink_url=f"https://demo.example.com/orders/{order_id}",
            ),
        )

    async def on_cancel_session(self, session_id: str) -> CheckoutSession:
        async with async_session() as db:
            row = await db.get(CheckoutSessionRow, session_id)
            if not row:
                raise ACPSellerError(404, "not_found", "session_not_found", "Session not found")

            if row.status in ("completed", "canceled"):
                raise ACPSellerError(
                    405, "method_not_allowed", "already_terminal",
                    f"Session is already {row.status}"
                )

            row.status = "canceled"
            session_data = row.session_data
            session_data["status"] = "canceled"
            row.session_data = session_data
            await db.commit()

        return CheckoutSession(**session_data)


# ── FastAPI App ──────────────────────────────────────────────────────────

adapter = WayfairSellerAdapter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if AUTO_INGEST_ON_STARTUP:
        try:
            result = await _trigger_temporal_product_csv_ingestion()
            logger.info("Temporal ingestion completed on startup: %s", result)
        except Exception as exc:
            logger.warning("Startup Temporal ingestion failed: %s", exc)
    yield


app = FastAPI(
    title="ACP Seller Service — Wayfair Demo",
    description="ACP-compliant seller backed by the WANDS product catalog",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount the ACP checkout router
checkout_router = create_seller_router(adapter, require_auth=False)
app.include_router(checkout_router)


# ── Product Search endpoint (not ACP spec, but needed for agents) ────────

@app.get("/products/search")
async def search_endpoint(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None),
    price_min: Optional[int] = Query(None, description="Min price in cents"),
    price_max: Optional[int] = Query(None, description="Max price in cents"),
    idempotency_key: Optional[str] = Query(None, alias="idempotency_key"),
    db: AsyncSession = Depends(get_session),
):
    result = await search_products(
        db=db,
        query=q,
        limit=limit,
        category=category,
        price_min=price_min,
        price_max=price_max,
    )
    await _log_acp_action(
        db,
        session_id="search-session",
        intent_type=ACPIntentType.SEARCH,
        input_payload={
            "q": q,
            "limit": limit,
            "category": category,
            "price_min": price_min,
            "price_max": price_max,
        },
        idempotency_key=idempotency_key or f"search_{uuid.uuid4().hex[:10]}",
        status=ACPExecutionStatus.SUCCEEDED,
        result_ref="search",
    )
    await db.commit()
    return result.model_dump()


@app.get("/products/{product_id}", response_model=ProductInfo)
async def product_details_endpoint(product_id: str, db: AsyncSession = Depends(get_session)):
    product = await db.get(ProductRow, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_info_from_row(product)


@app.get("/ratings/{product_id}", response_model=ProductRatingSummary)
async def ratings_endpoint(product_id: str, db: AsyncSession = Depends(get_session)):
    product = await db.get(ProductRow, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    rating = _rating_from_product(product)
    if rating is None:
        raise HTTPException(status_code=404, detail="Ratings not available for product")
    return rating


@app.post("/compare", response_model=CompareProductsResponse)
async def compare_endpoint(
    body: CompareProductsRequest,
    db: AsyncSession = Depends(get_session),
    idempotency_key: Optional[str] = Query(None, alias="idempotency_key"),
):
    rows = []
    for product_id in body.product_ids:
        row = await db.get(ProductRow, product_id)
        if row:
            rows.append(row)

    if len(rows) < 2:
        raise HTTPException(status_code=422, detail="At least two valid product_ids are required")

    response = CompareProductsResponse(
        products=[
            ComparedProduct(
                id=row.id,
                name=row.name,
                category=row.category or "",
                price=row.price_cents,
                currency=row.currency or "usd",
                in_stock=row.in_stock if row.in_stock is not None else True,
                attributes=row.attributes or {},
                rating=_rating_from_product(row),
            )
            for row in rows
        ]
    )

    await _log_acp_action(
        db,
        session_id="compare-session",
        intent_type=ACPIntentType.COMPARE,
        input_payload=body.model_dump(),
        idempotency_key=idempotency_key or f"compare_{uuid.uuid4().hex[:10]}",
        status=ACPExecutionStatus.SUCCEEDED,
        result_ref="compare",
    )
    await db.commit()
    return response


@app.post("/admin/ingest/product-csv")
async def ingest_product_csv_endpoint():
    """Trigger Temporal ingestion using wayfair_data/product.csv as the primary source."""
    result = await _trigger_temporal_product_csv_ingestion()
    return {
        "status": "triggered",
        "source": "wayfair_data/product.csv",
        "result": result,
        "temporal_host": TEMPORAL_HOST,
        "task_queue": TEMPORAL_TASK_QUEUE,
    }


@app.post("/admin/ingest/source")
async def ingest_source_endpoint(body: IngestSourceRequest):
    """Trigger source-adapter ingestion (csv now, postgres_cdc scaffolded)."""
    result = await _trigger_temporal_source_ingestion(
        source_type=body.source_type,
        source_config=body.source_config,
    )
    return {
        "status": "triggered",
        "source_type": body.source_type,
        "source_config": body.source_config,
        "result": result,
        "temporal_host": TEMPORAL_HOST,
        "task_queue": TEMPORAL_TASK_QUEUE,
    }


@app.get("/admin/ingest/stats")
async def ingestion_stats_endpoint(
    run_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_session),
):
    """Get ingestion run stats for a specific run or the latest run."""
    if run_id:
        row = await db.get(IngestionRunRow, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Ingestion run not found")
    else:
        row = (
            await db.execute(
                select(IngestionRunRow)
                .order_by(IngestionRunRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="No ingestion runs found")

    return {
        "run_id": row.id,
        "source": row.source,
        "total_rows": row.total_rows,
        "valid_rows": row.valid_rows,
        "skipped_rows": row.skipped_rows,
        "skipped_missing_required": row.skipped_missing_required,
        "skipped_missing_price": row.skipped_missing_price,
        "loaded_rows": row.loaded_rows,
        "min_valid_ratio": row.min_valid_ratio,
        "actual_valid_ratio": row.actual_valid_ratio,
        "max_skipped_rows": row.max_skipped_rows,
        "status": row.status,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "details": row.run_data,
    }


@app.post("/purchase/simulate", response_model=PurchaseSimulateResponse)
async def purchase_simulate_endpoint(
    body: PurchaseSimulateRequest,
    db: AsyncSession = Depends(get_session),
    idempotency_key: Optional[str] = Query(None, alias="idempotency_key"),
):
    product = await db.get(ProductRow, body.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    subtotal = product.price_cents * body.quantity
    tax = math.ceil(subtotal * TAX_RATE)
    total = subtotal + tax

    response = PurchaseSimulateResponse(
        simulation_id=f"sim_{uuid.uuid4().hex[:12]}",
        product_id=body.product_id,
        quantity=body.quantity,
        currency=product.currency or "usd",
        subtotal=subtotal,
        tax=tax,
        total=total,
    )

    await _log_acp_action(
        db,
        session_id="purchase-sim-session",
        intent_type=ACPIntentType.PURCHASE,
        input_payload=body.model_dump(),
        idempotency_key=idempotency_key or f"purchase_{uuid.uuid4().hex[:10]}",
        status=ACPExecutionStatus.SUCCEEDED,
        result_ref=response.simulation_id,
    )
    await db.commit()
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "service": "seller"}
