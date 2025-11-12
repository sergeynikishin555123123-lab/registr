import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Подключение к PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(DATABASE_URL, echo=True, poolclass=NullPool)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Импортируем модели после создания engine
from models import Base, User

async def create_tables():
    """Создаем таблицы в базе данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_or_create_user(tg_id: int, username: str, first_name: str):
    """Получаем или создаем пользователя"""
    async with AsyncSessionLocal() as session:
        user = await session.get(User, tg_id)
        if not user:
            user = User(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                status='active'
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Создан новый пользователь: {first_name} (ID: {tg_id})")
        return user

@dp.message(CommandStart())
async def start_command(message: types.Message):
    # Сохраняем пользователя в БД
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    # Проверяем источник (реферальная ссылка)
    if len(message.text.split()) > 1:
        source = message.text.split()[1]  # /start src_bloggerName
        user.source = source
        logger.info(f"Пользователь {user.first_name} пришел из источника: {source}")
    
    await message.answer(
        "🎉 Добро пожаловать в GenoLife!\n\n"
        "Я помогу вам пройти анализ и улучшить здоровье.\n\n"
        "Начнем с быстрого теста?",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(Command("profile"))
async def profile_command(message: types.Message):
    """Показывает профиль пользователя"""
    async with AsyncSessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        if user:
            await message.answer(
                f"👤 Ваш профиль:\n"
                f"Имя: {user.first_name}\n"
                f"Username: @{user.username}\n"
                f"Статус: {user.status}\n"
                f"Источник: {user.source or 'не указан'}\n"
                f"Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}"
            )

async def main():
    logger.info("🚀 Запуск бота GenoLife...")
    
    # Создаем таблицы в БД
    try:
        await create_tables()
        logger.info("✅ Таблицы базы данных созданы")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")
    
    # Запускаем бота
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
