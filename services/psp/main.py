"""
Mock PSP Service — Delegate Payment API.

Implements the ACP Delegate Payment spec. When STRIPE_API_KEY is set,
uses real Stripe tokenization; otherwise falls back to mock tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse

from acp_framework.models import (
    ACPError,
    ACPErrorResponse,
    DelegatePaymentRequest,
    DelegatePaymentResponse,
)
from acp_framework.payment import create_payment_provider


provider = create_payment_provider()
SUPPORTED_API_VERSIONS = {
    v.strip() for v in os.getenv("ACP_SUPPORTED_API_VERSIONS", "2026-01-30").split(",") if v.strip()
}
SIGNATURE_SECRET = os.getenv("ACP_OPENAI_SIGNATURE_SECRET", "")
_IDEMPOTENCY_STORE: dict[str, dict] = {}


def _payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _apply_common_response_headers(
    response: Response,
    idempotency_key: Optional[str],
    request_id: Optional[str],
) -> None:
    if idempotency_key:
        response.headers["Idempotency-Key"] = idempotency_key
    if request_id:
        response.headers["Request-Id"] = request_id


def _error_response(
    status_code: int,
    error: ACPError,
    idempotency_key: Optional[str],
    request_id: Optional[str],
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content=ACPErrorResponse(error=error).model_dump(),
    )
    _apply_common_response_headers(response, idempotency_key, request_id)
    return response


def _validate_api_version(api_version: Optional[str]) -> Optional[ACPError]:
    if not api_version:
        return ACPError(
            type="invalid_request",
            code="missing_api_version",
            message="Missing API-Version header",
            param="$.headers.API-Version",
        )
    if api_version not in SUPPORTED_API_VERSIONS:
        return ACPError(
            type="invalid_request",
            code="unsupported_api_version",
            message=f"Unsupported API-Version '{api_version}'",
            param="$.headers.API-Version",
        )
    return None


def _verify_signature(raw_body: bytes, signature: Optional[str]) -> Optional[ACPError]:
    if not SIGNATURE_SECRET:
        return None
    if not signature:
        return ACPError(
            type="invalid_request",
            code="missing_signature",
            message="Missing X-OpenAI-Signature header",
            param="$.headers.X-OpenAI-Signature",
        )
    expected = hmac.new(SIGNATURE_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return ACPError(
            type="invalid_request",
            code="invalid_signature",
            message="Invalid X-OpenAI-Signature",
            param="$.headers.X-OpenAI-Signature",
        )
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="ACP PSP Service — Delegate Payment",
    description="Delegate Payment API (mock or Stripe-backed)",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post(
    "/agentic_commerce/delegate_payment",
    status_code=201,
    response_model=DelegatePaymentResponse,
)
async def create_delegated_payment(
    request: Request,
    response: Response,
    body: DelegatePaymentRequest,
    authorization: Optional[str] = Header(None),
    api_version: Optional[str] = Header(None, alias="API-Version"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    request_id: Optional[str] = Header(None, alias="Request-Id"),
    x_openai_signature: Optional[str] = Header(None, alias="X-OpenAI-Signature"),
    accept_language: Optional[str] = Header(None, alias="Accept-Language"),
    user_agent: Optional[str] = Header(None, alias="User-Agent"),
):
    """
    Tokenize payment credentials and return a vault token with
    allowance constraints.
    """
    del accept_language, user_agent
    if not authorization or not authorization.startswith("Bearer "):
        return _error_response(
            401,
            ACPError(
                type="invalid_request",
                code="missing_authorization",
                message="Missing or invalid Authorization header",
                param="$.headers.Authorization",
            ),
            idempotency_key,
            request_id,
        )

    api_version_error = _validate_api_version(api_version)
    if api_version_error:
        return _error_response(400, api_version_error, idempotency_key, request_id)

    raw_body = await request.body()
    signature_error = _verify_signature(raw_body, x_openai_signature)
    if signature_error:
        return _error_response(401, signature_error, idempotency_key, request_id)

    payload_hash = _payload_hash(body.model_dump(mode="json"))
    if idempotency_key:
        existing = _IDEMPOTENCY_STORE.get(idempotency_key)
        if existing:
            if existing["payload_hash"] != payload_hash:
                return _error_response(
                    409,
                    ACPError(
                        type="invalid_request",
                        code="request_not_idempotent",
                        message="Idempotency key reused with different request payload",
                        param="$.headers.Idempotency-Key",
                    ),
                    idempotency_key,
                    request_id,
                )
            replay = JSONResponse(status_code=existing["status_code"], content=existing["response_body"])
            _apply_common_response_headers(replay, idempotency_key, existing.get("request_id"))
            return replay

    try:
        # Validate basic constraints
        if body.allowance.max_amount <= 0:
            return _error_response(
                422,
                ACPError(
                    type="invalid_request",
                    code="invalid_amount",
                    message="max_amount must be positive",
                    param="$.allowance.max_amount",
                ),
                idempotency_key,
                request_id,
            )

        if len(body.payment_method.number) < 13:
            return _error_response(
                400,
                ACPError(
                    type="invalid_request",
                    code="invalid_card",
                    message="Card number is too short",
                    param="$.payment_method.number",
                ),
                idempotency_key,
                request_id,
            )

        result = await provider.create_delegated_token(body)
        response_body = result.model_dump(mode="json")
        if idempotency_key:
            _IDEMPOTENCY_STORE[idempotency_key] = {
                "request_id": request_id,
                "payload_hash": payload_hash,
                "status_code": 201,
                "response_body": response_body,
            }
        _apply_common_response_headers(response, idempotency_key, request_id)
        return result

    except Exception as e:
        return _error_response(
            500,
            ACPError(
                type="api_error",
                code="internal_error",
                message=str(e),
            ),
            idempotency_key,
            request_id,
        )


@app.get("/health")
async def health():
    provider_type = type(provider).__name__
    return {"status": "ok", "service": "psp", "provider": provider_type}
