import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web
from app.bot.handlers import main_router
from app.bot.middlewares import (
    AuthMiddleware,
    DatabaseMiddleware,
    ErrorMiddleware,
    RequiredChannelMiddleware,
    ThrottlingMiddleware,
)
from app.bot.storage.persistent_storage import PersistentFSMStorage
from app.config import settings
from app.database.models import Base
from app.database.session import engine
from app.services.scheduler_service import SchedulerService

from logging.handlers import RotatingFileHandler
from pathlib import Path

logs_dir = Path("./storage/logs")
logs_dir.mkdir(parents=True, exist_ok=True)
log_file_path = logs_dir / "bot.log"

file_handler = RotatingFileHandler(
    filename=str(log_file_path),
    maxBytes=10 * 1024 * 1024,  # 10 MB per file
    backupCount=5,              # Keep up to 5 archived logs
    encoding="utf-8"
)

stream_handler = logging.StreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[stream_handler, file_handler]
)
logger = logging.getLogger("app")


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized successfully.")


async def health_check(request):
    return web.Response(text="Telegram Test Platform Bot is RUNNING 24/7 OK!")


async def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    app_web = web.Application()
    app_web.router.add_get("/", health_check)
    app_web.router.add_get("/health", health_check)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check web server running on port {port}")
    return runner


async def main():
    logger.info("Starting Telegram Test Platform Bot with Turbo Optimization...")

    # 1. Start HTTP Health Server for Render / Cloud immediately so health checks pass
    web_runner = None
    try:
        web_runner = await start_health_server()
    except Exception as e:
        logger.warning(f"Could not start health web server on port (not critical): {e}")

    # 2. Persistent Storage
    storage = PersistentFSMStorage()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher(storage=storage)

    # 3. Initialize Database Schema
    try:
        await create_tables()
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)

    # 4. Register Middlewares
    dp.update.middleware(ErrorMiddleware())
    dp.update.middleware(ThrottlingMiddleware(rate_limit=0.35))
    dp.update.middleware(DatabaseMiddleware())
    dp.update.middleware(AuthMiddleware(cache_ttl=120))
    dp.update.middleware(RequiredChannelMiddleware())

    # 5. Include Main Routers
    dp.include_router(main_router)

    # 6. Launch Background Scheduler
    scheduler_task = asyncio.create_task(SchedulerService.start_scheduler_loop(bot, interval_seconds=30))

    # 7. Start Polling
    logger.info("Bot is polling with instant update resolution...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member", "inline_query"],
            polling_timeout=15
        )
    except Exception as e:
        logger.critical(f"Unhandled error in polling: {e}", exc_info=True)
    finally:
        scheduler_task.cancel()
        if web_runner:
            try:
                await web_runner.cleanup()
            except Exception:
                pass
        try:
            await storage.close()
            await bot.session.close()
            await engine.dispose()
        except Exception:
            pass
        logger.info("Bot stopped.")


if __name__ == "__main__":
    import traceback
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot process exited.")
    except Exception as e:
        logger.critical(f"FATAL BOT CRASH: {e}")
        traceback.print_exc()
        sys.exit(1)
