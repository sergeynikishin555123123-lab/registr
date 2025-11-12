import asyncio
import logging
import os
import sys

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import config
from app.database.database import create_tables
from app.handlers import client, admin

async def main():
    logger.info("🚀 Запуск бота GenoLife...")
    
    # Создаем бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Создаем таблицы в БД
    try:
        await create_tables()
        logger.info("✅ Таблицы базы данных созданы")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")
    
    # Регистрируем роутеры
    dp.include_router(client.router)
    dp.include_router(admin.router)
    
    # Запускаем бота
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
