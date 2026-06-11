import logging
from motor.motor_asyncio import AsyncIOMotorClient
import config

logger = logging.getLogger(__name__)

# Initialize MongoDB Client
client = AsyncIOMotorClient(config.MONGO_URI)
db = client[config.DB_NAME]

# Collections
users_col = db["users"]
files_col = db["files"]
channels_col = db["channels"]
admins_col = db["admins"]
batches_col = db["batches"]
edit_sessions_col = db["edit_sessions"]
deletions_col = db["deletions"]
password_settings_col = db["password_settings"]
password_entries_col = db["password_entries"]
active_deliveries_col = db["active_deliveries"]
sub_bots_col = db["sub_bots"]
payments_col = db["payments"]
shorteners_col = db["shorteners"]
funnel_campaigns_col = db["funnel_campaigns"]
funnel_analytics_col = db["funnel_analytics"]
products_col = db["products"]
purchases_col = db["purchases"]
downloads_col = db["downloads"]
categories_col = db["categories"]
premium_catalog_col = db["premium_catalog"]
access_logs_col = db["access_logs"]
upi_pending_col = db["upi_pending"]
ads_col = db["ads"]
ad_impressions_col = db["ad_impressions"]
ad_clicks_col = db["ad_clicks"]
ad_drafts_col = db["ad_drafts"]
saas_plans_col = db["saas_plans"]
saas_subscriptions_col = db["saas_subscriptions"]
analytics_events_col = db["analytics_events"]


async def init_db():
    try:
        # Create unique index on token
        await files_col.create_index("token", unique=True)
        # Create indexes on user_id
        await users_col.create_index("user_id")
        await batches_col.create_index("user_id")
        await edit_sessions_col.create_index("user_id")

        # New Indexes for SaaS and Monetization
        await sub_bots_col.create_index("owner_id")
        await sub_bots_col.create_index("bot_token", unique=True)
        await payments_col.create_index("user_id")
        await payments_col.create_index("created_at")
        await shorteners_col.create_index("status")
        await funnel_campaigns_col.create_index("source")
        await funnel_campaigns_col.create_index("asset_type")
        await funnel_campaigns_col.create_index("active")
        await funnel_analytics_col.create_index("user_id")
        await funnel_analytics_col.create_index("source")
        await funnel_analytics_col.create_index("campaign_id")

        # Premium Access System indexes
        await premium_catalog_col.create_index("category")
        await premium_catalog_col.create_index("is_active")
        await premium_catalog_col.create_index("token")
        await access_logs_col.create_index("user_id")
        await access_logs_col.create_index("token")
        await access_logs_col.create_index("timestamp")
        await upi_pending_col.create_index("user_id")
        await upi_pending_col.create_index("status")

        # Ad Sponsored Promotions indexes
        await ads_col.create_index("type")
        await ads_col.create_index("status")
        await ads_col.create_index([("type", 1), ("status", 1)])
        await ad_impressions_col.create_index("ad_id")
        await ad_impressions_col.create_index("user_id")
        await ad_impressions_col.create_index("timestamp")
        await ad_clicks_col.create_index("ad_id")
        await ad_clicks_col.create_index("user_id")
        await ad_clicks_col.create_index("timestamp")

        # Marketplace indexes
        await products_col.create_index("token", unique=True)
        await products_col.create_index("owner_id")
        await products_col.create_index("category_id")
        await products_col.create_index("product_type")
        await products_col.create_index("is_active")
        await products_col.create_index("is_featured")
        await products_col.create_index("created_at")
        await purchases_col.create_index("user_id")
        await purchases_col.create_index("product_id")
        await purchases_col.create_index("product_token")
        await purchases_col.create_index("payment_id", unique=True, sparse=True)
        await purchases_col.create_index("status")
        await purchases_col.create_index("created_at")
        await downloads_col.create_index("purchase_id")
        await downloads_col.create_index("user_id")
        await downloads_col.create_index("product_id")
        await downloads_col.create_index("downloaded_at")
        await categories_col.create_index("slug", unique=True)
        await categories_col.create_index("is_active")
        await categories_col.create_index("order")

        # SaaS Licensing Platform indexes
        await saas_subscriptions_col.create_index("user_id")
        await saas_subscriptions_col.create_index([("user_id", 1), ("status", 1)])
        await saas_subscriptions_col.create_index("status")

        # Analytics Monetization indexes
        await analytics_events_col.create_index("date")
        await analytics_events_col.create_index("event")
        await analytics_events_col.create_index("user_id")
        await analytics_events_col.create_index("timestamp")
        await analytics_events_col.create_index("country")
        await analytics_events_col.create_index("source")
        await analytics_events_col.create_index([("event", 1), ("timestamp", 1)])
        await analytics_events_col.create_index([("country", 1), ("timestamp", 1)])
        await analytics_events_col.create_index([("source", 1), ("timestamp", 1)])

        # Migrate traffic attribution for older users
        await users_col.update_many(
            {"source": {"$exists": False}},
            {"$set": {"source": "direct", "campaign": None}}
        )

        logger.info("Database indexes and migrations initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database indexes/migrations: {e}")
