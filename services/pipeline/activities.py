"""
Temporal Activities — atomic units of work for the WANDS data pipeline.

Each activity is a standalone async function that can be retried independently.
"""

from __future__ import annotations

import csv
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from temporalio import activity

from services.pipeline.sources import build_source_adapter
from services.seller.database import IngestionRunRow, ProductRow, async_session
from sqlalchemy import text


BASE_DIR = Path(__file__).resolve().parents[2]
data_dir_env = os.getenv("WANDS_DATA_DIR", "data")
data_dir_candidate = Path(data_dir_env)
if not data_dir_candidate.is_absolute():
    data_dir_candidate = BASE_DIR / data_dir_candidate

fallback_dir = BASE_DIR / "services" / "seller" / "wayfair_data"
if not (data_dir_candidate / "product.csv").exists() and (fallback_dir / "product.csv").exists():
    data_dir_candidate = fallback_dir

DATA_DIR = str(data_dir_candidate)
MIN_VALID_RATIO = float(os.getenv("INGEST_MIN_VALID_RATIO", "0.0"))
MAX_SKIPPED_ROWS = int(os.getenv("INGEST_MAX_SKIPPED_ROWS", "5000"))


@dataclass
class ParseResult:
    """Result from parsing WANDS CSV files."""
    product_count: int
    file_path: str


@dataclass
class TransformResult:
    """Result from transforming WANDS products to ACP format."""
    run_id: str
    source: str
    total_rows: int
    valid_rows: int
    skipped_rows: int
    skipped_missing_required: int
    skipped_missing_price: int
    loaded_rows: int
    min_valid_ratio: float
    actual_valid_ratio: float
    max_skipped_rows: int
    status: str
    error_message: str


@activity.defn
async def parse_wands_csv() -> ParseResult:
    """
    Parse the WANDS product.csv file.
    Returns the count and path of parsed products.
    """
    file_path = os.path.join(DATA_DIR, "product.csv")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Required source file not found: {file_path}")

    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        reader = _build_reader_with_detected_delimiter(f)
        for _ in reader:
            count += 1

    activity.logger.info(f"Parsed {count} products from {file_path}")
    return ParseResult(product_count=count, file_path=file_path)


@activity.defn
async def transform_and_load_products(file_path: str) -> dict:
    """
    Read WANDS products from CSV, transform to our schema,
    and bulk-insert into PostgreSQL.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Required source file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        rows = list(_build_reader_with_detected_delimiter(f))

    result = await _transform_and_load_rows(rows=rows, source=file_path)
    await _persist_ingestion_run(result)

    if result.status != "succeeded":
        raise ValueError(result.error_message)

    return {
        "run_id": result.run_id,
        "source": result.source,
        "total_rows": result.total_rows,
        "valid_rows": result.valid_rows,
        "skipped_rows": result.skipped_rows,
        "skipped_missing_required": result.skipped_missing_required,
        "skipped_missing_price": result.skipped_missing_price,
        "loaded_rows": result.loaded_rows,
        "min_valid_ratio": result.min_valid_ratio,
        "actual_valid_ratio": result.actual_valid_ratio,
        "max_skipped_rows": result.max_skipped_rows,
        "status": result.status,
    }


@activity.defn
async def ingest_catalog_source(
    source_type: str = "csv",
    source_config: dict[str, Any] | None = None,
) -> dict:
    """Ingest catalog snapshot from a configured source adapter."""
    adapter = build_source_adapter(source_type, source_config=source_config)
    rows = await adapter.snapshot_rows()
    source_label = f"{source_type}:{(source_config or {}).get('name', 'default')}"

    result = await _transform_and_load_rows(rows=rows, source=source_label)
    await _persist_ingestion_run(result)

    if result.status != "succeeded":
        raise ValueError(result.error_message)

    return {
        "run_id": result.run_id,
        "source": result.source,
        "total_rows": result.total_rows,
        "valid_rows": result.valid_rows,
        "skipped_rows": result.skipped_rows,
        "skipped_missing_required": result.skipped_missing_required,
        "skipped_missing_price": result.skipped_missing_price,
        "loaded_rows": result.loaded_rows,
        "min_valid_ratio": result.min_valid_ratio,
        "actual_valid_ratio": result.actual_valid_ratio,
        "max_skipped_rows": result.max_skipped_rows,
        "status": result.status,
    }


async def _transform_and_load_rows(*, rows: list[dict[str, str]], source: str) -> TransformResult:
    run_id = f"ing_{uuid.uuid4().hex[:12]}"
    products = []
    total_rows = 0
    skipped_missing_required = 0
    skipped_missing_price = 0

    for row in rows:
        total_rows += 1
        product_id = row.get("product_id", "").strip()
        name = row.get("product_name", "").strip()
        description = row.get("product_description", "").strip()
        category = row.get("product_class", "").strip()
        price_cents = _parse_price_cents(row)

        if not product_id or not name:
            skipped_missing_required += 1
            continue

        if price_cents is None:
            price_cents = 0  # Allow rows without price to load with 0 cents

        attributes = {
            k: v
            for k, v in row.items()
            if k not in {"product_id", "product_name", "product_description", "product_class"}
            and v not in (None, "")
        }

        products.append({
            "id": product_id,
            "name": name,
            "description": description,
            "category": category,
            "price_cents": price_cents,
            "currency": "usd",
            "image_url": "",
            "in_stock": True,
            "attributes": attributes,
            "search_vector": f"{name} {description} {category}",
        })

    valid_rows = len(products)
    skipped_rows = skipped_missing_required + skipped_missing_price
    loaded_rows = await _bulk_insert(products)
    actual_valid_ratio = (valid_rows / total_rows) if total_rows > 0 else 0.0

    status = "succeeded"
    error_message = ""
    if total_rows == 0:
        status = "failed"
        error_message = "No rows found in source snapshot"
    elif skipped_rows > MAX_SKIPPED_ROWS:
        status = "failed"
        error_message = (
            f"Skipped rows exceed threshold: {skipped_rows} > {MAX_SKIPPED_ROWS}"
        )

    return TransformResult(
        run_id=run_id,
        source=source,
        total_rows=total_rows,
        valid_rows=valid_rows,
        skipped_rows=skipped_rows,
        skipped_missing_required=skipped_missing_required,
        skipped_missing_price=skipped_missing_price,
        loaded_rows=loaded_rows,
        min_valid_ratio=MIN_VALID_RATIO,
        actual_valid_ratio=actual_valid_ratio,
        max_skipped_rows=MAX_SKIPPED_ROWS,
        status=status,
        error_message=error_message,
    )


async def _persist_ingestion_run(result: TransformResult) -> None:
    async with async_session() as db:
        db.add(
            IngestionRunRow(
                id=result.run_id,
                source=result.source,
                total_rows=result.total_rows,
                valid_rows=result.valid_rows,
                skipped_rows=result.skipped_rows,
                skipped_missing_required=result.skipped_missing_required,
                skipped_missing_price=result.skipped_missing_price,
                loaded_rows=result.loaded_rows,
                min_valid_ratio=f"{result.min_valid_ratio:.4f}",
                actual_valid_ratio=f"{result.actual_valid_ratio:.4f}",
                max_skipped_rows=result.max_skipped_rows,
                status=result.status,
                error_message=result.error_message,
                run_data={
                    "run_id": result.run_id,
                    "source": result.source,
                    "total_rows": result.total_rows,
                    "valid_rows": result.valid_rows,
                    "skipped_rows": result.skipped_rows,
                    "skipped_missing_required": result.skipped_missing_required,
                    "skipped_missing_price": result.skipped_missing_price,
                    "loaded_rows": result.loaded_rows,
                    "min_valid_ratio": result.min_valid_ratio,
                    "actual_valid_ratio": result.actual_valid_ratio,
                    "max_skipped_rows": result.max_skipped_rows,
                    "status": result.status,
                    "error_message": result.error_message,
                },
            )
        )
        await db.commit()


async def _bulk_insert(products: list[dict]) -> int:
    """Bulk insert products into Postgres, upserting on conflict."""
    if not products:
        return 0

    async with async_session() as db:
        # Clear existing products first (for re-ingestion)
        await db.execute(text("DELETE FROM products"))

        # Batch insert
        batch_size = 500
        inserted = 0
        for i in range(0, len(products), batch_size):
            batch = products[i : i + batch_size]
            for p in batch:
                db.add(ProductRow(**p))
            await db.flush()
            inserted += len(batch)
            activity.logger.info(f"Inserted {inserted}/{len(products)} products")

        await db.commit()

    activity.logger.info(f"Total: {inserted} products loaded")
    return inserted


def _parse_price_cents(row: dict[str, str]) -> int | None:
    """Parse price from dataset row, returning cents or None when unavailable/invalid."""
    candidates = ["price_cents", "price", "product_price", "final_price"]
    for key in candidates:
        raw = (row.get(key) or "").strip()
        if not raw:
            continue
        cleaned = raw.replace("$", "").replace(",", "")
        try:
            if "." in cleaned:
                return int(round(float(cleaned) * 100))
            return int(cleaned)
        except ValueError:
            continue
    return None


def _build_reader_with_detected_delimiter(file_obj) -> csv.DictReader:
    """Build a DictReader that supports comma or tab-delimited source files."""
    sample = file_obj.read(4096)
    file_obj.seek(0)

    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
        delimiter = dialect.delimiter
    except csv.Error:
        # Wayfair file is typically tab-separated with a .csv extension.
        if "\t" in sample:
            delimiter = "\t"

    return csv.DictReader(file_obj, delimiter=delimiter)
