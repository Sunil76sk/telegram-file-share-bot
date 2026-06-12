import asyncio
import logging

# Create and set event loop before importing pyrogram (required for compatibility with Python 3.12+ / 3.14)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from bot import app  # noqa: E402

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    import os
    import socket
    import datetime
    pid = os.getpid()
    hostname = socket.gethostname()
    timestamp = datetime.datetime.now().isoformat()
    logger.info(f"PID: {pid}")
    logger.info(f"Hostname: {hostname}")
    logger.info(f"Timestamp: {timestamp}")
    logger.info("BOT INSTANCE STARTED")
    
    logger.info("Starting Telegram File Share Bot...")
    
    # Diagnostic prints
    try:
        import handlers.premium
        logger.info(f"DIAGNOSTIC: handlers.premium imported. Symbol: {getattr(handlers.premium, 'premium_command_handler', None)}")
        logger.info(f"DIAGNOSTIC: app id in bot: {id(app)}, app id in premium: {id(handlers.premium.app)}")
    except Exception as e:
        logger.error(f"DIAGNOSTIC: Failed to import handlers.premium: {e}")
        
    async def print_handlers_later():
        await asyncio.sleep(2.0)
        logger.info("DIAGNOSTIC: Groups after 2 seconds:")
        for group, handlers in sorted(app.dispatcher.groups.items()):
            logger.info(f"Group {group}:")
            for h in handlers:
                logger.info(f"  - {h.__class__.__name__}: callback={h.callback.__name__ if hasattr(h, 'callback') else 'None'}")
                
    loop.create_task(print_handlers_later())
    app.run()
