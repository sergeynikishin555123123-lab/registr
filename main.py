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

async def get_user(tg_id: int, username: str = None, first_name: str = None):
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

# ОБРАБОТЧИК КОМАНДЫ /START
@dp.message(CommandStart())
async def start_command(message: types.Message):
    # Определяем источник (реферальная ссылка)
    source = 'direct'
    scenario = 'default'
    
    if len(message.text.split()) > 1:
        source = message.text.split()[1]  # /start src_bloggerName
        
        # Определяем сценарий по источнику
        if 'blogger1' in source:
            scenario = 'blogger1'
        elif 'blogger2' in source:
            scenario = 'blogger2'
    
    # Сохраняем пользователя в БД
    user = await get_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    # Обновляем источник и сценарий
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, message.from_user.id)
        db_user.source = source
        db_user.scenario = scenario
        await session.commit()
    
    # Создаем клавиатуру с кнопками
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Начать тест")],
            [KeyboardButton(text="О проекте"), KeyboardButton(text="Помощь")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🎉 Добро пожаловать в GenoLife!\n\n"
        "Я помогу вам пройти анализ и улучшить здоровье.\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )
    
    logger.info(f"Пользователь {user.first_name} пришел из: {source}, сценарий: {scenario}")

# ОБРАБОТЧИК КОМАНДЫ /PROFILE
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
                f"Сценарий: {user.scenario}\n"
                f"Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}",
                reply_markup=ReplyKeyboardRemove()
            )

# ОБРАБОТЧИК КОМАНДЫ /HELP
@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "❓ Помощь по боту:\n\n"
        "/start - начать работу\n"
        "/profile - ваш профиль\n"
        "/help - помощь\n\n"
        "Или используйте кнопки меню!"
    )

# ОБРАБОТЧИК КНОПКИ "НАЧАТЬ ТЕСТ"
@dp.message(F.text == "Начать тест")
async def start_test_handler(message: types.Message):
    await message.answer(
        "🧪 Отлично! Начинаем тест...\n\n"
        "Вопрос 1: Как часто вы чувствуете усталость?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Часто"), KeyboardButton(text="Иногда")],
                [KeyboardButton(text="Редко"), KeyboardButton(text="Никогда")]
            ],
            resize_keyboard=True
        )
    )

# ОБРАБОТЧИК КНОПКИ "О ПРОЕКТЕ"
@dp.message(F.text == "О проекте")
async def about_handler(message: types.Message):
    await message.answer(
        "🏥 GenoLife - это современная система анализа здоровья\n\n"
        "Мы помогаем:\n"
        "• Пройти генетический анализ\n"
        "• Получить персональные рекомендации\n"
        "• Улучшить качество жизни"
    )

# ОБРАБОТЧИК КНОПКИ "ПОМОЩЬ"
@dp.message(F.text == "Помощь")
async def help_button_handler(message: types.Message):
    await help_command(message)

# ОБРАБОТЧИК ЛЮБОГО ТЕКСТА (если не распознано)
@dp.message()
async def echo_handler(message: types.Message):
    await message.answer(
        "🤔 Я вас не понял. Используйте кнопки меню или команды:\n"
        "/start - начать работу\n"
        "/help - помощь"
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
