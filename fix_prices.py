#!/usr/bin/env python3
"""
Add realistic prices to products based on category.
"""
import asyncio
import random
from sqlalchemy import text, select
from services.seller.database import async_session, ProductRow

# Price ranges by category (in cents)
PRICE_RANGES = {
    "Beds": (20000, 150000),  # $200-$1500
    "Dining Tables": (15000, 100000),  # $150-$1000
    "Dining Table Sets": (25000, 200000),  # $250-$2000
    "Slow Cookers": (2000, 15000),  # $20-$150
    "Chairs": (5000, 50000),  # $50-$500
    "Accent Chairs": (10000, 80000),  # $100-$800
    "Bar Stools": (4000, 25000),  # $40-$250
    "Sofas": (30000, 200000),  # $300-$2000
    "Tables": (10000, 100000),  # $100-$1000
    "Lighting": (2000, 50000),  # $20-$500
    "Cabinets": (15000, 150000),  # $150-$1500
    "Default": (1000, 50000),  # $10-$500
}

def get_price_for_category(category: str) -> int:
    """Generate a realistic price based on category."""
    category_key = category.split("/")[0].strip() if "/" in category else category

    for key, (min_price, max_price) in PRICE_RANGES.items():
        if key.lower() in category.lower():
            return random.randint(min_price, max_price)

    # Default price
    return random.randint(*PRICE_RANGES["Default"])

async def fix_prices():
    """Update all products with realistic prices."""
    async with async_session() as db:
        # Get all products with 0 price
        result = await db.execute(
            select(ProductRow).where(ProductRow.price_cents == 0)
        )
        products = result.scalars().all()

        print(f"Found {len(products)} products with $0 price")

        count = 0
        for product in products:
            # Generate price based on category
            new_price = get_price_for_category(product.category or "")

            # Update
            await db.execute(
                text("UPDATE products SET price_cents = :price WHERE id = :id"),
                {"price": new_price, "id": product.id}
            )
            count += 1

            if count % 1000 == 0:
                print(f"Updated {count} products...")
                await db.commit()

        await db.commit()
        print(f"✅ Updated {count} products with realistic prices")

        # Show some examples
        result = await db.execute(
            text("SELECT id, name, category, price_cents FROM products LIMIT 10")
        )
        print("\nExample products:")
        for row in result:
            print(f"  {row.name[:50]:50s} ${row.price_cents/100:8.2f} ({row.category})")

if __name__ == "__main__":
    asyncio.run(fix_prices())