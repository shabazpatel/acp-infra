"""
Temporal Worker — registers workflows and activities, then runs.

Usage:
    python -m services.pipeline.worker
"""

from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from services.pipeline.activities import ingest_catalog_source, parse_wands_csv, transform_and_load_products
from services.pipeline.workflows import IngestCatalogSourceWorkflow, IngestWANDSWorkflow
from services.seller.database import init_db


TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "acp-pipeline"


async def run_worker():
    """Start the Temporal worker and optionally trigger ingestion."""
    # Initialize database tables
    await init_db()

    # Connect to Temporal
    client = await Client.connect(TEMPORAL_HOST)

    # Create and run the worker
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[IngestWANDSWorkflow, IngestCatalogSourceWorkflow],
        activities=[parse_wands_csv, transform_and_load_products, ingest_catalog_source],
    )

    print(f"🏭 Temporal worker started on queue '{TASK_QUEUE}'")
    print(f"   Connected to: {TEMPORAL_HOST}")
    await worker.run()


async def trigger_ingestion():
    """Trigger the WANDS ingestion workflow."""
    client = await Client.connect(TEMPORAL_HOST)

    result = await client.execute_workflow(
        IngestWANDSWorkflow.run,
        id="wands-ingestion",
        task_queue=TASK_QUEUE,
    )
    print(f"✅ {result}")
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "trigger":
        asyncio.run(trigger_ingestion())
    else:
        asyncio.run(run_worker())
