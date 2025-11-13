import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# База данных
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(BigInteger, unique=True, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    source = Column(String(100), nullable=True)
    status = Column(String(50), default='lead')
    created_at = Column(DateTime, default=datetime.utcnow)

class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    question_id = Column(String(100))
    answer = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# Подключение к PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_tables():
    """Создаем таблицы в базе данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Таблицы базы данных созданы")

async def get_or_create_user(tg_id: int, username: str, first_name: str, source: str = 'direct'):
    """Получаем или создаем пользователя"""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                source=source,
                status='active'
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"✅ Создан новый пользователь: {first_name}")
        else:
            logger.info(f"✅ Найден существующий пользователь: {first_name}")
        
        return user

async def save_quiz_answer(user_id: int, question_id: str, answer: str):
    """Сохраняет ответ на вопрос квиза"""
    async with AsyncSessionLocal() as session:
        quiz_answer = QuizAnswer(
            user_id=user_id,
            question_id=question_id,
            answer=answer
        )
        session.add(quiz_answer)
        await session.commit()
        logger.info(f"💾 Сохранен ответ: {question_id} = {answer}")

# ОБРАБОТЧИК /start
@dp.message(CommandStart())
async def start_command(message: types.Message):
    logger.info(f"📥 Получен /start от {message.from_user.id}")
    
    # Определяем источник
    source = 'direct'
    if len(message.text.split()) > 1:
        source = message.text.split()[1]
        logger.info(f"🔗 Реферальная ссылка: {source}")
    
    # Сохраняем пользователя
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        source
    )
    
    # Клавиатура
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать тест")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🎉 Добро пожаловать в GenoLife!\n\n"
        "Я помогу вам пройти анализ и улучшить здоровье.\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

# ОБРАБОТЧИК /profile
@dp.message(Command("profile"))
@dp.message(F.text == "👤 Профиль")
async def profile_command(message: types.Message):
    logger.info(f"📊 Запрос профиля от {message.from_user.id}")
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
        user = result.scalar_one_or_none()
        
        if user:
            profile_text = (
                f"👤 Ваш профиль:\n"
                f"Имя: {user.first_name}\n"
                f"Username: @{user.username}\n"
                f"Статус: {user.status}\n"
                f"Источник: {user.source or 'не указан'}\n"
                f"Зарегистрирован: {user.created_at.strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            profile_text = "❌ Профиль не найден. Напишите /start"
    
    await message.answer(profile_text)

# ОБРАБОТЧИК "Начать тест"
@dp.message(F.text == "🧪 Начать тест")
async def start_test_handler(message: types.Message):
    await message.answer(
        "🧪 Отлично! Начинаем тест...\n\n"
        "❓ Вопрос 1: Как часто вы чувствуете усталость?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😫 Часто"), KeyboardButton(text="😐 Иногда")],
                [KeyboardButton(text="😊 Редко"), KeyboardButton(text="🎉 Никогда")],
                [KeyboardButton(text="🔙 Назад")]
            ],
            resize_keyboard=True
        )
    )

# ОБРАБОТЧИКИ ОТВЕТОВ НА ВОПРОС 1
@dp.message(F.text.in_(["😫 Часто", "😐 Иногда", "😊 Редко", "🎉 Никогда"]))
async def question1_handler(message: types.Message):
    # Сохраняем ответ
    await save_quiz_answer(message.from_user.id, "question1_fatigue", message.text)
    
    # Следующий вопрос
    await message.answer(
        f"✅ Ответ сохранен: {message.text}\n\n"
        "❓ Вопрос 2: Какой у вас обычно сон?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😴 Крепкий"), KeyboardButton(text="🛌 Беспокойный")],
                [KeyboardButton(text="⏰ Прерывистый"), KeyboardButton(text="💤 Бессонница")],
                [KeyboardButton(text="🔙 Назад")]
            ],
            resize_keyboard=True
        )
    )

# ОБРАБОТЧИКИ ОТВЕТОВ НА ВОПРОС 2
@dp.message(F.text.in_(["😴 Крепкий", "🛌 Беспокойный", "⏰ Прерывистый", "💤 Бессонница"]))
async def question2_handler(message: types.Message):
    # Сохраняем ответ
    await save_quiz_answer(message.from_user.id, "question2_sleep", message.text)
    
    # Следующий вопрос
    await message.answer(
        f"✅ Ответ сохранен: {message.text}\n\n"
        "❓ Вопрос 3: Как часто вы занимаетесь спортом?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💪 Регулярно"), KeyboardButton(text="🚶 Иногда")],
                [KeyboardButton(text="🧘 Редко"), KeyboardButton(text="🚫 Никогда")],
                [KeyboardButton(text="🔙 Назад")]
            ],
            resize_keyboard=True
        )
    )

# ОБРАБОТЧИКИ ОТВЕТОВ НА ВОПРОС 3
@dp.message(F.text.in_(["💪 Регулярно", "🚶 Иногда", "🧘 Редко", "🚫 Никогда"]))
async def question3_handler(message: types.Message):
    # Сохраняем ответ
    await save_quiz_answer(message.from_user.id, "question3_sport", message.text)
    
    # Завершение теста
    await message.answer(
        f"✅ Ответ сохранен: {message.text}\n\n"
        "🎉 Тест завершен! Спасибо за ответы!\n\n"
        "На основе ваших ответов мы подготовим персональные рекомендации.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧪 Начать тест")],
                [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="ℹ️ О проекте")]
            ],
            resize_keyboard=True
        )
    )

# ОБРАБОТЧИК "О проекте"
@dp.message(F.text == "ℹ️ О проекте")
async def about_handler(message: types.Message):
    await message.answer(
        "🏥 GenoLife - современная система анализа здоровья\n\n"
        "Мы помогаем:\n"
        "• Пройти генетический анализ\n"
        "• Получить персональные рекомендации\n"
        "• Улучшить качество жизни"
    )

# ОБРАБОТЧИК "Назад"
@dp.message(F.text == "🔙 Назад")
async def back_handler(message: types.Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать тест")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    await message.answer("Главное меню:", reply_markup=keyboard)

# ОБРАБОТЧИК ЛЮБОГО ТЕКСТА
@dp.message()
async def echo_handler(message: types.Message):
    await message.answer(
        "🤔 Используйте кнопки меню или команды:\n"
        "/start - начать работу\n"
        "/profile - ваш профиль"
    )

async def main():
    logger.info("🚀 Запуск бота GenoLife с квизом...")
    
    # Создаем таблицы
    try:
        await create_tables()
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")
    
    # Запускаем бота
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
