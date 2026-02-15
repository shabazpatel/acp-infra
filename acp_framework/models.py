"""
ACP Pydantic Models — matches the Agentic Commerce Protocol spec (2026-01-30).

These models cover both the Agentic Checkout API and the Delegate Payment API.
All monetary amounts are in the smallest currency unit (e.g. cents for USD).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CheckoutStatus(str, Enum):
    NOT_READY_FOR_PAYMENT = "not_ready_for_payment"
    READY_FOR_PAYMENT = "ready_for_payment"
    COMPLETED = "completed"
    CANCELED = "canceled"


class FulfillmentType(str, Enum):
    SHIPPING = "shipping"
    DIGITAL = "digital"
    PICKUP = "pickup"
    LOCAL_DELIVERY = "local_delivery"


class TotalType(str, Enum):
    ITEMS_BASE_AMOUNT = "items_base_amount"
    SUBTOTAL = "subtotal"
    TAX = "tax"
    FULFILLMENT = "fulfillment"
    DISCOUNT = "discount"
    TOTAL = "total"


class LinkType(str, Enum):
    TERMS_OF_USE = "terms_of_use"
    PRIVACY_POLICY = "privacy_policy"
    RETURN_POLICY = "return_policy"


class MessageLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Shared / Common
# ---------------------------------------------------------------------------

class Address(BaseModel):
    name: str
    line_one: str
    line_two: Optional[str] = None
    city: str
    state: str
    country: str
    postal_code: str


class Buyer(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone_number: Optional[str] = None


class Item(BaseModel):
    id: str
    quantity: int = Field(ge=1)


# ---------------------------------------------------------------------------
# Checkout — Line Items & Totals
# ---------------------------------------------------------------------------

class LineItem(BaseModel):
    id: str
    item: Item
    base_amount: int
    discount: int = 0
    subtotal: int
    tax: int = 0
    total: int


class Total(BaseModel):
    type: TotalType
    display_text: str
    amount: int


# ---------------------------------------------------------------------------
# Fulfillment Options
# ---------------------------------------------------------------------------

class FulfillmentOptionBase(BaseModel):
    type: FulfillmentType
    id: str
    title: str
    subtitle: Optional[str] = None
    subtotal: int = 0
    tax: int = 0
    total: int = 0


class FulfillmentOptionShipping(FulfillmentOptionBase):
    type: FulfillmentType = FulfillmentType.SHIPPING
    carrier: Optional[str] = None
    earliest_delivery_time: Optional[str] = None
    latest_delivery_time: Optional[str] = None


class FulfillmentOptionDigital(FulfillmentOptionBase):
    type: FulfillmentType = FulfillmentType.DIGITAL


# ---------------------------------------------------------------------------
# Capabilities — Payment Handlers, Interventions, Extensions
# ---------------------------------------------------------------------------

class PaymentHandlerConfig(BaseModel):
    merchant_id: Optional[str] = None
    accepted_brands: Optional[list[str]] = None
    supports_3ds: Optional[bool] = None


class PaymentHandler(BaseModel):
    id: str
    name: str
    version: str
    spec: Optional[str] = None
    requires_delegate_payment: bool = True
    requires_pci_compliance: bool = False
    psp: str = "stripe"
    config_schema: Optional[str] = None
    instrument_schemas: Optional[list[str]] = None
    config: Optional[PaymentHandlerConfig] = None


class InterventionCapabilities(BaseModel):
    supported: list[str] = []
    required: list[str] = []
    enforcement: str = "conditional"


class ExtensionDeclaration(BaseModel):
    name: str
    extends: list[str] = []


class Payment(BaseModel):
    handlers: list[PaymentHandler] = []


class Capabilities(BaseModel):
    payment: Optional[Payment] = None
    interventions: Optional[InterventionCapabilities] = None
    extensions: Optional[list[ExtensionDeclaration]] = None


# ---------------------------------------------------------------------------
# Messages & Links
# ---------------------------------------------------------------------------

class MessageInfo(BaseModel):
    type: MessageLevel = MessageLevel.INFO
    code: Optional[str] = None
    path: Optional[str] = None
    content_type: str = "plain"
    content: str


class PaymentProvider(BaseModel):
    provider: str
    supported_payment_methods: list[str] = ["card"]


class Link(BaseModel):
    type: LinkType
    url: str


# ---------------------------------------------------------------------------
# Payment Data (for checkout completion)
# ---------------------------------------------------------------------------

class PaymentData(BaseModel):
    token: str
    provider: str = "stripe"
    handler_id: Optional[str] = None
    billing_address: Optional[Address] = None


# ---------------------------------------------------------------------------
# Order (returned after successful checkout completion)
# ---------------------------------------------------------------------------

class Order(BaseModel):
    id: str
    checkout_session_id: str
    permalink_url: Optional[str] = None


class Refund(BaseModel):
    id: str
    amount: int
    currency: str
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Discount Extension
# ---------------------------------------------------------------------------

class Coupon(BaseModel):
    id: str
    name: str
    percent_off: Optional[float] = None
    amount_off: Optional[int] = None
    currency: Optional[str] = None
    duration: Optional[str] = None
    duration_in_months: Optional[int] = None
    max_redemptions: Optional[int] = None
    times_redeemed: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None


class DiscountAllocation(BaseModel):
    path: str
    amount: int


class AppliedDiscount(BaseModel):
    id: str
    code: Optional[str] = None
    coupon: Optional[Coupon] = None
    amount: int
    automatic: bool = False
    start: Optional[str] = None
    end: Optional[str] = None
    method: Optional[str] = None
    priority: Optional[int] = None
    allocations: list[DiscountAllocation] = []


class RejectedDiscount(BaseModel):
    code: str
    reason: str
    message: Optional[str] = None


class Discounts(BaseModel):
    codes: list[str] = []
    applied: list[AppliedDiscount] = []
    rejected: list[RejectedDiscount] = []


# ---------------------------------------------------------------------------
# Checkout Session (the core response object)
# ---------------------------------------------------------------------------

class CheckoutSessionBase(BaseModel):
    id: str
    buyer: Optional[Buyer] = None
    payment_provider: Optional[PaymentProvider] = None
    capabilities: Optional[Capabilities] = None
    status: CheckoutStatus = CheckoutStatus.NOT_READY_FOR_PAYMENT
    currency: str = "usd"
    line_items: list[LineItem] = []
    fulfillment_address: Optional[Address] = None
    fulfillment_options: list[FulfillmentOptionBase] = []
    fulfillment_option_id: Optional[str] = None
    totals: list[Total] = []
    messages: list[MessageInfo] = []
    links: list[Link] = []
    discounts: Optional[Discounts] = None


class CheckoutSession(CheckoutSessionBase):
    """Active checkout session (not yet completed)."""
    pass


class CheckoutSessionWithOrder(CheckoutSessionBase):
    """Completed checkout session with order details."""
    order: Optional[Order] = None


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class CheckoutSessionCreateRequest(BaseModel):
    buyer: Optional[Buyer] = None
    items: list[Item] = Field(min_length=1)
    fulfillment_address: Optional[Address] = None
    discounts: Optional[Discounts] = None


class CheckoutSessionUpdateRequest(BaseModel):
    buyer: Optional[Buyer] = None
    items: Optional[list[Item]] = None
    fulfillment_address: Optional[Address] = None
    fulfillment_option_id: Optional[str] = None
    discounts: Optional[Discounts] = None


class CheckoutSessionCompleteRequest(BaseModel):
    buyer: Optional[Buyer] = None
    payment_data: PaymentData


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ACPError(BaseModel):
    type: str
    code: str
    message: str
    param: Optional[str] = None


class ACPErrorResponse(BaseModel):
    error: ACPError


# ---------------------------------------------------------------------------
# Delegate Payment API Models
# ---------------------------------------------------------------------------

class PaymentMethodCard(BaseModel):
    type: str = "card"
    card_number_type: str = "network_token"  # "fpan" | "network_token"
    number: str
    exp_month: Optional[str] = None
    exp_year: Optional[str] = None
    name: Optional[str] = None
    cvc: Optional[str] = None
    checks_performed: Optional[dict[str, Any]] = None
    iin: Optional[str] = None
    display_card_funding_type: Optional[str] = None  # "credit" | "debit"
    display_brand: Optional[str] = None
    display_last4: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class Allowance(BaseModel):
    reason: str = "one_time"
    max_amount: int
    currency: str = "usd"
    checkout_session_id: Optional[str] = None
    merchant_id: Optional[str] = None
    expires_at: Optional[str] = None


class RiskSignal(BaseModel):
    type: str
    score: int
    action: str = "authorized"


class DelegatePaymentRequest(BaseModel):
    payment_method: PaymentMethodCard
    allowance: Allowance
    risk_signals: list[RiskSignal] = Field(min_length=1)
    metadata: Optional[dict[str, Any]] = None
    billing_address: Optional[Address] = None


class DelegatePaymentResponse(BaseModel):
    id: str
    created: str
    metadata: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Product Catalog Models (not part of ACP spec, but needed for seller search)
# ---------------------------------------------------------------------------

class ProductInfo(BaseModel):
    """Product model for seller catalogs (maps to ACP items)."""
    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: int  # in cents
    currency: str = "usd"
    image_url: Optional[str] = None
    in_stock: bool = True
    attributes: Optional[dict[str, Any]] = None


class ProductSearchResult(BaseModel):
    products: list[ProductInfo]
    total_count: int
    query: str


# ---------------------------------------------------------------------------
# Deterministic Catalog API Models
# ---------------------------------------------------------------------------

class ProductRatingSummary(BaseModel):
    product_id: str
    average_rating: float
    rating_count: int
    distribution: dict[str, int]


class CompareProductsRequest(BaseModel):
    product_ids: list[str] = Field(min_length=2, max_length=4)


class ComparedProduct(BaseModel):
    id: str
    name: str
    category: Optional[str] = None
    price: int
    currency: str = "usd"
    in_stock: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)
    rating: Optional[ProductRatingSummary] = None


class CompareProductsResponse(BaseModel):
    products: list[ComparedProduct]


class PurchaseSimulateRequest(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1)
    buyer_email: Optional[str] = None


class PurchaseSimulateResponse(BaseModel):
    simulation_id: str
    product_id: str
    quantity: int
    currency: str
    subtotal: int
    tax: int
    total: int


# ---------------------------------------------------------------------------
# ACP Action Contract (Intent -> Action -> Verification -> Execution)
# ---------------------------------------------------------------------------

class ACPIntentType(str, Enum):
    SEARCH = "search"
    COMPARE = "compare"
    PURCHASE = "purchase"


class ACPExecutionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class ACPActor(BaseModel):
    type: str
    id: str


class ACPIntent(BaseModel):
    type: ACPIntentType
    confidence: float = Field(ge=0.0, le=1.0)
    user_utterance: str


class ACPAction(BaseModel):
    type: ACPIntentType
    input: dict[str, Any]
    idempotency_key: str


class ACPVerification(BaseModel):
    schema_valid: bool
    resource_checks: list[str] = Field(default_factory=list)
    policy_checks: list[str] = Field(default_factory=list)
    approved: bool
    fail_reasons: list[str] = Field(default_factory=list)


class ACPExecution(BaseModel):
    status: ACPExecutionStatus
    service: str
    latency_ms: int = Field(ge=0)
    result_ref: Optional[str] = None
    error: Optional[str] = None


class ACPActionEvent(BaseModel):
    action_id: str
    timestamp: datetime
    session_id: str
    actor: ACPActor
    intent: ACPIntent
    action: ACPAction
    verification: ACPVerification
    execution: ACPExecution
