"""
ACP Agent Tools — @function_tool wrappers for OpenAI Agents SDK.

These tools let any OpenAI Agent interact with ACP-compliant sellers
and payment providers. Each tool is a typed async function that the
agent can call during its run loop.

Usage with OpenAI Agents SDK:
    from agents import Agent
    from acp_framework.agent import create_commerce_tools

    tools = create_commerce_tools(seller_url="http://localhost:8001")
    agent = Agent(name="shopper", tools=tools, instructions="...")
"""

from __future__ import annotations

import httpx
from agents import function_tool
from pydantic import ValidationError

from acp_framework.models import (
    CompareProductsResponse,
    CheckoutSession,
    CheckoutSessionWithOrder,
    ProductInfo,
    ProductRatingSummary,
    ProductSearchResult,
    PurchaseSimulateResponse,
)


def create_commerce_tools(
    seller_url: str,
    psp_url: str = "",
    auth_token: str = "demo-token",
) -> list:
    """
    Create a list of @function_tool-decorated functions that an OpenAI
    Agent can use to search products and manage ACP checkout sessions.
    """

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "API-Version": "2026-01-30",
    }

    def _validate_json_response(model_cls, data: dict):
        try:
            return model_cls.model_validate(data).model_dump(mode="json")
        except ValidationError as exc:
            raise RuntimeError(f"Invalid response from seller service: {exc}") from exc

    @function_tool
    async def search_products(query: str, max_results: int = 5) -> dict:
        """
        Search the seller's product catalog by keyword.

        Args:
            query: Natural language search query (e.g. "blue velvet sofa")
            max_results: Maximum number of products to return (default 5)

        Returns:
            JSON string with matching products including id, name, price, and description.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{seller_url}/products/search",
                params={"q": query, "limit": max_results},
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(ProductSearchResult, resp.json())

    @function_tool
    async def get_product_details(product_id: str) -> dict:
        """Get deterministic product details by ID."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{seller_url}/products/{product_id}",
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(ProductInfo, resp.json())

    @function_tool
    async def get_product_rating(product_id: str) -> dict:
        """Get deterministic rating summary for a product."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{seller_url}/ratings/{product_id}",
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(ProductRatingSummary, resp.json())

    @function_tool
    async def compare_products(product_ids: list[str]) -> dict:
        """Compare 2-4 products side-by-side."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{seller_url}/compare",
                json={"product_ids": product_ids},
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(CompareProductsResponse, resp.json())

    @function_tool
    async def simulate_purchase(product_id: str, quantity: int = 1, buyer_email: str = "") -> dict:
        """Simulate a purchase deterministically without creating a real order."""
        payload: dict = {
            "product_id": product_id,
            "quantity": quantity,
        }
        if buyer_email:
            payload["buyer_email"] = buyer_email

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{seller_url}/purchase/simulate",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(PurchaseSimulateResponse, resp.json())

    @function_tool
    async def create_checkout(
        product_id: str,
        quantity: int = 1,
        buyer_first_name: str = "",
        buyer_last_name: str = "",
        buyer_email: str = "",
        address_line_one: str = "",
        address_city: str = "",
        address_state: str = "",
        address_country: str = "US",
        address_postal_code: str = "",
    ) -> dict:
        """
        Create a new ACP checkout session with the selected product.

        Args:
            product_id: The product ID to purchase
            quantity: Number of items
            buyer_first_name: Buyer's first name
            buyer_last_name: Buyer's last name
            buyer_email: Buyer's email address
            address_line_one: Street address
            address_city: City
            address_state: State/province
            address_country: Country code (default US)
            address_postal_code: ZIP/postal code

        Returns:
            JSON string with the checkout session details including session ID,
            line items, totals, and available fulfillment options.
        """
        payload: dict = {
            "items": [{"id": product_id, "quantity": quantity}],
        }
        # Only include buyer if all required buyer fields are non-empty
        if buyer_first_name and buyer_last_name and buyer_email:
            payload["buyer"] = {
                "first_name": buyer_first_name,
                "last_name": buyer_last_name,
                "email": buyer_email,
            }
        # Only include fulfillment_address if all required address fields are non-empty
        if address_line_one and address_city and address_state and address_postal_code:
            payload["fulfillment_address"] = {
                "name": f"{buyer_first_name} {buyer_last_name}" if buyer_first_name else "Customer",
                "line_one": address_line_one,
                "city": address_city,
                "state": address_state,
                "country": address_country,
                "postal_code": address_postal_code,
            }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{seller_url}/checkout_sessions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(CheckoutSession, resp.json())

    @function_tool
    async def update_checkout(
        session_id: str,
        fulfillment_option_id: str = "",
        product_id: str = "",
        quantity: int = 0,
    ) -> dict:
        """
        Update an existing checkout session — e.g. select a shipping option
        or change the item quantity.

        Args:
            session_id: The checkout session ID
            fulfillment_option_id: ID of the fulfillment option to select
            product_id: Product ID if changing items
            quantity: New quantity if changing items

        Returns:
            JSON string with the updated checkout session state.
        """
        payload: dict = {}
        if fulfillment_option_id:
            payload["fulfillment_option_id"] = fulfillment_option_id
        if product_id and quantity > 0:
            payload["items"] = [{"id": product_id, "quantity": quantity}]

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{seller_url}/checkout_sessions/{session_id}",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(CheckoutSession, resp.json())

    @function_tool
    async def get_checkout_status(session_id: str) -> dict:
        """
        Get the current state of a checkout session.

        Args:
            session_id: The checkout session ID

        Returns:
            JSON string with the current checkout session state, including
            status, line items, totals, and fulfillment options.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{seller_url}/checkout_sessions/{session_id}",
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(CheckoutSession, resp.json())

    @function_tool
    async def complete_checkout(session_id: str, payment_token: str = "mock_token") -> dict:
        """
        Complete the checkout by processing payment. The session must be in
        'ready_for_payment' status.

        Args:
            session_id: The checkout session ID
            payment_token: Payment token from the PSP (use 'mock_token' for demo)

        Returns:
            JSON string with the completed checkout session including order details.
        """
        payload = {
            "payment_data": {
                "token": payment_token,
                "provider": "stripe",
            }
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{seller_url}/checkout_sessions/{session_id}/complete",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(CheckoutSessionWithOrder, resp.json())

    @function_tool
    async def cancel_checkout(session_id: str) -> dict:
        """
        Cancel an active checkout session.

        Args:
            session_id: The checkout session ID to cancel

        Returns:
            JSON string with the canceled checkout session state.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{seller_url}/checkout_sessions/{session_id}/cancel",
                headers=headers,
            )
            resp.raise_for_status()
            return _validate_json_response(CheckoutSession, resp.json())

    return [
        search_products,
        get_product_details,
        get_product_rating,
        compare_products,
        simulate_purchase,
        create_checkout,
        update_checkout,
        get_checkout_status,
        complete_checkout,
        cancel_checkout,
    ]
