from __future__ import annotations

import asyncio
import logging
from pyrogram import Client
import config
import database
from bot import app

logger = logging.getLogger(__name__)


class SaaSRunner:
    def __init__(self):
        self.clients: dict[str, Client] = {}

    async def copy_handlers(self, source_client: Client, target_client: Client):
        """Wait for handlers to register, then copy all handlers from source to target."""
        await asyncio.sleep(
            0.2
        )  # Yield control to let Pyrogram tasks register handlers

        EXCLUDED_MODULES = {
            "handlers.funnel",
            "handlers.ads",
            "handlers.analytics",
            "handlers.premium_admin",
        }

        for group, handlers in source_client.dispatcher.groups.items():
            for handler in handlers:
                # Restrict platform command handlers from being copied to sub-bots
                callback = getattr(handler, "callback", None)
                if callback:
                    module_name = getattr(callback, "__module__", "")
                    if module_name in EXCLUDED_MODULES:
                        continue
                target_client.add_handler(handler, group)
        logger.info(
            f"Copied all handlers to sub-bot client @{target_client.me.username}"
        )

    async def start_bot(self, bot_token: str, username: str) -> bool:
        """Start a Pyrogram client for the given sub-bot token."""
        if bot_token in self.clients:
            logger.info(f"Bot @{username} is already running.")
            return True

        logger.info(f"Starting sub-bot @{username}...")
        try:
            client = Client(
                name=f"sub_bot_{username}",
                api_id=config.API_ID,
                api_hash=str(config.API_HASH),
                bot_token=bot_token,
                workdir=".",  # Store session files in project root
            )
            await client.start()

            # Ensure client.me is populated
            if not client.me:
                client.me = await client.get_me()

            await self.copy_handlers(app, client)
            self.clients[bot_token] = client
            logger.info(f"Sub-bot @{username} started successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to start sub-bot @{username}: {e}")
            await database.set_sub_bot_active(bot_token, False)
            return False

    async def stop_bot(self, bot_token: str):
        """Stop a running sub-bot client."""
        client = self.clients.pop(bot_token, None)
        if client:
            try:
                await client.stop()
                logger.info("Stopped sub-bot client.")
            except Exception as e:
                logger.error(f"Error stopping sub-bot client: {e}")

    async def start_all(self):
        """Fetch all active sub-bots from database and start them in the background."""
        active_bots = await database.get_all_active_sub_bots()
        logger.info(f"Found {len(active_bots)} active sub-bots to start.")
        for bot_doc in active_bots:
            token = bot_doc["bot_token"]
            username = bot_doc["username"]
            asyncio.create_task(self.start_bot(token, username))

    async def stop_all(self):
        """Stop all running sub-bot clients."""
        logger.info("Stopping all sub-bots...")
        tokens = list(self.clients.keys())
        for token in tokens:
            await self.stop_bot(token)


# Global singleton
saas_runner = SaaSRunner()
