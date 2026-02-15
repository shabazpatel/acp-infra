"""
ACP Framework — Reusable Agentic Commerce Protocol library.

This framework enables merchants to become ACP-compliant and allows
AI agents to complete purchases through standardized APIs.

Example usage for merchants:
    from acp_framework import ACPSellerAdapter, create_seller_router

    class MyShopAdapter(ACPSellerAdapter):
        async def on_create_session(self, request):
            # Your checkout logic
            ...

    app.include_router(create_seller_router(MyShopAdapter()))

Example usage for agents:
    from acp_framework import create_commerce_tools

    tools = create_commerce_tools(seller_url="https://merchant.com")
    agent = Agent(tools=tools, ...)
"""

__version__ = "0.1.0"

# Export main models
from acp_framework.models import (
    CheckoutSession,
    CheckoutSessionCreateRequest,
    CheckoutSessionUpdateRequest,
    CheckoutSessionCompleteRequest,
    CheckoutSessionWithOrder,
    CheckoutStatus,
    Order,
    LineItem,
    Total,
    TotalType,
    Buyer,
    Address,
    Payment,
    PaymentData,
    PaymentHandler,
    FulfillmentOptionShipping,
    FulfillmentType,
    ProductInfo,
    ProductSearchResult,
    DelegatePaymentRequest,
    DelegatePaymentResponse,
)

# Export seller components
from acp_framework.seller import (
    ACPSellerAdapter,
    ACPSellerError,
    create_seller_router,
)

# Export agent tools
from acp_framework.agent import create_commerce_tools

__all__ = [
    "__version__",
    # Core Models
    "CheckoutSession",
    "CheckoutSessionCreateRequest",
    "CheckoutSessionUpdateRequest",
    "CheckoutSessionCompleteRequest",
    "CheckoutSessionWithOrder",
    "CheckoutStatus",
    "Order",
    "LineItem",
    "Total",
    "TotalType",
    "Buyer",
    "Address",
    "Payment",
    "PaymentData",
    "PaymentHandler",
    "FulfillmentOptionShipping",
    "FulfillmentType",
    "ProductInfo",
    "ProductSearchResult",
    "DelegatePaymentRequest",
    "DelegatePaymentResponse",
    # Seller Components
    "ACPSellerAdapter",
    "ACPSellerError",
    "create_seller_router",
    # Agent Components
    "create_commerce_tools",
]
