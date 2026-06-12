from __future__ import annotations

import logging
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

BOTFATHER_COL = db["botfather_menu"]

DEFAULT_COMMANDS = [
    {"command": "start", "description": "Start the bot and get welcome message"},
    {"command": "premium", "description": "View premium subscription plans"},
    {"command": "subscribe", "description": "Alias for /premium"},
    {"command": "referral", "description": "View referral link and rewards"},
    {"command": "share", "description": "Alias for /referral"},
    {"command": "newpost", "description": "Create a new channel post"},
    {"command": "schedule", "description": "View scheduled posts"},
    {"command": "reposts", "description": "View auto-reposting jobs"},
    {"command": "templates", "description": "Manage post templates"},
    {"command": "channel_stats", "description": "View channel analytics"},
    {"command": "my_channels", "description": "List your managed channels"},
    {"command": "batch", "description": "Start batch file upload"},
    {"command": "cancel", "description": "Cancel current operation"},
    {"command": "stats", "description": "View bot statistics"},
    {"command": "store", "description": "Browse premium store"},
    {"command": "settings", "description": "User preferences and settings"},
    {"command": "help", "description": "Get help using the bot"},
]

ADMIN_COMMANDS = [
    {"command": "broadcast", "description": "Broadcast message to all users"},
    {"command": "broadcast_status", "description": "Check broadcast status"},
    {"command": "broadcast_unlock", "description": "Force unlock broadcast"},
    {"command": "editlink", "description": "Edit a file share link"},
    {"command": "edit_link", "description": "Advanced link editor"},
    {"command": "shorteners", "description": "Manage URL shorteners"},
    {"command": "ads", "description": "Sponsored promotions dashboard"},
    {"command": "adstats", "description": "View ad statistics"},
    {"command": "traffic", "description": "View traffic analytics"},
    {"command": "analytics", "description": "View analytics dashboard"},
    {"command": "advertise", "description": "Advertiser portal"},
    {"command": "ban", "description": "Ban a user"},
    {"command": "unban", "description": "Unban a user"},
    {"command": "add_admin", "description": "Add dynamic admin"},
    {"command": "del_admin", "description": "Remove dynamic admin"},
    {"command": "upi_pending", "description": "View pending UPI payments"},
    {"command": "pending_upi", "description": "Alias for /upi_pending"},
    {"command": "grantpremium", "description": "Grant premium to user"},
    {"command": "revokepremium", "description": "Revoke premium from user"},
    {"command": "diagnose", "description": "Run system diagnostics"},
    {"command": "backup", "description": "Create database backup"},
    {"command": "restore", "description": "Restore database backup"},
    {"command": "backups", "description": "List available backups"},
    {"command": "sync_menu", "description": "Sync commands with BotFather"},
    {"command": "worker_status", "description": "View worker status"},
]

CREATOR_COMMANDS = [
    {"command": "add_channel", "description": "Add channel to Creator Studio"},
    {"command": "del_channel", "description": "Remove channel from Creator Studio"},
    {"command": "channels", "description": "List force sub channels"},
    {"command": "channel_settings", "description": "Alias for /my_channels"},
]


async def get_sync_payload(include_admin: bool = False) -> str:
    commands = list(DEFAULT_COMMANDS)
    commands.extend(CREATOR_COMMANDS)

    lines = []
    for cmd in commands:
        lines.append(f"{cmd['command']} - {cmd['description']}")
    return "\n".join(lines)


async def get_admin_sync_payload() -> str:
    return await get_sync_payload(include_admin=True)


async def save_menu_snapshot(menu_type: str, payload: str):
    await BOTFATHER_COL.update_one(
        {"type": menu_type},
        {"$set": {"payload": payload, "updated_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc)}},
        upsert=True,
    )


async def get_menu_snapshot(menu_type: str) -> str | None:
    doc = await BOTFATHER_COL.find_one({"type": menu_type})
    return doc.get("payload") if doc else None


async def get_formatted_command_list() -> str:
    text = "**Available Commands**\n\n**User Commands:**\n"
    for cmd in DEFAULT_COMMANDS:
        text += f"/{cmd['command']} — {cmd['description']}\n"

    text += "\n**Creator Commands:**\n"
    for cmd in CREATOR_COMMANDS:
        text += f"/{cmd['command']} — {cmd['description']}\n"

    text += "\n**Admin Commands (hidden from menu):**\n"
    for cmd in ADMIN_COMMANDS:
        text += f"/{cmd['command']} — {cmd['description']}\n"

    return text
