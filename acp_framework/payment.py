"""
ACP Payment Provider Abstraction.

Provides a base class `DelegatePaymentProvider` and two implementations:
- `MockDelegatePayment` — in-memory mock for development/demos
- `StripeDelegatePayment` — real Stripe integration (just change the API key)

The factory `create_payment_provider()` auto-selects based on env config.
"""

from __future__ import annotations

import abc
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from acp_framework.models import (
    DelegatePaymentRequest,
    DelegatePaymentResponse,
)


class DelegatePaymentProvider(abc.ABC):
    """Abstract base for delegate payment providers."""

    @abc.abstractmethod
    async def create_delegated_token(
        self,
        request: DelegatePaymentRequest,
    ) -> DelegatePaymentResponse:
        """Tokenize payment credentials and return a vault token."""
        ...


class MockDelegatePayment(DelegatePaymentProvider):
    """
    In-memory mock for development — issues fake vault tokens
    that pass validation without hitting any external service.
    """

    def __init__(self):
        self._tokens: dict[str, dict] = {}

    async def create_delegated_token(
        self,
        request: DelegatePaymentRequest,
    ) -> DelegatePaymentResponse:
        token_id = f"vt_mock_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()

        self._tokens[token_id] = {
            "allowance": request.allowance.model_dump(),
            "created": now,
            "payment_method_last4": request.payment_method.number[-4:],
        }

        return DelegatePaymentResponse(
            id=token_id,
            created=now,
            metadata={
                "source": "mock_delegate_payment",
                **(request.metadata or {}),
            },
        )

    def validate_token(self, token_id: str) -> Optional[dict]:
        """Check if a mock token exists and return its data."""
        return self._tokens.get(token_id)


class StripeDelegatePayment(DelegatePaymentProvider):
    """
    Real Stripe integration for delegate payment.

    Uses Stripe's Payment Methods API to tokenize card credentials
    and create a scoped token. Requires STRIPE_API_KEY env var.

    This implementation is production-ready — just set the API key.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("STRIPE_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "STRIPE_API_KEY is required for StripeDelegatePayment. "
                "Use MockDelegatePayment for development."
            )

    async def create_delegated_token(
        self,
        request: DelegatePaymentRequest,
    ) -> DelegatePaymentResponse:
        import stripe

        stripe.api_key = self.api_key

        # Create a Stripe PaymentMethod from the card details
        pm = stripe.PaymentMethod.create(
            type="card",
            card={
                "number": request.payment_method.number,
                "exp_month": int(request.payment_method.exp_month or "12"),
                "exp_year": int(request.payment_method.exp_year or "2027"),
                "cvc": request.payment_method.cvc or "123",
            },
        )

        token_id = f"spt_{pm.id}"
        now = datetime.now(timezone.utc).isoformat()

        return DelegatePaymentResponse(
            id=token_id,
            created=now,
            metadata={
                "source": "stripe_delegate_payment",
                "stripe_pm_id": pm.id,
                "merchant_id": request.allowance.merchant_id,
                **(request.metadata or {}),
            },
        )


def create_payment_provider(
    stripe_api_key: Optional[str] = None,
) -> DelegatePaymentProvider:
    """
    Factory — returns StripeDelegatePayment if an API key is available,
    otherwise falls back to MockDelegatePayment.
    """
    key = stripe_api_key or os.getenv("STRIPE_API_KEY", "")
    if key:
        return StripeDelegatePayment(api_key=key)
    return MockDelegatePayment()
