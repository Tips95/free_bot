"""
Точка входа приложения
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from config import settings
from database.base import init_db
from services.tariff_service import TariffService
from database.base import get_session
from scheduler.tasks import setup_scheduler
import sys

# Импорты handlers
from handlers import start, main_menu, subscription, payment

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


async def main():
    """Основная функция"""
    # Инициализация БД
    logger.info("Initializing database...")
    await init_db()
    
    # Инициализация дефолтных тарифов
    async for session in get_session():
        await TariffService.init_default_tariffs(session=session)
        break
    
    # Создание бота и диспетчера
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    
    # Получаем username бота, если не указан в конфиге
    if not settings.BOT_USERNAME:
        bot_info = await bot.get_me()
        settings.BOT_USERNAME = bot_info.username
        logger.info(f"Bot username: {settings.BOT_USERNAME}")
    
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(main_menu.router)
    dp.include_router(subscription.router)
    dp.include_router(payment.router)
    
    # Настройка планировщика
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started")
    
    try:
        # Запуск бота
        logger.info("Starting bot...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
