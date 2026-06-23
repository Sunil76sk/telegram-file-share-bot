from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import secrets

from database.mongo import db

logger = logging.getLogger(__name__)

CALLBACK_TOKENS_COL = db["callback_tokens"]
CALLBACK_LOG_COL = db["callback_execution_log"]

HMAC_KEY = secrets.token_hex(32)


def _make_signature(data: str) -> str:
    return hmac.new(HMAC_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()[:16]


async def create_callback_token(
    user_id: int,
    action: str,
    payload: str | None = None,
    expires_in: int = 300,
) -> str:
    token_data = {
        "user_id": user_id,
        "action": action,
        "payload": payload,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "expires_at": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=expires_in),
        "used": False,
    }
    raw = json.dumps(
        {
            "uid": user_id,
            "act": action,
            "pay": payload,
            "ts": token_data["created_at"].isoformat(),
        }
    )
    sig = _make_signature(raw)
    token_id = f"cb_{sig}_{secrets.token_hex(4)}"
    token_data["_id"] = token_id
    token_data["token"] = token_id
    await CALLBACK_TOKENS_COL.insert_one(token_data)
    return token_id


async def validate_callback_token(
    token: str, user_id: int, expected_action: str | None = None
) -> dict | None:
    doc = await CALLBACK_TOKENS_COL.find_one({"_id": token})
    if not doc:
        logger.warning(f"Callback token {token} not found")
        return None
    if doc.get("used"):
        logger.warning(f"Callback token {token} already used")
        return None
    if doc.get("user_id") != user_id:
        logger.warning(
            f"Callback token user mismatch: expected {doc.get('user_id')}, got {user_id}"
        )
        return None
    if expected_action and doc.get("action") != expected_action:
        logger.warning(
            f"Callback token action mismatch: expected {expected_action}, got {doc.get('action')}"
        )
        return None
    expires_at = doc.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
    if expires_at and datetime.datetime.now(datetime.timezone.utc) > expires_at:
        logger.warning(f"Callback token {token} expired")
        return None
    return doc


async def consume_callback_token(token: str) -> bool:
    result = await CALLBACK_TOKENS_COL.update_one(
        {"_id": token, "used": False},
        {
            "$set": {
                "used": True,
                "consumed_at": datetime.datetime.now(datetime.timezone.utc),
            }
        },
    )
    return result.modified_count > 0


async def log_callback_execution(
    callback_data: str,
    user_id: int,
    handler: str,
    success: bool,
    error: str | None = None,
):
    await CALLBACK_LOG_COL.insert_one(
        {
            "callback_data": callback_data,
            "user_id": user_id,
            "handler": handler,
            "success": success,
            "error": error,
            "executed_at": datetime.datetime.now(datetime.timezone.utc),
        }
    )


async def cleanup_expired_tokens():
    result = await CALLBACK_TOKENS_COL.delete_many(
        {
            "expires_at": {"$lte": datetime.datetime.now(datetime.timezone.utc)},
            "used": False,
        }
    )
    if result.deleted_count:
        logger.info(f"Cleaned {result.deleted_count} expired callback tokens")
