import sys
sys.path.append(".")
import asyncio
import logging
from pyrogram import Client
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trace_get_chat")

async def main():
    app = Client(
        name="trace_session",
        api_id=config.API_ID,
        api_hash=str(config.API_HASH),
        bot_token=str(config.BOT_TOKEN),
        workdir=".",
    )
    
    await app.start()
    try:
        chat_id = -1004243142724
        logger.info(f"Attempting to call get_chat with ID: {chat_id}")
        chat = await app.get_chat(chat_id)
        logger.info(f"SUCCESS: Title='{chat.title}', Type='{chat.type}', Username='{chat.username}'")
        
        # Also check bot member status
        member = await app.get_chat_member(chat_id, "me")
        logger.info(f"SUCCESS: Bot status in channel is '{member.status}'")
        if member.privileges:
            logger.info(f"SUCCESS: Bot privileges: post={member.privileges.can_post_messages}, delete={member.privileges.can_delete_messages}")
        else:
            logger.info("Bot has NO privileges object")
            
    except Exception as e:
        logger.error(f"FAILURE: Caught exception: {e}", exc_info=True)
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
