"""
Product search using PostgreSQL full-text search.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from acp_framework.models import ProductInfo, ProductSearchResult
from services.seller.database import ProductRow


async def search_products(
    db: AsyncSession,
    query: str,
    limit: int = 10,
    category: Optional[str] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
) -> ProductSearchResult:
    """
    Full-text search over the product catalog using Postgres.
    Falls back to ILIKE if the query is very short.
    """
    conditions = ["1=1"]
    params: dict = {"limit": limit}

    if len(query.strip()) >= 3:
        # Use Postgres full-text search
        conditions.append(
            "to_tsvector('english', name || ' ' || description || ' ' || category) "
            "@@ plainto_tsquery('english', :query)"
        )
        params["query"] = query
        order_by = (
            "ts_rank(to_tsvector('english', name || ' ' || description || ' ' || category), "
            "plainto_tsquery('english', :query)) DESC"
        )
    else:
        # Short queries — use ILIKE
        conditions.append("(name ILIKE :pattern OR category ILIKE :pattern)")
        params["pattern"] = f"%{query}%"
        order_by = "name ASC"

    if category:
        conditions.append("category ILIKE :cat")
        params["cat"] = f"%{category}%"

    if price_min is not None:
        conditions.append("price_cents >= :pmin")
        params["pmin"] = price_min

    if price_max is not None:
        conditions.append("price_cents <= :pmax")
        params["pmax"] = price_max

    where_clause = " AND ".join(conditions)

    sql = text(f"""
        SELECT id, name, description, category, price_cents, currency, image_url, in_stock, attributes
        FROM products
        WHERE {where_clause}
        ORDER BY {order_by}
        LIMIT :limit
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    products = [
        ProductInfo(
            id=row.id,
            name=row.name,
            description=row.description or "",
            category=row.category or "",
            price=row.price_cents,
            currency=row.currency or "usd",
            image_url=row.image_url or "",
            in_stock=row.in_stock if row.in_stock is not None else True,
            attributes=row.attributes or {},
        )
        for row in rows
    ]

    # Get total count
    count_sql = text(f"SELECT COUNT(*) FROM products WHERE {where_clause}")
    count_params = {k: v for k, v in params.items() if k != "limit"}
    count_result = await db.execute(count_sql, count_params)
    total = count_result.scalar() or 0

    return ProductSearchResult(products=products, total_count=total, query=query)
