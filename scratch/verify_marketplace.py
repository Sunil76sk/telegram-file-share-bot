import asyncio
import logging
import sys
import os

# Adjust path to find the database module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Initializing database...")
    await database.init_db()

    logger.info("Running marketplace category seeding...")
    await database.seed_marketplace_categories()

    logger.info("Retrieving all seeded categories...")
    categories = await database.get_all_categories()
    logger.info(f"Retrieved {len(categories)} categories:")
    for cat in categories:
        logger.info(f" - {cat['icon']} {cat['name']} (slug: {cat['slug']})")

    if not categories:
        raise ValueError("No categories found in the database. Seeding failed!")

    logger.info("Testing product creation...")
    token = "test_preset_token_123"
    name = "Test Lightroom Preset"
    description = "A professional test preset."
    price = 50
    price_upi = 19.99
    owner_id = 999999
    category_id = categories[0]["_id"]
    product_type = categories[0]["slug"]
    files = [
        {
            "file_id": "AgACAgQAAxkBAAEC",
            "file_unique_id": "unique_1",
            "media_type": "document",
            "file_name": "preset.dng",
            "file_size": 102400,
        }
    ]

    # Clean up any pre-existing test product
    existing = await database.get_product_by_token(token)
    if existing:
        logger.info("Removing pre-existing test product...")
        await database.delete_product(existing["_id"])

    product = await database.create_product(
        token=token,
        name=name,
        description=description,
        price=price,
        owner_id=owner_id,
        category_id=category_id,
        product_type=product_type,
        files=files,
        price_upi=price_upi,
    )
    logger.info(
        f"Product created successfully: {product['name']} (token: {product['token']}, price_upi: {product.get('price_upi')})"
    )

    # Verify retrieval
    retrieved = await database.get_product_by_token(token)
    if (
        not retrieved
        or retrieved["name"] != name
        or retrieved["price_upi"] != price_upi
    ):
        raise ValueError("Product retrieval verification failed!")
    logger.info("Product retrieval verification passed!")

    # Verify purchase recording
    logger.info("Testing purchase recording...")
    payment_id = "test_charge_id_123"

    # Clean up pre-existing purchase
    existing_purchase = await database.get_purchase_by_payment_id(payment_id)
    if existing_purchase:
        await database.purchases_col.delete_one({"_id": existing_purchase["_id"]})

    purchase = await database.record_purchase(
        user_id=111111,
        product_id=product["_id"],
        product_token=product["token"],
        amount_paid=price,
        payment_id=payment_id,
        status="completed",
        files_delivered=files,
    )
    logger.info(
        f"Purchase recorded: {purchase['_id']} (amount: {purchase['amount_paid']})"
    )

    # Verify purchase check
    has_purchased = await database.verify_purchase(111111, product["_id"])
    if not has_purchased:
        raise ValueError("Purchase verification check failed!")
    logger.info("Purchase verification check passed!")

    # Verify download tracking
    logger.info("Testing download tracking...")
    download = await database.record_download(
        purchase_id=purchase["_id"],
        user_id=111111,
        product_id=product["_id"],
        file_id=files[0]["file_id"],
    )
    logger.info(f"Download tracked: {download['_id']}")

    downloads_count = await database.get_total_downloads(product["_id"])
    logger.info(f"Total downloads for product: {downloads_count}")
    if downloads_count != 1:
        raise ValueError("Download counting check failed!")
    logger.info("Download count verification passed!")

    # Clean up test data
    logger.info("Cleaning up test data...")
    await database.delete_product(product["_id"])
    await database.purchases_col.delete_one({"_id": purchase["_id"]})
    await database.downloads_col.delete_one({"_id": download["_id"]})

    logger.info(
        "Marketplace verification script run successfully. All checks passed! 🎉"
    )


if __name__ == "__main__":
    asyncio.run(main())
