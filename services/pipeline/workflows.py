"""
Temporal Workflows — durable, orchestrated multi-step processes.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from services.pipeline.activities import (
        ParseResult,
        ingest_catalog_source,
        parse_wands_csv,
        transform_and_load_products,
    )


@workflow.defn
class IngestWANDSWorkflow:
    """
    Ingest the Wayfair WANDS dataset into the product catalog.

    Steps:
    1. Parse the WANDS CSV files
    2. Transform products to ACP schema and bulk-load into Postgres
    """

    @workflow.run
    async def run(self) -> str:
        workflow.logger.info("Starting WANDS data ingestion")

        # Step 1: Parse the CSV
        parse_result: ParseResult = await workflow.execute_activity(
            parse_wands_csv,
            start_to_close_timeout=timedelta(minutes=5),
        )
        workflow.logger.info(f"Parsed {parse_result.product_count} products")

        # Step 2: Transform and load
        stats: dict = await workflow.execute_activity(
            transform_and_load_products,
            args=[parse_result.file_path],
            start_to_close_timeout=timedelta(minutes=10),
        )

        summary = (
            "Ingestion complete: "
            f"run_id={stats.get('run_id')} "
            f"loaded={stats.get('loaded_rows')} "
            f"valid={stats.get('valid_rows')}/{stats.get('total_rows')} "
            f"skipped={stats.get('skipped_rows')}"
        )
        workflow.logger.info(summary)
        return summary


@workflow.defn
class IngestCatalogSourceWorkflow:
    """Ingest from a named source adapter (csv today, postgres_cdc scaffolded)."""

    @workflow.run
    async def run(
        self,
        source_type: str = "csv",
        source_config: dict[str, Any] | None = None,
    ) -> str:
        workflow.logger.info("Starting catalog source ingestion")

        stats: dict = await workflow.execute_activity(
            ingest_catalog_source,
            args=[source_type, source_config],
            start_to_close_timeout=timedelta(minutes=10),
        )

        summary = (
            "Source ingestion complete: "
            f"source={stats.get('source')} "
            f"run_id={stats.get('run_id')} "
            f"loaded={stats.get('loaded_rows')} "
            f"valid={stats.get('valid_rows')}/{stats.get('total_rows')} "
            f"skipped={stats.get('skipped_rows')}"
        )
        workflow.logger.info(summary)
        return summary
