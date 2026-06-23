from __future__ import annotations

import datetime
import logging
from database.mongo import db

logger = logging.getLogger(__name__)

RATE_LIMITS_COL = db["rate_limits"]


async def check_rate_limit(
    user_id: int,
    action: str,
    limit: int,
    window_seconds: int = 60,
) -> bool:
    """
    Check if the user has exceeded the rate limit for a specific action.
    Returns True if the action is allowed, False if rate-limited.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(seconds=window_seconds)

    try:
        # Clean up stale records in this window to keep database clean
        await RATE_LIMITS_COL.delete_many(
            {"user_id": user_id, "action": action, "timestamp": {"$lt": cutoff}}
        )

        # Count requests within the current window
        count = await RATE_LIMITS_COL.count_documents(
            {"user_id": user_id, "action": action, "timestamp": {"$gte": cutoff}}
        )

        if count >= limit:
            logger.warning(
                f"Rate limit exceeded: user={user_id} action={action} limit={limit}"
            )
            return False

        # Log this request
        await RATE_LIMITS_COL.insert_one(
            {"user_id": user_id, "action": action, "timestamp": now}
        )
        return True
    except Exception as e:
        logger.error(f"Error checking rate limit for user {user_id}: {e}")
        # Fail open under database errors to avoid blocking users
        return True
