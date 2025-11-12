import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
logger.info(f"Токен бота: {BOT_TOKEN}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ПРОСТОЙ ОБРАБОТЧИК /start
@dp.message(CommandStart())
async def start_command(message: types.Message):
    logger.info(f"Получена команда /start от {message.from_user.id}")
    await message.answer("✅ Бот работает! Команда /start обработана!")

# ПРОСТОЙ ОБРАБОТЧИК /profile
@dp.message(Command("profile"))
async def profile_command(message: types.Message):
    logger.info(f"Получена команда /profile от {message.from_user.id}")
    await message.answer("✅ Профиль! Команда /profile обработана!")

# ОБРАБОТЧИК ЛЮБОГО СООБЩЕНИЯ
@dp.message()
async def any_message(message: types.Message):
    logger.info(f"Получено сообщение: {message.text} от {message.from_user.id}")
    await message.answer(f"Вы написали: {message.text}")

async def main():
    logger.info("🚀 ЗАПУСК ДИАГНОСТИЧЕСКОГО БОТА...")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
