from __future__ import annotations

import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from pymongo import ReturnDocument

from database.mongo import products_col, purchases_col, downloads_col, categories_col

# Product types for digital products
PRODUCT_TYPES = [
    "lightroom_presets",
    "lut_packs",
    "prompt_packs",
    "thumbnail_templates",
    "editing_overlays",
    "motion_graphics",
    "ai_workflows",
]

# Product type display names
PRODUCT_TYPE_NAMES = {
    "lightroom_presets": "Lightroom Presets",
    "lut_packs": "LUT Packs",
    "prompt_packs": "Prompt Packs",
    "thumbnail_templates": "Thumbnail Templates",
    "editing_overlays": "Editing Overlays",
    "motion_graphics": "Motion Graphics",
    "ai_workflows": "AI Workflows",
}

# Product type icons
PRODUCT_TYPE_ICONS = {
    "lightroom_presets": "🎨",
    "lut_packs": "🎬",
    "prompt_packs": "🤖",
    "thumbnail_templates": "📹",
    "editing_overlays": "✨",
    "motion_graphics": "🎭",
    "ai_workflows": "🧠",
}


# =============================================================================
# CATEGORY OPERATIONS
# =============================================================================


async def create_category(
    name: str,
    slug: str,
    description: str = "",
    icon: str = "📁",
    order: int = 0,
    is_active: bool = True,
) -> Dict[str, Any]:
    """Create a new product category."""
    category_doc = {
        "name": name,
        "slug": slug,
        "description": description,
        "icon": icon,
        "order": order,
        "is_active": is_active,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }
    result = await categories_col.insert_one(category_doc)
    res = await categories_col.find_one({"_id": result.inserted_id})
    return res if res is not None else {}


async def get_category_by_id(category_id: ObjectId) -> Optional[Dict[str, Any]]:
    """Get a category by its ObjectId."""
    return await categories_col.find_one({"_id": category_id})


async def get_category_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get a category by its slug."""
    return await categories_col.find_one({"slug": slug})


async def get_all_categories(include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Get all categories, optionally including inactive ones."""
    query = {} if include_inactive else {"is_active": True}
    return [doc async for doc in categories_col.find(query).sort("order", 1)]


async def update_category(category_id: ObjectId, **kwargs) -> Optional[Dict[str, Any]]:
    """Update category fields."""
    kwargs["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
    return await categories_col.find_one_and_update(
        {"_id": category_id}, {"$set": kwargs}, return_document=ReturnDocument.AFTER
    )


async def delete_category(category_id: ObjectId) -> bool:
    """Delete a category."""
    result = await categories_col.delete_one({"_id": category_id})
    return result.deleted_count > 0


# =============================================================================
# PRODUCT OPERATIONS
# =============================================================================


async def create_product(
    token: str,
    name: str,
    description: str,
    price: int,
    owner_id: int,
    category_id: Optional[ObjectId] = None,
    product_type: str = "lightroom_presets",
    files: Optional[List[Dict[str, Any]]] = None,
    thumbnail: Optional[str] = None,
    is_active: bool = True,
    is_featured: bool = False,
    stock: Optional[int] = None,
    tags: Optional[List[str]] = None,
    price_upi: float = 0.0,
) -> Dict[str, Any]:
    """Create a new digital product."""
    if files is None:
        files = []
    if tags is None:
        tags = []

    product_doc = {
        "token": token,
        "name": name,
        "description": description,
        "price": price,
        "owner_id": owner_id,
        "category_id": category_id,
        "product_type": product_type,
        "files": files,
        "thumbnail": thumbnail,
        "is_active": is_active,
        "is_featured": is_featured,
        "stock": stock,
        "tags": tags,
        "price_upi": price_upi,
        "sales_count": 0,
        "views": 0,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }
    result = await products_col.insert_one(product_doc)
    res = await products_col.find_one({"_id": result.inserted_id})
    return res if res is not None else {}


async def get_product_by_id(product_id: ObjectId) -> Optional[Dict[str, Any]]:
    """Get a product by its ObjectId."""
    return await products_col.find_one({"_id": product_id})


async def get_product_by_token(token: str) -> Optional[Dict[str, Any]]:
    """Get a product by its unique token."""
    return await products_col.find_one({"token": token})


async def get_products(
    category_id: Optional[ObjectId] = None,
    product_type: Optional[str] = None,
    search: Optional[str] = None,
    owner_id: Optional[int] = None,
    is_active: bool = True,
    is_featured: Optional[bool] = None,
    limit: int = 20,
    skip: int = 0,
    sort_by: str = "created_at",
    sort_order: int = -1,
) -> List[Dict[str, Any]]:
    """Get products with optional filters."""
    query: Dict[str, Any] = {"is_active": is_active}

    if category_id:
        query["category_id"] = category_id
    if product_type:
        query["product_type"] = product_type
    if owner_id:
        query["owner_id"] = owner_id
    if is_featured:
        query["is_featured"] = is_featured
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]

    cursor = products_col.find(query)
    cursor = cursor.sort(sort_by, sort_order)
    cursor = cursor.skip(skip).limit(limit)

    return [doc async for doc in cursor]


async def get_products_by_owner(owner_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all products by a specific owner."""
    return [
        doc
        async for doc in products_col.find({"owner_id": owner_id})
        .sort("created_at", -1)
        .limit(limit)
    ]


async def get_featured_products(limit: int = 10) -> List[Dict[str, Any]]:
    """Get featured products."""
    return [
        doc
        async for doc in products_col.find({"is_active": True, "is_featured": True})
        .sort("created_at", -1)
        .limit(limit)
    ]


async def get_top_selling_products(limit: int = 10) -> List[Dict[str, Any]]:
    """Get top selling products by sales count."""
    return [
        doc
        async for doc in products_col.find({"is_active": True})
        .sort("sales_count", -1)
        .limit(limit)
    ]


async def get_newest_products(limit: int = 10) -> List[Dict[str, Any]]:
    """Get newest products."""
    return [
        doc
        async for doc in products_col.find({"is_active": True})
        .sort("created_at", -1)
        .limit(limit)
    ]


async def update_product(product_id: ObjectId, **kwargs) -> Optional[Dict[str, Any]]:
    """Update product fields."""
    kwargs["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
    return await products_col.find_one_and_update(
        {"_id": product_id}, {"$set": kwargs}, return_document=ReturnDocument.AFTER
    )


async def increment_product_views(product_id: ObjectId) -> None:
    """Increment product view count."""
    await products_col.update_one({"_id": product_id}, {"$inc": {"views": 1}})


async def increment_product_sales(product_id: ObjectId, session=None) -> None:
    """Increment product sales count."""
    await products_col.update_one(
        {"_id": product_id}, {"$inc": {"sales_count": 1}}, session=session
    )


async def delete_product(product_id: ObjectId) -> bool:
    """Delete a product."""
    result = await products_col.delete_one({"_id": product_id})
    return result.deleted_count > 0


async def toggle_product_featured(product_id: ObjectId, is_featured: bool) -> bool:
    """Toggle featured status of a product."""
    result = await products_col.update_one(
        {"_id": product_id}, {"$set": {"is_featured": is_featured}}
    )
    return result.modified_count > 0


async def toggle_product_active(product_id: ObjectId, is_active: bool) -> bool:
    """Toggle active status of a product."""
    result = await products_col.update_one(
        {"_id": product_id}, {"$set": {"is_active": is_active}}
    )
    return result.modified_count > 0


async def get_product_count() -> int:
    """Get total number of products."""
    return await products_col.count_documents({})


async def get_active_product_count() -> int:
    """Get total number of active products."""
    return await products_col.count_documents({"is_active": True})


# =============================================================================
# PURCHASE OPERATIONS
# =============================================================================


async def record_purchase(
    user_id: int,
    product_id: ObjectId,
    product_token: str,
    amount_paid: int,
    payment_id: str,
    status: str = "completed",
    files_delivered: Optional[List[Dict[str, Any]]] = None,
    session=None,
) -> Dict[str, Any]:
    """Record a new purchase."""
    if files_delivered is None:
        files_delivered = []

    purchase_doc = {
        "user_id": user_id,
        "product_id": product_id,
        "product_token": product_token,
        "amount_paid": amount_paid,
        "payment_id": payment_id,
        "status": status,
        "files_delivered": files_delivered,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }
    result = await purchases_col.insert_one(purchase_doc, session=session)
    res = await purchases_col.find_one({"_id": result.inserted_id}, session=session)
    return res if res is not None else {}


async def get_purchase_by_id(purchase_id: ObjectId) -> Optional[Dict[str, Any]]:
    """Get a purchase by its ObjectId."""
    return await purchases_col.find_one({"_id": purchase_id})


async def get_purchase_by_payment_id(payment_id: str) -> Optional[Dict[str, Any]]:
    """Get a purchase by Telegram payment ID."""
    return await purchases_col.find_one({"payment_id": payment_id})


async def get_user_purchases(
    user_id: int, limit: int = 50, skip: int = 0
) -> List[Dict[str, Any]]:
    """Get all purchases by a user."""
    cursor = purchases_col.find({"user_id": user_id})
    cursor = cursor.sort("created_at", -1)
    cursor = cursor.skip(skip).limit(limit)
    return [doc async for doc in cursor]


async def get_purchases_by_product(product_id: ObjectId) -> List[Dict[str, Any]]:
    """Get all purchases for a specific product."""
    return [
        doc
        async for doc in purchases_col.find({"product_id": product_id}).sort(
            "created_at", -1
        )
    ]


async def verify_purchase(user_id: int, product_id: ObjectId) -> bool:
    """Check if a user has purchased a product."""
    count = await purchases_col.count_documents(
        {"user_id": user_id, "product_id": product_id, "status": "completed"}
    )
    return count > 0


async def verify_purchase_by_token(user_id: int, product_token: str) -> bool:
    """Check if a user has purchased a product by token."""
    count = await purchases_col.count_documents(
        {"user_id": user_id, "product_token": product_token, "status": "completed"}
    )
    return count > 0


async def get_purchase_count() -> int:
    """Get total number of purchases."""
    return await purchases_col.count_documents({})


async def get_sales_by_owner(owner_id: int) -> List[Dict[str, Any]]:
    """Get all sales for products owned by a user."""
    # First get all product IDs by owner
    products = await products_col.find({"owner_id": owner_id}).to_list(None)
    product_ids = [p["_id"] for p in products]

    return [
        doc
        async for doc in purchases_col.find({"product_id": {"$in": product_ids}}).sort(
            "created_at", -1
        )
    ]


async def get_total_revenue_by_owner(owner_id: int) -> int:
    """Get total revenue for a product owner."""
    products = await products_col.find({"owner_id": owner_id}).to_list(None)
    product_ids = [p["_id"] for p in products]

    pipeline = [
        {"$match": {"product_id": {"$in": product_ids}, "status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_paid"}}},
    ]
    result = await purchases_col.aggregate(pipeline).to_list(None)
    return result[0]["total"] if result else 0


# =============================================================================
# DOWNLOAD TRACKING OPERATIONS
# =============================================================================


async def record_download(
    purchase_id: ObjectId,
    user_id: int,
    product_id: ObjectId,
    file_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a file download."""
    download_doc = {
        "purchase_id": purchase_id,
        "user_id": user_id,
        "product_id": product_id,
        "file_id": file_id,
        "downloaded_at": datetime.datetime.now(datetime.timezone.utc),
        "ip_address": ip_address,
        "user_agent": user_agent,
    }
    result = await downloads_col.insert_one(download_doc)
    res = await downloads_col.find_one({"_id": result.inserted_id})
    return res if res is not None else {}


async def get_downloads_by_purchase(purchase_id: ObjectId) -> List[Dict[str, Any]]:
    """Get all downloads for a purchase."""
    return [
        doc
        async for doc in downloads_col.find({"purchase_id": purchase_id}).sort(
            "downloaded_at", -1
        )
    ]


async def get_downloads_by_product(product_id: ObjectId) -> List[Dict[str, Any]]:
    """Get all downloads for a product."""
    return [
        doc
        async for doc in downloads_col.find({"product_id": product_id}).sort(
            "downloaded_at", -1
        )
    ]


async def get_downloads_by_user(user_id: int) -> List[Dict[str, Any]]:
    """Get all downloads by a user."""
    return [
        doc
        async for doc in downloads_col.find({"user_id": user_id}).sort(
            "downloaded_at", -1
        )
    ]


async def get_total_downloads(product_id: ObjectId) -> int:
    """Get total download count for a product."""
    return await downloads_col.count_documents({"product_id": product_id})


async def get_unique_downloaders(product_id: ObjectId) -> int:
    """Get count of unique users who downloaded a product."""
    pipeline = [
        {"$match": {"product_id": product_id}},
        {"$group": {"_id": "$user_id"}},
        {"$count": "count"},
    ]
    result = await downloads_col.aggregate(pipeline).to_list(None)
    return result[0]["count"] if result else 0


# =============================================================================
# STATISTICS & ANALYTICS
# =============================================================================


async def get_marketplace_stats() -> Dict[str, Any]:
    """Get overall marketplace statistics."""
    total_products = await get_product_count()
    active_products = await get_active_product_count()
    total_purchases = await get_purchase_count()

    # Get total revenue
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_paid"}}},
    ]
    revenue_result = await purchases_col.aggregate(pipeline).to_list(None)
    total_revenue = revenue_result[0]["total"] if revenue_result else 0

    return {
        "total_products": total_products,
        "active_products": active_products,
        "total_purchases": total_purchases,
        "total_revenue": total_revenue,
    }


async def get_product_stats(product_id: ObjectId) -> Dict[str, Any]:
    """Get statistics for a specific product."""
    product = await get_product_by_id(product_id)
    if not product:
        return {}

    purchases = await get_purchases_by_product(product_id)
    downloads = await get_downloads_by_product(product_id)

    return {
        "product_id": product_id,
        "views": product.get("views", 0),
        "sales_count": product.get("sales_count", 0),
        "purchases": len(purchases),
        "total_downloads": len(downloads),
        "unique_downloaders": await get_unique_downloaders(product_id),
        "total_revenue": sum(p.get("amount_paid", 0) for p in purchases),
    }


async def seed_marketplace_categories() -> None:
    """Seed the default product categories if they don't exist."""
    categories_data: List[Dict[str, Any]] = [
        {
            "name": "Lightroom Presets",
            "slug": "lightroom_presets",
            "icon": "🎨",
            "description": "Professional photo presets",
            "order": 1,
        },
        {
            "name": "LUT Packs",
            "slug": "lut_packs",
            "icon": "🎬",
            "description": "Cinematic video LUTs",
            "order": 2,
        },
        {
            "name": "Prompt Packs",
            "slug": "prompt_packs",
            "icon": "🤖",
            "description": "Curated AI prompts",
            "order": 3,
        },
        {
            "name": "Thumbnail Templates",
            "slug": "thumbnail_templates",
            "icon": "📹",
            "description": "Stunning thumbnail designs",
            "order": 4,
        },
        {
            "name": "Editing Overlays",
            "slug": "editing_overlays",
            "icon": "✨",
            "description": "Visual overlays and assets",
            "order": 5,
        },
        {
            "name": "Motion Graphics",
            "slug": "motion_graphics",
            "icon": "🎭",
            "description": "Rich motion assets",
            "order": 6,
        },
        {
            "name": "AI Workflows",
            "slug": "ai_workflows",
            "icon": "🧠",
            "description": "Step-by-step AI workflows",
            "order": 7,
        },
    ]
    for cat in categories_data:
        existing = await get_category_by_slug(cat["slug"])
        if not existing:
            await create_category(
                name=cat["name"],
                slug=cat["slug"],
                description=cat["description"],
                icon=cat["icon"],
                order=cat["order"],
            )


# =============================================================================
# BACKWARD COMPATIBILITY CATALOG HELPER FUNCTIONS
# =============================================================================


async def get_catalog_item(item_id: str | ObjectId) -> Optional[Dict[str, Any]]:
    """Helper for backward compatibility with catalog items."""
    if isinstance(item_id, str):
        try:
            item_id = ObjectId(item_id)
        except Exception:
            return None
    return await get_product_by_id(item_id)


async def get_catalog_item_by_token(token: str) -> Optional[Dict[str, Any]]:
    """Helper for backward compatibility with catalog items."""
    return await get_product_by_token(token)


async def increment_catalog_purchases(item_id: str | ObjectId, amount: int = 0) -> None:
    """Helper for backward compatibility with catalog items."""
    if isinstance(item_id, str):
        try:
            item_id = ObjectId(item_id)
        except Exception:
            return
    await increment_product_sales(item_id)
