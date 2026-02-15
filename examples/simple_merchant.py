"""
Simple example showing how to use acp-framework to create an ACP-compliant merchant.

This minimal example shows the core pattern:
1. Install: pip install git+https://github.com/shabazpatel/acp-infra.git
2. Implement: Create adapter with your business logic
3. Deploy: Mount router in your FastAPI app
"""

from fastapi import FastAPI
from acp_framework import (
    ACPSellerAdapter,
    create_seller_router,
    CheckoutSession,
    CheckoutSessionCreateRequest,
    CheckoutSessionUpdateRequest,
    CheckoutSessionCompleteRequest,
    CheckoutSessionWithOrder,
    CheckoutStatus,
    Order,
)


class SimpleShopAdapter(ACPSellerAdapter):
    """
    Minimal adapter implementation showing required methods.
    In production, replace with calls to your actual systems.
    """

    async def on_create_session(
        self, request: CheckoutSessionCreateRequest
    ) -> CheckoutSession:
        """Create a new checkout session."""
        # TODO: Replace with your catalog/pricing logic
        session_id = f"cs_example_{id(request)}"

        return CheckoutSession(
            id=session_id,
            status=CheckoutStatus.NOT_READY_FOR_PAYMENT,
            currency="usd",
            line_items=[],  # Add your line items here
            fulfillment_options=[],  # Add shipping options
            totals=[],  # Add price breakdown
        )

    async def on_get_session(self, session_id: str) -> CheckoutSession:
        """Retrieve an existing checkout session."""
        # TODO: Load from your database
        raise NotImplementedError("Load session from your database")

    async def on_update_session(
        self, session_id: str, request: CheckoutSessionUpdateRequest
    ) -> CheckoutSession:
        """Update checkout (e.g., select shipping method)."""
        # TODO: Update in your database
        raise NotImplementedError("Update session in your database")

    async def on_complete_session(
        self, session_id: str, request: CheckoutSessionCompleteRequest
    ) -> CheckoutSessionWithOrder:
        """Complete checkout and create order."""
        # TODO: Process payment and create order
        order_id = f"order_example_{session_id}"

        return CheckoutSessionWithOrder(
            id=session_id,
            status=CheckoutStatus.COMPLETED,
            currency="usd",
            line_items=[],
            totals=[],
            order=Order(
                id=order_id,
                checkout_session_id=session_id,
                permalink_url=f"https://yourshop.com/orders/{order_id}",
            ),
        )

    async def on_cancel_session(self, session_id: str) -> CheckoutSession:
        """Cancel an active checkout session."""
        # TODO: Mark as canceled in your database
        raise NotImplementedError("Cancel session in your database")


# Create FastAPI app
app = FastAPI(title="Simple ACP Merchant")

# Mount ACP endpoints - this gives you 5 routes automatically:
# POST   /checkout_sessions
# GET    /checkout_sessions/{id}
# POST   /checkout_sessions/{id}
# POST   /checkout_sessions/{id}/complete
# POST   /checkout_sessions/{id}/cancel
adapter = SimpleShopAdapter()
acp_router = create_seller_router(adapter, require_auth=False)
app.include_router(acp_router)


@app.get("/")
async def root():
    return {
        "message": "Simple ACP Merchant",
        "endpoints": [
            "POST /checkout_sessions - Create checkout",
            "GET /checkout_sessions/{id} - Get checkout",
            "POST /checkout_sessions/{id} - Update checkout",
            "POST /checkout_sessions/{id}/complete - Complete order",
            "POST /checkout_sessions/{id}/cancel - Cancel checkout",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    print("Starting Simple ACP Merchant on http://localhost:8000")
    print("API docs at http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
