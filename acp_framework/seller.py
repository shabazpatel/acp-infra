"""
ACP Seller Router Factory.

Provides `ACPSellerAdapter` (abstract base) and `create_seller_router()` to
auto-generate the 5 ACP checkout endpoints as a FastAPI APIRouter.

Usage:
    class MySellerAdapter(ACPSellerAdapter):
        async def on_create_session(self, request, ...) -> CheckoutSession: ...
        ...

    router = create_seller_router(MySellerAdapter())
    app.include_router(router)
"""

from __future__ import annotations

import abc
import hashlib
import hmac
import json
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from acp_framework.models import (
    ACPError,
    ACPErrorResponse,
    CheckoutSession,
    CheckoutSessionCompleteRequest,
    CheckoutSessionCreateRequest,
    CheckoutSessionUpdateRequest,
    CheckoutSessionWithOrder,
    CheckoutStatus,
)


class ACPSellerAdapter(abc.ABC):
    """
    Abstract base class that merchants implement to become ACP-compliant.

    Each hook receives the validated ACP request and should return the
    appropriate response object.  Raise `ACPSellerError` to return a
    structured ACP error to the agent.
    """

    @abc.abstractmethod
    async def on_create_session(
        self,
        request: CheckoutSessionCreateRequest,
    ) -> CheckoutSession:
        """Handle POST /checkout_sessions."""
        ...

    @abc.abstractmethod
    async def on_get_session(
        self,
        session_id: str,
    ) -> CheckoutSession:
        """Handle GET /checkout_sessions/{id}."""
        ...

    @abc.abstractmethod
    async def on_update_session(
        self,
        session_id: str,
        request: CheckoutSessionUpdateRequest,
    ) -> CheckoutSession:
        """Handle POST /checkout_sessions/{id}."""
        ...

    @abc.abstractmethod
    async def on_complete_session(
        self,
        session_id: str,
        request: CheckoutSessionCompleteRequest,
    ) -> CheckoutSessionWithOrder:
        """Handle POST /checkout_sessions/{id}/complete."""
        ...

    @abc.abstractmethod
    async def on_cancel_session(
        self,
        session_id: str,
    ) -> CheckoutSession:
        """Handle POST /checkout_sessions/{id}/cancel."""
        ...


class ACPSellerError(Exception):
    """Raise inside adapter hooks to return a structured ACP error."""

    def __init__(
        self,
        status_code: int,
        error_type: str,
        code: str,
        message: str,
        param: Optional[str] = None,
    ):
        self.status_code = status_code
        self.body = ACPErrorResponse(
            error=ACPError(type=error_type, code=code, message=message, param=param)
        )
        super().__init__(message)


SUPPORTED_API_VERSIONS = {
    v.strip() for v in os.getenv("ACP_SUPPORTED_API_VERSIONS", "2026-01-30").split(",") if v.strip()
}
SIGNATURE_SECRET = os.getenv("ACP_OPENAI_SIGNATURE_SECRET", "")
_IDEMPOTENCY_STORE: dict[tuple[str, str], dict] = {}


def _validate_api_version(api_version: Optional[str]) -> None:
    if not api_version:
        raise ACPSellerError(
            status_code=400,
            error_type="invalid_request",
            code="missing_api_version",
            message="Missing API-Version header",
            param="$.headers.API-Version",
        )
    if api_version not in SUPPORTED_API_VERSIONS:
        raise ACPSellerError(
            status_code=400,
            error_type="invalid_request",
            code="unsupported_api_version",
            message=f"Unsupported API-Version '{api_version}'",
            param="$.headers.API-Version",
        )


def _verify_signature(raw_body: bytes, signature: Optional[str]) -> None:
    if not SIGNATURE_SECRET:
        return
    if not signature:
        raise ACPSellerError(
            status_code=401,
            error_type="invalid_request",
            code="missing_signature",
            message="Missing X-OpenAI-Signature header",
            param="$.headers.X-OpenAI-Signature",
        )
    expected = hmac.new(SIGNATURE_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ACPSellerError(
            status_code=401,
            error_type="invalid_request",
            code="invalid_signature",
            message="Invalid X-OpenAI-Signature",
            param="$.headers.X-OpenAI-Signature",
        )


def _payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _apply_common_response_headers(response: Response, idempotency_key: Optional[str], request_id: Optional[str]) -> None:
    if idempotency_key:
        response.headers["Idempotency-Key"] = idempotency_key
    if request_id:
        response.headers["Request-Id"] = request_id


def _error_response(
    error: ACPSellerError,
    idempotency_key: Optional[str],
    request_id: Optional[str],
) -> JSONResponse:
    response = JSONResponse(status_code=error.status_code, content=error.body.model_dump())
    _apply_common_response_headers(response, idempotency_key, request_id)
    return response


def _idempotency_lookup(route: str, idempotency_key: Optional[str], payload_hash: str) -> Optional[JSONResponse]:
    if not idempotency_key:
        return None
    key = (route, idempotency_key)
    existing = _IDEMPOTENCY_STORE.get(key)
    if not existing:
        return None
    if existing["payload_hash"] != payload_hash:
        conflict = ACPSellerError(
            status_code=409,
            error_type="invalid_request",
            code="request_not_idempotent",
            message="Idempotency key reused with different request payload",
            param="$.headers.Idempotency-Key",
        )
        return _error_response(conflict, idempotency_key, existing.get("request_id"))
    replay = JSONResponse(status_code=existing["status_code"], content=existing["response_body"])
    _apply_common_response_headers(replay, idempotency_key, existing.get("request_id"))
    return replay


def _idempotency_store(
    route: str,
    idempotency_key: Optional[str],
    request_id: Optional[str],
    payload_hash: str,
    status_code: int,
    response_body: dict,
) -> None:
    if not idempotency_key:
        return
    _IDEMPOTENCY_STORE[(route, idempotency_key)] = {
        "request_id": request_id,
        "payload_hash": payload_hash,
        "status_code": status_code,
        "response_body": response_body,
    }


def _validate_bearer_token(authorization: Optional[str]) -> str:
    """Extract and validate bearer token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return authorization[7:]


def create_seller_router(
    adapter: ACPSellerAdapter,
    prefix: str = "",
    require_auth: bool = True,
) -> APIRouter:
    """
    Create a FastAPI APIRouter with all 5 ACP checkout endpoints wired
    to the given adapter.
    """
    router = APIRouter(prefix=prefix, tags=["ACP Checkout"])

    @router.post("/checkout_sessions", status_code=201, response_model=CheckoutSession)
    async def create_checkout_session(
        request: Request,
        response: Response,
        body: CheckoutSessionCreateRequest,
        authorization: Optional[str] = Header(None),
        api_version: Optional[str] = Header(None, alias="API-Version"),
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        request_id: Optional[str] = Header(None, alias="Request-Id"),
        x_openai_signature: Optional[str] = Header(None, alias="X-OpenAI-Signature"),
        accept_language: Optional[str] = Header(None, alias="Accept-Language"),
        user_agent: Optional[str] = Header(None, alias="User-Agent"),
    ):
        del accept_language, user_agent
        _validate_api_version(api_version)
        if require_auth:
            _validate_bearer_token(authorization)
        raw_body = await request.body()
        _verify_signature(raw_body, x_openai_signature)
        payload_hash = _payload_hash(body.model_dump(mode="json"))
        replay = _idempotency_lookup("POST:/checkout_sessions", idempotency_key, payload_hash)
        if replay:
            return replay
        try:
            session = await adapter.on_create_session(body)
            response_body = session.model_dump(mode="json")
            _idempotency_store(
                "POST:/checkout_sessions",
                idempotency_key,
                request_id,
                payload_hash,
                201,
                response_body,
            )
            _apply_common_response_headers(response, idempotency_key, request_id)
            return session
        except ACPSellerError as e:
            return _error_response(e, idempotency_key, request_id)

    @router.get("/checkout_sessions/{session_id}", response_model=CheckoutSession)
    async def get_checkout_session(
        request: Request,
        response: Response,
        session_id: str,
        authorization: Optional[str] = Header(None),
        api_version: Optional[str] = Header(None, alias="API-Version"),
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        request_id: Optional[str] = Header(None, alias="Request-Id"),
        x_openai_signature: Optional[str] = Header(None, alias="X-OpenAI-Signature"),
        accept_language: Optional[str] = Header(None, alias="Accept-Language"),
        user_agent: Optional[str] = Header(None, alias="User-Agent"),
    ):
        del accept_language, user_agent
        _validate_api_version(api_version)
        if require_auth:
            _validate_bearer_token(authorization)
        raw_body = await request.body()
        _verify_signature(raw_body, x_openai_signature)
        try:
            session = await adapter.on_get_session(session_id)
            _apply_common_response_headers(response, idempotency_key, request_id)
            return session
        except ACPSellerError as e:
            return _error_response(e, idempotency_key, request_id)

    @router.post("/checkout_sessions/{session_id}", response_model=CheckoutSession)
    async def update_checkout_session(
        request: Request,
        response: Response,
        session_id: str,
        body: CheckoutSessionUpdateRequest,
        authorization: Optional[str] = Header(None),
        api_version: Optional[str] = Header(None, alias="API-Version"),
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        request_id: Optional[str] = Header(None, alias="Request-Id"),
        x_openai_signature: Optional[str] = Header(None, alias="X-OpenAI-Signature"),
        accept_language: Optional[str] = Header(None, alias="Accept-Language"),
        user_agent: Optional[str] = Header(None, alias="User-Agent"),
    ):
        del accept_language, user_agent
        _validate_api_version(api_version)
        if require_auth:
            _validate_bearer_token(authorization)
        raw_body = await request.body()
        _verify_signature(raw_body, x_openai_signature)
        payload_hash = _payload_hash(body.model_dump(mode="json"))
        replay = _idempotency_lookup(
            f"POST:/checkout_sessions/{session_id}", idempotency_key, payload_hash
        )
        if replay:
            return replay
        try:
            session = await adapter.on_update_session(session_id, body)
            response_body = session.model_dump(mode="json")
            _idempotency_store(
                f"POST:/checkout_sessions/{session_id}",
                idempotency_key,
                request_id,
                payload_hash,
                200,
                response_body,
            )
            _apply_common_response_headers(response, idempotency_key, request_id)
            return session
        except ACPSellerError as e:
            return _error_response(e, idempotency_key, request_id)

    @router.post(
        "/checkout_sessions/{session_id}/complete",
        response_model=CheckoutSessionWithOrder,
    )
    async def complete_checkout_session(
        request: Request,
        response: Response,
        session_id: str,
        body: CheckoutSessionCompleteRequest,
        authorization: Optional[str] = Header(None),
        api_version: Optional[str] = Header(None, alias="API-Version"),
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        request_id: Optional[str] = Header(None, alias="Request-Id"),
        x_openai_signature: Optional[str] = Header(None, alias="X-OpenAI-Signature"),
        accept_language: Optional[str] = Header(None, alias="Accept-Language"),
        user_agent: Optional[str] = Header(None, alias="User-Agent"),
    ):
        del accept_language, user_agent
        _validate_api_version(api_version)
        if require_auth:
            _validate_bearer_token(authorization)
        raw_body = await request.body()
        _verify_signature(raw_body, x_openai_signature)
        payload_hash = _payload_hash(body.model_dump(mode="json"))
        replay = _idempotency_lookup(
            f"POST:/checkout_sessions/{session_id}/complete", idempotency_key, payload_hash
        )
        if replay:
            return replay
        try:
            result = await adapter.on_complete_session(session_id, body)
            response_body = result.model_dump(mode="json")
            _idempotency_store(
                f"POST:/checkout_sessions/{session_id}/complete",
                idempotency_key,
                request_id,
                payload_hash,
                200,
                response_body,
            )
            _apply_common_response_headers(response, idempotency_key, request_id)
            return result
        except ACPSellerError as e:
            return _error_response(e, idempotency_key, request_id)

    @router.post("/checkout_sessions/{session_id}/cancel", response_model=CheckoutSession)
    async def cancel_checkout_session(
        request: Request,
        response: Response,
        session_id: str,
        authorization: Optional[str] = Header(None),
        api_version: Optional[str] = Header(None, alias="API-Version"),
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        request_id: Optional[str] = Header(None, alias="Request-Id"),
        x_openai_signature: Optional[str] = Header(None, alias="X-OpenAI-Signature"),
        accept_language: Optional[str] = Header(None, alias="Accept-Language"),
        user_agent: Optional[str] = Header(None, alias="User-Agent"),
    ):
        del accept_language, user_agent
        _validate_api_version(api_version)
        if require_auth:
            _validate_bearer_token(authorization)
        raw_body = await request.body()
        _verify_signature(raw_body, x_openai_signature)
        payload_hash = _payload_hash({})
        replay = _idempotency_lookup(
            f"POST:/checkout_sessions/{session_id}/cancel", idempotency_key, payload_hash
        )
        if replay:
            return replay
        try:
            session = await adapter.on_cancel_session(session_id)
            response_body = session.model_dump(mode="json")
            _idempotency_store(
                f"POST:/checkout_sessions/{session_id}/cancel",
                idempotency_key,
                request_id,
                payload_hash,
                200,
                response_body,
            )
            _apply_common_response_headers(response, idempotency_key, request_id)
            return session
        except ACPSellerError as e:
            return _error_response(e, idempotency_key, request_id)

    return router
