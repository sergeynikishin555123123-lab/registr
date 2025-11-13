import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text, Float, Boolean, select, text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 898508164))
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
    phone = Column(String(20), nullable=True)
    city = Column(String(100), nullable=True)
    timezone = Column(String(50), nullable=True)
    source = Column(String(100), nullable=True)
    scenario = Column(String(50), default='default')
    status = Column(String(50), default='lead')
    created_at = Column(DateTime, default=datetime.utcnow)

class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    question_id = Column(String(100))
    answer = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    amount = Column(Float)
    payment_status = Column(String(50), default='new')
    payment_date = Column(DateTime, nullable=True)
    transaction_id = Column(String(100), nullable=True)
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

async def add_missing_columns():
    """Добавляем отсутствующие колонки в существующие таблицы"""
    async with engine.begin() as conn:
        # Проверяем существование колонки scenario в таблице users
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'scenario'
        """))
        scenario_exists = result.scalar() is not None
        
        if not scenario_exists:
            logger.info("🔄 Добавляем колонку scenario в таблицу users...")
            await conn.execute(text("ALTER TABLE users ADD COLUMN scenario VARCHAR(50) DEFAULT 'default'"))
            logger.info("✅ Колонка scenario добавлена")
        
        # Проверяем другие возможные отсутствующие колонки
        columns_to_check = ['phone', 'city', 'timezone', 'source']
        for column in columns_to_check:
            result = await conn.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = '{column}'
            """))
            if result.scalar() is None:
                logger.info(f"🔄 Добавляем колонку {column} в таблицу users...")
                if column in ['phone', 'city', 'timezone', 'source']:
                    await conn.execute(text(f"ALTER TABLE users ADD COLUMN {column} VARCHAR(100)"))
                logger.info(f"✅ Колонка {column} добавлена")

async def cleanup_orders():
    """Очищает некорректные заказы"""
    async with AsyncSessionLocal() as session:
        # Находим заказы с user_id которые не существуют в таблице users
        result = await session.execute(text("""
            DELETE FROM orders 
            WHERE user_id NOT IN (SELECT id FROM users)
        """))
        await session.commit()
        logger.info(f"🗑️ Удалено {result.rowcount} некорректных заказов")

async def setup_database():
    """Настраиваем базу данных"""
    await create_tables()
    await add_missing_columns()
    await cleanup_orders()
    logger.info("✅ База данных полностью настроена")

async def get_user(tg_id: int):
    """Получаем пользователя из БД по tg_id"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        return result.scalar_one_or_none()

async def get_or_create_user(tg_id: int, username: str, first_name: str, source: str = 'direct'):
    """Получаем или создаем пользователя"""
    async with AsyncSessionLocal() as session:
        user = await get_user(tg_id)
        
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

async def create_order(user_id: int, amount: float):
    """Создает заказ"""
    async with AsyncSessionLocal() as session:
        # Находим пользователя по tg_id чтобы получить его id в БД
        user_result = await session.execute(select(User).where(User.tg_id == user_id))
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.error(f"❌ Пользователь с tg_id {user_id} не найден при создании заказа")
            return None
            
        order = Order(
            user_id=user.id,  # Сохраняем id пользователя из БД, а не tg_id
            amount=amount,
            payment_status='pending'
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        logger.info(f"💰 Создан заказ #{order.id} для пользователя {user.first_name} (ID: {user.id})")
        return order

# Состояния для FSM
class OrderStates(StatesGroup):
    waiting_contacts = State()
    waiting_timezone = State()

# ОБРАБОТЧИК /start
@dp.message(CommandStart())
async def start_command(message: types.Message):
    logger.info(f"📥 Получен /start от {message.from_user.id}")
    
    # Определяем источник и сценарий
    source = 'direct'
    scenario = 'default'
    
    if len(message.text.split()) > 1:
        source = message.text.split()[1]
        
        # Определяем сценарий по источнику
        if 'blogger1' in source:
            scenario = 'blogger1'
            welcome_text = "👋 Привет! Вы пришли от Блоггера 1!\n\nДавайте узнаем больше о вашем здоровье..."
        elif 'blogger2' in source:
            scenario = 'blogger2' 
            welcome_text = "👋 Привет! Вы пришли от Блоггера 2!\n\nНачнем путь к улучшению здоровья!"
        else:
            welcome_text = "🎉 Добро пожаловать в GenoLife!\n\nЯ помогу вам пройти анализ и улучшить здоровье."
    else:
        welcome_text = "🎉 Добро пожаловать в GenoLife!\n\nЯ помогу вам пройти анализ и улучшить здоровье."
    
    # Сохраняем пользователя
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        source
    )
    
    # Обновляем сценарий (безопасно, так как колонка теперь есть)
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, message.from_user.id)
        if hasattr(db_user, 'scenario'):
            db_user.scenario = scenario
        await session.commit()
    
    # Клавиатура
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(welcome_text + "\n\nВыберите действие:", reply_markup=keyboard)
    logger.info(f"🔗 Пользователь {user.first_name} пришел из: {source}, сценарий: {scenario}")

# ОБРАБОТЧИК РЕФЕРАЛЬНОЙ ССЫЛКИ
@dp.message(F.text == "🔗 Моя реф ссылка")
async def my_referral_handler(message: types.Message):
    bot_username = (await bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
    
    await message.answer(
        f"🔗 Ваша реферальная ссылка:\n\n"
        f"`{referral_link}`\n\n"
        f"Поделитесь этой ссылкой с друзьями!",
        parse_mode="Markdown"
    )

# ОБРАБОТЧИК ОПЛАТЫ
@dp.message(F.text == "💰 Оплатить анализ")
async def payment_handler(message: types.Message, state: FSMContext):
    # Создаем заказ
    order = await create_order(message.from_user.id, 2990.00)
    
    if not order:
        await message.answer("❌ Ошибка при создании заказа. Попробуйте еще раз.")
        return
    
    # ТЕСТОВАЯ оплата - сразу переходим к подтверждению
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Тестовая оплата", callback_data=f"test_payment:{order.id}")],
            [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid:{order.id}")]
        ]
    )
    
    await message.answer(
        "💰 Оплата анализа\n\n"
        "Стоимость полного анализа: 2 990 руб.\n\n"
        "Включает:\n"
        "• Комплект для сбора анализов\n"
        "• Подробный отчет\n"
        "• Персональные рекомендации\n\n"
        "💡 *Для теста:* нажмите 'Тестовая оплата' или 'Я оплатил(а)'",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ТЕСТОВАЯ ОПЛАТА (исправленная)
@dp.callback_query(F.data.startswith("test_payment:"))
async def test_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        order_id = int(callback.data.split(":")[1])
        logger.info(f"🧪 Тестовая оплата для заказа #{order_id}")
        
        # Обновляем статус заказа
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, order_id)
            if order:
                order.payment_status = 'paid'
                order.payment_date = datetime.utcnow()
                order.transaction_id = f"TEST_{uuid.uuid4()[:8]}"
                await session.commit()
                
                # Обновляем статус пользователя
                user = await session.get(User, order.user_id)
                
                if user:
                    user.status = 'paid'
                    await session.commit()
                    
                    logger.info(f"✅ Тестовая оплата подтверждена для заказа #{order_id}")
                    
                    await callback.message.answer(
                        "🎉 Тестовая оплата подтверждена! Спасибо за заказ!\n\n"
                        "Теперь нам нужны ваши контактные данные для доставки набора.",
                        reply_markup=ReplyKeyboardMarkup(
                            keyboard=[
                                [KeyboardButton(text="📞 Оставить контакты", request_contact=True)]
                            ],
                            resize_keyboard=True
                        )
                    )
                    
                    await state.set_state(OrderStates.waiting_contacts)
                    await callback.answer("✅ Тестовая оплата подтверждена!")
                else:
                    await callback.answer("❌ Пользователь не найден")
            else:
                await callback.answer("❌ Заказ не найден")
                
    except Exception as e:
        logger.error(f"❌ Ошибка при тестовой оплате: {e}")
        await callback.answer("❌ Произошла ошибка")

# ОБРАБОТЧИК ПОДТВЕРЖДЕНИЯ ОПЛАТЫ (ИСПРАВЛЕННЫЙ)
@dp.callback_query(F.data.startswith("paid:"))
async def payment_confirmation_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        order_id = int(callback.data.split(":")[1])
        logger.info(f"💰 Подтверждение оплаты для заказа #{order_id}")
        
        # Обновляем статус заказа
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, order_id)
            if order:
                order.payment_status = 'paid'
                order.payment_date = datetime.utcnow()
                order.transaction_id = str(uuid.uuid4())[:8]
                await session.commit()
                
                # Обновляем статус пользователя (теперь user_id = id пользователя в БД)
                user = await session.get(User, order.user_id)
                
                if user:
                    user.status = 'paid'
                    await session.commit()
                    
                    logger.info(f"✅ Оплата подтверждена для заказа #{order_id}, пользователь {user.first_name}")
                    
                    await callback.message.answer(
                        "🎉 Оплата подтверждена! Спасибо за заказ!\n\n"
                        "Теперь нам нужны ваши контактные данные для доставки набора.",
                        reply_markup=ReplyKeyboardMarkup(
                            keyboard=[
                                [KeyboardButton(text="📞 Оставить контакты", request_contact=True)]
                            ],
                            resize_keyboard=True
                        )
                    )
                    
                    await state.set_state(OrderStates.waiting_contacts)
                    await callback.answer("✅ Оплата подтверждена!")
                else:
                    logger.error(f"❌ Пользователь не найден для заказа #{order_id}")
                    await callback.answer("❌ Ошибка: пользователь не найден")
            else:
                await callback.answer("❌ Заказ не найден")
                
    except Exception as e:
        logger.error(f"❌ Ошибка при подтверждении оплаты: {e}")
        await callback.answer("❌ Произошла ошибка")

# ОБРАБОТЧИК КОНТАКТОВ (ИСПРАВЛЕННЫЙ ПОИСК)
@dp.message(OrderStates.waiting_contacts, F.contact)
async def contact_handler(message: types.Message, state: FSMContext):
    try:
        phone = message.contact.phone_number
        logger.info(f"📞 Получен контакт: {phone} от пользователя {message.from_user.id}")
        
        # Сохраняем контакт - ИЩЕМ ПО tg_id (ID Telegram), а не по id БД
        async with AsyncSessionLocal() as session:
            # Ищем пользователя по tg_id (ID Telegram)
            result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
            user = result.scalar_one_or_none()
            
            if user:
                user.phone = phone
                await session.commit()
                logger.info(f"✅ Телефон сохранен для пользователя {user.first_name} (ID: {user.id})")
            else:
                logger.error(f"❌ Пользователь с tg_id {message.from_user.id} не найден в БД")
                await message.answer("❌ Ошибка: пользователь не найден в базе данных")
                return
        
        # Создаем клавиатуру для выбора часового пояса
        timezone_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Москва (+3)"), KeyboardButton(text="Калининград (+2)")],
                [KeyboardButton(text="Екатеринбург (+5)"), KeyboardButton(text="Определить по городу")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            f"✅ Телефон сохранен: {phone}\n\n"
            "Теперь выберите ваш часовой пояс:",
            reply_markup=timezone_keyboard
        )
        
        # Переходим к следующему состоянию
        await state.set_state(OrderStates.waiting_timezone)
        logger.info(f"✅ Переход к состоянию waiting_timezone для пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке контакта: {e}")
        await message.answer("❌ Произошла ошибка при сохранении контакта")

# ОБРАБОТЧИК ЧАСОВОГО ПОЯСА (ИСПРАВЛЕННЫЙ ПОИСК)
@dp.message(OrderStates.waiting_timezone)
async def timezone_handler(message: types.Message, state: FSMContext):
    logger.info(f"🕐 Обработка часового пояса: {message.text}")
    
    timezone_map = {
        "Москва (+3)": "Europe/Moscow",
        "Калининград (+2)": "Europe/Kaliningrad", 
        "Екатеринбург (+5)": "Asia/Yekaterinburg",
        "Определить по городу": "auto"
    }
    
    if message.text in timezone_map:
        timezone = timezone_map[message.text]
        logger.info(f"✅ Выбран часовой пояс: {timezone}")
        
        # Сохраняем часовой пояс - ИЩЕМ ПО tg_id
        async with AsyncSessionLocal() as session:
            # Ищем пользователя по tg_id (ID Telegram)
            result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
            user = result.scalar_one_or_none()
            
            if user:
                user.timezone = timezone
                if message.text == "Определить по городу":
                    user.city = "auto"
                await session.commit()
                logger.info(f"✅ Часовой пояс сохранен для пользователя {user.first_name} (ID: {user.id})")
            else:
                logger.error(f"❌ Пользователь с tg_id {message.from_user.id} не найден при сохранении часового пояса")
                await message.answer("❌ Ошибка: пользователь не найден")
                return
        
        # Главное меню после успешного завершения
        main_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧪 Начать тест")],
                [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Статус заказа")]
            ],
            resize_keyboard=True
        )
        
        success_message = f"✅ Часовой пояс сохранен: {message.text}\n\n"
        if message.text == "Определить по городу":
            success_message += "📍 Мы определим ваш часовой пояс автоматически по городу.\n\n"
        
        success_message += "🎊 Поздравляем с покупкой! Ваш набор будет отправлен в ближайшее время.\n\nМенеджер свяжется с вами для уточнения деталей доставки."
        
        await message.answer(success_message, reply_markup=main_keyboard)
        
        # Очищаем состояние
        await state.clear()
        logger.info(f"✅ Состояние очищено для пользователя {message.from_user.id}")
        
    else:
        logger.warning(f"⚠️ Неизвестный часовой пояс: {message.text}")
        await message.answer(
            "❌ Пожалуйста, выберите часовой пояс из предложенных вариантов:\n"
            "• Москва (+3)\n"
            "• Калининград (+2)\n" 
            "• Екатеринбург (+5)\n"
            "• Определить по городу"
        )
    
    if message.text in timezone_map:
        timezone = timezone_map[message.text]
        logger.info(f"✅ Выбран часовой пояс: {timezone}")
        
        # Сохраняем часовой пояс
        async with AsyncSessionLocal() as session:
            user = await session.get(User, message.from_user.id)
            if user:
                user.timezone = timezone
                if message.text == "Определить по городу":
                    user.city = "auto"
                await session.commit()
                logger.info(f"✅ Часовой пояс сохранен для пользователя {user.first_name}")
            else:
                logger.error(f"❌ Пользователь не найден при сохранении часового пояса")
        
        # Главное меню после успешного завершения
        main_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧪 Начать тест")],
                [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Статус заказа")]
            ],
            resize_keyboard=True
        )
        
        success_message = f"✅ Часовой пояс сохранен: {message.text}\n\n"
        if message.text == "Определить по городу":
            success_message += "📍 Мы определим ваш часовой пояс автоматически по городу.\n\n"
        
        success_message += "🎊 Поздравляем с покупкой! Ваш набор будет отправлен в ближайшее время.\n\nМенеджер свяжется с вами для уточнения деталей доставки."
        
        await message.answer(success_message, reply_markup=main_keyboard)
        
        # Очищаем состояние
        await state.clear()
        logger.info(f"✅ Состояние очищено для пользователя {message.from_user.id}")
        
    else:
        logger.warning(f"⚠️ Неизвестный часовой пояс: {message.text}")
        await message.answer(
            "❌ Пожалуйста, выберите часовой пояс из предложенных вариантов:\n"
            "• Москва (+3)\n"
            "• Калининград (+2)\n" 
            "• Екатеринбург (+5)\n"
            "• Определить по городу"
        )

# ОБРАБОТЧИК ПРОФИЛЯ
@dp.message(Command("profile"))
@dp.message(F.text == "👤 Профиль")
async def profile_command(message: types.Message):
    logger.info(f"📊 Запрос профиля от {message.from_user.id}")
    
    user = await get_user(message.from_user.id)
    
    if user:
        # Получаем последний заказ
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
            )
            order = result.scalar_one_or_none()
        
        # Безопасно получаем scenario (может отсутствовать в старых записях)
        scenario = getattr(user, 'scenario', 'default')
        
        profile_text = (
            f"👤 Ваш профиль:\n"
            f"Имя: {user.first_name or 'Не указано'}\n"
            f"Username: @{user.username or 'Не указан'}\n"
            f"Телефон: {user.phone or 'Не указан'}\n"
            f"Часовой пояс: {user.timezone or 'Не указан'}\n"
            f"Статус: {user.status}\n"
            f"Источник: {user.source or 'Не указан'}\n"
            f"Сценарий: {scenario}\n"
            f"Зарегистрирован: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        )
        
        if order:
            status_text = {
                'new': '🆕 Новый',
                'pending': '⏳ Ожидает оплаты', 
                'paid': '✅ Оплачен',
                'shipped': '🚚 Отправлен',
                'delivered': '📦 Доставлен'
            }
            profile_text += f"Последний заказ: #{order.id} ({status_text.get(order.payment_status, order.payment_status)})"
        
    else:
        profile_text = "❌ Профиль не найден. Напишите /start"
    
    await message.answer(profile_text)

# ОБРАБОТЧИК СТАТУСА ЗАКАЗА
@dp.message(F.text == "📦 Статус заказа")
async def order_status_handler(message: types.Message):
    user = await get_user(message.from_user.id)
    
    if not user:
        await message.answer("❌ Сначала напишите /start")
        return
        
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
        )
        order = result.scalar_one_or_none()
        
        if order:
            status_text = {
                'new': '🆕 Новый',
                'pending': '⏳ Ожидает оплаты', 
                'paid': '✅ Оплачен',
                'shipped': '🚚 Отправлен',
                'delivered': '📦 Доставлен'
            }
            
            await message.answer(
                f"📦 Ваш заказ #{order.id}\n"
                f"Статус: {status_text.get(order.payment_status, order.payment_status)}\n"
                f"Сумма: {order.amount} руб\n"
                f"Дата: {order.created_at.strftime('%d.%m.%Y')}"
            )
        else:
            await message.answer("❌ У вас нет заказов")

# ОБРАБОТЧИКИ ДЛЯ ТЕСТА
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

@dp.message(F.text.in_(["😫 Часто", "😐 Иногда", "😊 Редко", "🎉 Никогда"]))
async def question1_handler(message: types.Message):
    await save_quiz_answer(message.from_user.id, "question1_fatigue", message.text)
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

@dp.message(F.text.in_(["😴 Крепкий", "🛌 Беспокойный", "⏰ Прерывистый", "💤 Бессонница"]))
async def question2_handler(message: types.Message):
    await save_quiz_answer(message.from_user.id, "question2_sleep", message.text)
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

@dp.message(F.text.in_(["💪 Регулярно", "🚶 Иногда", "🧘 Редко", "🚫 Никогда"]))
async def question3_handler(message: types.Message):
    await save_quiz_answer(message.from_user.id, "question3_sport", message.text)
    await message.answer(
        f"✅ Ответ сохранен: {message.text}\n\n"
        "🎉 Тест завершен! Спасибо за ответы!\n\n"
        "На основе ваших ответов мы подготовим персональные рекомендации.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
            ],
            resize_keyboard=True
        )
    )

@dp.message(F.text == "ℹ️ О проекте")
async def about_handler(message: types.Message):
    await message.answer(
        "🏥 GenoLife - современная система анализа здоровья\n\n"
        "Мы помогаем:\n"
        "• Пройти генетический анализ\n"
        "• Получить персональные рекомендации\n"
        "• Улучшить качество жизни"
    )

@dp.message(F.text == "🔙 Назад")
async def back_handler(message: types.Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    await message.answer("Главное меню:", reply_markup=keyboard)

@dp.message()
async def echo_handler(message: types.Message):
    await message.answer(
        "🤔 Используйте кнопки меню или команды:\n"
        "/start - начать работу\n"
        "/profile - ваш профиль"
    )

async def main():
    logger.info("🚀 Запуск бота GenoLife с исправленной БД...")
    
    try:
        await setup_database()
        logger.info("✅ База данных настроена")
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
