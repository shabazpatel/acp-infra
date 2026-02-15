"""
Agent Service — FastAPI app with chat endpoint.

Exposes the commerce agent via REST API for the demo UI.
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.agent.commerce_agent import run_agent_with_memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="ACP Agent Service",
    description="AI-powered commerce agent using OpenAI Agents SDK",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow CORS for the demo UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    user_id: str
    session_id: str
    checkout_session_id: str | None = None


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the commerce agent and get a response."""
    session_id = request.session_id or f"sess_{uuid.uuid4().hex[:8]}"

    response = await run_agent_with_memory(
        user_message=request.message,
        user_id=request.user_id,
        session_id=session_id,
    )

    checkout_session_id = None
    match = re.search(r"cs_[a-f0-9]+", response)
    if match:
        checkout_session_id = match.group(0)

    return ChatResponse(
        response=response,
        user_id=request.user_id,
        session_id=session_id,
        checkout_session_id=checkout_session_id,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent"}
