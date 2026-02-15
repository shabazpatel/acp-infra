"""
Source adapters for catalog ingestion.

This module defines a minimal abstraction layer so ingestion can evolve
from file-based snapshot loads to customer database CDC feeds.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass
class ChangeEvent:
    """Canonical catalog change event emitted by a source adapter."""

    op: Literal["upsert", "delete"]
    entity_id: str
    payload: dict[str, Any]
    source_cursor: str | None = None
    occurred_at: str | None = None


class CatalogSourceAdapter(Protocol):
    """Adapter contract for snapshot + incremental change retrieval."""

    async def snapshot_rows(self) -> list[dict[str, str]]:
        """Return a full snapshot of source rows for bootstrap ingestion."""

    async def poll_changes(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ChangeEvent], str | None]:
        """Return incremental change events and the next cursor/watermark."""


class CsvSnapshotAdapter:
    """Current source adapter based on WANDS product.csv snapshots."""

    def __init__(self, *, data_dir: str = "data", filename: str = "product.csv"):
        self.file_path = os.path.join(data_dir, filename)

    async def snapshot_rows(self) -> list[dict[str, str]]:
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Required source file not found: {self.file_path}")

        with open(self.file_path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    async def poll_changes(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ChangeEvent], str | None]:
        # CSV source is snapshot-based and does not currently support incremental CDC.
        return [], cursor


class PostgresCdcAdapter:
    """
    Placeholder adapter for customer Postgres CDC.

    Production implementation should consume logical replication / Debezium
    streams and return canonical ChangeEvent objects.
    """

    def __init__(self, *, dsn: str, slot_name: str, publication: str):
        self.dsn = dsn
        self.slot_name = slot_name
        self.publication = publication

    async def snapshot_rows(self) -> list[dict[str, str]]:
        raise NotImplementedError(
            "PostgresCdcAdapter.snapshot_rows is not implemented yet. "
            "Bootstrap strategy depends on customer schema and table mapping."
        )

    async def poll_changes(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ChangeEvent], str | None]:
        raise NotImplementedError(
            "PostgresCdcAdapter.poll_changes is not implemented yet. "
            "Implement CDC stream consumption and cursor checkpointing."
        )


def build_source_adapter(
    source_type: str,
    *,
    source_config: dict[str, Any] | None = None,
) -> CatalogSourceAdapter:
    """Factory for ingestion source adapters."""
    cfg = source_config or {}

    if source_type == "csv":
        return CsvSnapshotAdapter(
            data_dir=str(cfg.get("data_dir", "data")),
            filename=str(cfg.get("filename", "product.csv")),
        )

    if source_type == "postgres_cdc":
        return PostgresCdcAdapter(
            dsn=str(cfg.get("dsn", "")),
            slot_name=str(cfg.get("slot_name", "acp_slot")),
            publication=str(cfg.get("publication", "acp_publication")),
        )

    raise ValueError(f"Unsupported source_type: {source_type}")
