"""
Database models and connection for the Seller Service.

Uses async SQLAlchemy with asyncpg for PostgreSQL.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://acp:acp@localhost:5432/acp",
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ── Product catalog ──────────────────────────────────────────────────────

class ProductRow(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    category = Column(String, default="")
    price_cents = Column(Integer, nullable=False)
    currency = Column(String, default="usd")
    image_url = Column(String, default="")
    in_stock = Column(Boolean, default=True)
    attributes = Column(JSONB, default=dict)
    # Postgres full-text search vector — populated via trigger or on insert
    search_vector = Column(
        Text,
        default="",
        doc="Concatenated searchable text (name + description + category)",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Checkout sessions ────────────────────────────────────────────────────

class CheckoutSessionRow(Base):
    __tablename__ = "checkout_sessions"

    id = Column(String, primary_key=True)
    status = Column(String, default="not_ready_for_payment")
    buyer = Column(JSONB, default=dict)
    items = Column(JSONB, default=list)
    fulfillment_address = Column(JSONB, nullable=True)
    fulfillment_option_id = Column(String, nullable=True)
    session_data = Column(JSONB, default=dict)  # full CheckoutSession JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Orders ───────────────────────────────────────────────────────────────

class OrderRow(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    checkout_session_id = Column(String, nullable=False)
    payment_token = Column(String, default="")
    total_cents = Column(Integer, default=0)
    currency = Column(String, default="usd")
    status = Column(String, default="created")
    order_data = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── ACP Action Audit Log ──────────────────────────────────────────────────

class ACPActionEventRow(Base):
    __tablename__ = "acp_action_events"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False)
    actor_type = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    intent_type = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    status = Column(String, nullable=False)
    event_data = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Ingestion Run Stats ───────────────────────────────────────────────────

class IngestionRunRow(Base):
    __tablename__ = "ingestion_runs"

    id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    total_rows = Column(Integer, default=0)
    valid_rows = Column(Integer, default=0)
    skipped_rows = Column(Integer, default=0)
    skipped_missing_required = Column(Integer, default=0)
    skipped_missing_price = Column(Integer, default=0)
    loaded_rows = Column(Integer, default=0)
    min_valid_ratio = Column(String, default="0.0")
    actual_valid_ratio = Column(String, default="0.0")
    max_skipped_rows = Column(Integer, default=0)
    status = Column(String, nullable=False)
    error_message = Column(Text, default="")
    run_data = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Source Connections + Checkpoints (CDC scaffold) ──────────────────────

class SourceConnectionRow(Base):
    __tablename__ = "source_connections"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # csv | postgres_cdc
    status = Column(String, nullable=False, default="active")
    source_config = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SourceCheckpointRow(Base):
    __tablename__ = "source_checkpoints"

    source_id = Column(String, primary_key=True)
    cursor = Column(String, default="")
    last_event_at = Column(String, default="")
    checkpoint_data = Column("metadata", JSONB, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Helpers ──────────────────────────────────────────────────────────────

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def init_db():
    """Create all tables (for development — use Alembic for production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
