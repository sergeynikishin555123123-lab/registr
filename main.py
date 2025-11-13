import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime
import uuid

from config import config
from database import (
    get_user_by_tg_id, get_or_create_user, create_tables, 
    cleanup_duplicate_users, AsyncSessionLocal, User, Order, QuizAnswer
)
from content_manager import content_manager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаем бота
bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для FSM
class OrderStates(StatesGroup):
    waiting_contacts = State()
    waiting_timezone = State()
    waiting_city = State()

class QuizStates(StatesGroup):
    question1 = State()
    question2 = State()
    question3 = State()

# ========== ОБРАБОТЧИК КНОПКИ ОПЛАТЫ ПОСЛЕ КВИЗА ==========

@dp.message(F.text == "💳 Заказать анализ со скидкой")
async def offer_payment_after_quiz_handler(message: types.Message):
    """Обработчик кнопки оплаты после квиза - ДОЛЖЕН БЫТЬ ПЕРВЫМ"""
    logger.info(f"💳 Получена кнопка оплаты после квиза от {message.from_user.id}")
    
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return
    
    # Создаем заказ в БД
    async with AsyncSessionLocal() as session:
        order = Order(
            user_id=user.id,
            amount=2990.00,
            payment_status='pending'
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
    
    # Инлайн клавиатура для оплаты
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", callback_data=f"payment:{order.id}")],
            [InlineKeyboardButton(text="🧪 Пройти тест еще раз", callback_data="retry_quiz")],
            [InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="contact_manager")]
        ]
    )
    
    await message.answer(
        "💰 *Специальное предложение после теста!*\n\n"
        "🎁 *Полный анализ GenoLife со скидкой 20%*\n\n"
        "*Что входит:*\n"
        "• Комплект для сбора анализов (доставка бесплатно)\n"
        "• 4 пробирки для сбора образцов\n"
        "• Подробный отчет с расшифровкой\n"
        "• Персональные рекомендации\n"
        "• 14-дневная программа восстановления\n\n"
        "*💵 Стоимость:* ~~3 737 руб~~ *2 990 руб*\n"
        "*Экономия: 747 руб!*\n\n"
        "⏰ *Предложение действительно 24 часа*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@dp.message(CommandStart())
async def start_command(message: types.Message):
    """Обработчик команды /start с реферальными ссылками"""
    logger.info(f"📥 Получен /start от {message.from_user.id}")
    
    # Парсим источник и определяем сценарий
    source = 'direct'
    scenario = 'default'
    
    if len(message.text.split()) > 1:
        source_param = message.text.split()[1]
        source = source_param
        
        # Определяем сценарий по источнику
        if source_param.startswith('src_'):
            scenario = source_param[4:]  # Убираем 'src_'
        elif source_param.startswith('ref_'):
            scenario = 'referral'
        elif source_param.startswith('blogger'):
            scenario = source_param
    
    # Сохраняем/обновляем пользователя
    user = await get_or_create_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        source=source
    )
    
    # Обновляем сценарий пользователя
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        db_user.scenario = scenario
        await session.commit()
    
    # Получаем контент для сценария
    welcome_key = f'welcome_{scenario}'
    welcome_content = content_manager.get(welcome_key) or content_manager.get('welcome_default')
    
    if welcome_content:
        welcome_text = welcome_content['text']
    else:
        welcome_text = "🎉 Добро пожаловать в GenoLife!\n\nЯ помогу вам пройти анализ и улучшить здоровье."
    
    # Главное меню
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать 60-секундный тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(welcome_text, reply_markup=keyboard)
    logger.info(f"🔗 Пользователь {user.first_name} пришел из: {source}, сценарий: {scenario}")

# ========== СИСТЕМА КВИЗА ==========

@dp.message(F.text == "🧪 Начать 60-секундный тест")
async def start_quiz_handler(message: types.Message, state: FSMContext):
    """Начало квиза"""
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return
    
    await message.answer(
        "🧪 *60-секундный тест GenoLife*\n\n"
        "Ответьте на 3 простых вопроса, чтобы узнать больше о вашем здоровье и получить персональные рекомендации.\n\n"
        "❓ *Вопрос 1/3:* Как часто вы чувствуете усталость в течение дня?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😫 Постоянно"), KeyboardButton(text="😐 Часто")],
                [KeyboardButton(text="😊 Иногда"), KeyboardButton(text="🎉 Почти никогда")],
                [KeyboardButton(text="🔙 Отменить тест")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.question1)

@dp.message(QuizStates.question1, F.text.in_(["😫 Постоянно", "😐 Часто", "😊 Иногда", "🎉 Почти никогда"]))
async def question1_handler(message: types.Message, state: FSMContext):
    """Обработчик первого вопроса"""
    # Сохраняем ответ
    await save_quiz_answer(message.from_user.id, "energy_level", message.text)
    
    await message.answer(
        f"✅ *Ответ сохранен*\n\n"
        "❓ *Вопрос 2/3:* Как вы оцениваете качество своего сна?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😴 Отлично высыпаюсь"), KeyboardButton(text="🛌 Часто просыпаюсь")],
                [KeyboardButton(text="⏰ Трудно заснуть"), KeyboardButton(text="💤 Бессонница")],
                [KeyboardButton(text="🔙 Назад"), KeyboardButton(text="🔙 Отменить тест")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.question2)

@dp.message(QuizStates.question2, F.text.in_(["😴 Отлично высыпаюсь", "🛌 Часто просыпаюсь", "⏰ Трудно заснуть", "💤 Бессонница"]))
async def question2_handler(message: types.Message, state: FSMContext):
    """Обработчик второго вопроса"""
    # Сохраняем ответ
    await save_quiz_answer(message.from_user.id, "sleep_quality", message.text)
    
    await message.answer(
        f"✅ *Ответ сохранен*\n\n"
        "❓ *Вопрос 3/3:* Как часто вы занимаетесь физической активностью?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💪 3+ раза в неделю"), KeyboardButton(text="🚶 1-2 раза в неделю")],
                [KeyboardButton(text="🧘 Меньше 1 раза"), KeyboardButton(text="🚫 Не занимаюсь")],
                [KeyboardButton(text="🔙 Назад"), KeyboardButton(text="🔙 Отменить тест")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.question3)

@dp.message(QuizStates.question3, F.text.in_(["💪 3+ раза в неделю", "🚶 1-2 раза в неделю", "🧘 Меньше 1 раза", "🚫 Не занимаюсь"]))
async def question3_handler(message: types.Message, state: FSMContext):
    """Обработчик третьего вопроса - завершение квиза"""
    # Сохраняем ответ
    await save_quiz_answer(message.from_user.id, "activity_level", message.text)
    
    # Анализируем ответы и даем рекомендацию
    recommendation = await analyze_quiz_answers(message.from_user.id)
    
    # ПРЕДЛОЖЕНИЕ ОПЛАТЫ ПОСЛЕ КВИЗА
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Заказать анализ со скидкой")],
            [KeyboardButton(text="📊 Посмотреть детальный отчет"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"🎉 *Тест завершен!*\n\n"
        f"{recommendation}\n\n"
        f"*💡 На основе ваших ответов мы рекомендуем:*\n"
        f"• Пройти полный анализ гормонального фона\n"
        f"• Получить персональные рекомендации\n"
        f"• Начать 14-дневную программу восстановления\n\n"
        f"*🎁 Специальное предложение:*\n"
        f"Полный анализ со скидкой 20% - всего 2 990 руб!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

# Кнопка "Назад" в квизе
@dp.message(QuizStates.question2, F.text == "🔙 Назад")
async def back_to_question1(message: types.Message, state: FSMContext):
    """Возврат к вопросу 1"""
    await message.answer(
        "❓ *Вопрос 1/3:* Как часто вы чувствуете усталость в течение дня?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😫 Постоянно"), KeyboardButton(text="😐 Часто")],
                [KeyboardButton(text="😊 Иногда"), KeyboardButton(text="🎉 Почти никогда")],
                [KeyboardButton(text="🔙 Отменить тест")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.question1)

# Отмена теста
@dp.message(QuizStates.question1, F.text == "🔙 Отменить тест")
@dp.message(QuizStates.question2, F.text == "🔙 Отменить тест")
@dp.message(QuizStates.question3, F.text == "🔙 Отменить тест")
async def cancel_quiz_handler(message: types.Message, state: FSMContext):
    """Отмена квиза"""
    await state.clear()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать 60-секундный тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "❌ Тест отменен. Вы можете пройти его в любое время!",
        reply_markup=keyboard
    )

# ========== ОБРАБОТЧИКИ CALLBACK КНОПОК ==========

@dp.callback_query(F.data.startswith("payment:"))
async def payment_callback_handler(callback: types.CallbackQuery):
    """Обработчик перехода к оплате"""
    order_id = int(callback.data.split(":")[1])
    
    # Обновляем статус заказа
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, order_id)
        if order:
            order.payment_status = 'processing'
            await session.commit()
    
    # Тестовая оплата
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Тестовая оплата", callback_data=f"test_pay:{order_id}")],
            [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"confirm_pay:{order_id}")]
        ]
    )
    
    await callback.message.answer(
        "🔐 *Переход к оплате*\n\n"
        "Для тестирования используйте:\n"
        "• *Тестовая оплата* - симуляция успешной оплаты\n"
        "• *Я оплатил(а)* - если уже совершили платеж\n\n"
        "В рабочей версии здесь будет ссылка на ЮКассу.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "retry_quiz")
async def retry_quiz_handler(callback: types.CallbackQuery, state: FSMContext):
    """Повторное прохождение квиза"""
    await callback.message.answer(
        "🧪 *Начинаем тест заново!*\n\n"
        "❓ *Вопрос 1/3:* Как часто вы чувствуете усталость в течение дня?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😫 Постоянно"), KeyboardButton(text="😐 Часто")],
                [KeyboardButton(text="😊 Иногда"), KeyboardButton(text="🎉 Почти никогда")],
                [KeyboardButton(text="🔙 Отменить тест")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.question1)
    await callback.answer()

@dp.callback_query(F.data == "contact_manager")
async def contact_manager_handler(callback: types.CallbackQuery):
    """Обработчик связи с менеджером"""
    await callback.message.answer(
        "📞 *Связь с менеджером*\n\n"
        "Наш менеджер свяжется с вами в ближайшее время в рабочие часы.\n\n"
        "Если вопрос срочный, вы можете написать нам напрямую: @genolife_support",
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== СИСТЕМА ОПЛАТЫ ==========

@dp.callback_query(F.data.startswith("test_pay:"))
async def test_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик тестовой оплаты"""
    try:
        order_id = int(callback.data.split(":")[1])
        
        async with AsyncSessionLocal() as session:
            # Обновляем заказ
            order = await session.get(Order, order_id)
            if order:
                order.payment_status = 'paid'
                order.payment_date = datetime.utcnow()
                order.transaction_id = f"TEST_{uuid.uuid4().hex[:8]}"
                
                # Обновляем пользователя
                user = await session.get(User, order.user_id)
                user.status = 'paid'
                
                await session.commit()
                
                await callback.message.answer(
                    "🎉 *Оплата подтверждена! Спасибо за заказ!*\n\n"
                    "Теперь нам нужны ваши контактные данные для доставки набора.",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="📞 Оставить контакты", request_contact=True)]],
                        resize_keyboard=True
                    )
                )
                
                await state.set_state(OrderStates.waiting_contacts)
                await callback.answer("✅ Тестовая оплата подтверждена!")
                
                # Уведомление менеджеру
                await notify_managers(f"💰 Новая оплата от {user.first_name} (@{user.username})")
            else:
                await callback.answer("❌ Заказ не найден")
                
    except Exception as e:
        logger.error(f"❌ Ошибка тестовой оплаты: {e}")
        await callback.answer("❌ Ошибка оплаты")

@dp.callback_query(F.data.startswith("confirm_pay:"))
async def confirm_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик подтверждения оплаты"""
    try:
        order_id = int(callback.data.split(":")[1])
        
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, order_id)
            if order:
                order.payment_status = 'paid'
                order.payment_date = datetime.utcnow()
                order.transaction_id = f"MANUAL_{uuid.uuid4().hex[:8]}"
                
                user = await session.get(User, order.user_id)
                user.status = 'paid'
                
                await session.commit()
                
                await callback.message.answer(
                    "🎉 *Оплата подтверждена! Спасибо за заказ!*\n\n"
                    "Теперь нам нужны ваши контактные данные для доставки набора.",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text="📞 Оставить контакты", request_contact=True)]],
                        resize_keyboard=True
                    )
                )
                
                await state.set_state(OrderStates.waiting_contacts)
                await callback.answer("✅ Оплата подтверждена!")
                
                await notify_managers(f"💰 Подтверждена оплата от {user.first_name}")
            else:
                await callback.answer("❌ Заказ не найден")
                
    except Exception as e:
        logger.error(f"❌ Ошибка подтверждения оплаты: {e}")
        await callback.answer("❌ Ошибка")

# ========== ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ ==========

@dp.message(F.text == "🔗 Моя реф ссылка")
async def my_referral_handler(message: types.Message):
    """Генерация реферальной ссылки"""
    bot_username = (await bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
    
    await message.answer(
        f"🔗 *Ваша реферальная ссылка:*\n\n"
        f"`{referral_link}`\n\n"
        f"*Поделитесь с друзьями и получайте бонусы!*",
        parse_mode="Markdown"
    )

@dp.message(F.text == "💰 Оплатить анализ")
async def direct_payment_handler(message: types.Message):
    """Прямой переход к оплате без квиза"""
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return
    
    # Создаем заказ в БД
    async with AsyncSessionLocal() as session:
        order = Order(
            user_id=user.id,
            amount=2990.00,
            payment_status='pending'
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", callback_data=f"payment:{order.id}")]
        ]
    )
    
    await message.answer(
        "💰 *Оплата анализа GenoLife*\n\n"
        "*Что входит:*\n"
        "• Комплект для сбора анализов\n"
        "• Подробный отчет с расшифровкой\n"
        "• Персональные рекомендации\n"
        "• 14-дневная программа восстановления\n\n"
        "*💵 Стоимость:* 2 990 руб\n\n"
        "*Рекомендуем сначала пройти тест для получения скидки!*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: types.Message):
    """Показывает профиль пользователя"""
    user = await get_user_by_tg_id(message.from_user.id)
    
    if not user:
        await message.answer("❌ Профиль не найден. Напишите /start")
        return
    
    # Получаем последний заказ
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
        )
        order = result.scalar_one_or_none()
    
    profile_text = (
        f"👤 *Ваш профиль:*\n\n"
        f"*Имя:* {user.first_name or 'Не указано'}\n"
        f"*Username:* @{user.username or 'Не указан'}\n"
        f"*Телефон:* {user.phone or 'Не указан'}\n"
        f"*Город:* {user.city or 'Не указан'}\n"
        f"*Часовой пояс:* {user.timezone or 'Не указан'}\n"
        f"*Статус:* {user.status}\n"
        f"*Источник:* {user.source or 'Не указан'}\n"
        f"*Сценарий:* {getattr(user, 'scenario', 'default')}\n"
    )
    
    if order:
        status_map = {
            'new': '🆕 Новый',
            'pending': '⏳ Ожидает оплаты', 
            'processing': '🔄 В обработке',
            'paid': '✅ Оплачен',
            'shipped': '🚚 Отправлен',
            'delivered': '📦 Доставлен'
        }
        profile_text += f"\n*Последний заказ:* #{order.id} ({status_map.get(order.payment_status, order.payment_status)})"
    
    await message.answer(profile_text, parse_mode="Markdown")

@dp.message(F.text == "📦 Статус заказа")
async def order_status_handler(message: types.Message):
    """Показывает статус заказа"""
    user = await get_user_by_tg_id(message.from_user.id)
    
    if not user:
        await message.answer("❌ Пользователь не найден")
        return
        
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
        )
        order = result.scalar_one_or_none()
        
        if order:
            status_map = {
                'new': '🆕 Новый',
                'pending': '⏳ Ожидает оплаты', 
                'processing': '🔄 В обработке',
                'paid': '✅ Оплачен - ожидайте звонка менеджера',
                'shipped': '🚚 Набор отправлен',
                'delivered': '📦 Набор доставлен'
            }
            
            status = status_map.get(order.payment_status, order.payment_status)
            
            status_text = (
                f"📦 *Статус вашего заказа #{order.id}:*\n\n"
                f"*Статус:* {status}\n"
                f"*Сумма:* {order.amount} руб\n"
                f"*Дата заказа:* {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            )
            
            if order.tracking_code:
                status_text += f"*Трек-номер:* {order.tracking_code}\n"
            if order.eta_date:
                status_text += f"*Примерная дата доставки:* {order.eta_date.strftime('%d.%m.%Y')}\n"
            
            await message.answer(status_text, parse_mode="Markdown")
        else:
            await message.answer("❌ У вас нет активных заказов")

@dp.message(F.text == "ℹ️ О проекте")
async def about_handler(message: types.Message):
    """Информация о проекте"""
    about_text = (
        "🏥 *GenoLife - современная система анализа здоровья*\n\n"
        "*Что мы делаем:*\n"
        "• Анализируем гормональный профиль\n"
        "• Помогаем восстановить энергетический баланс\n"
        "• Даем персональные рекомендации\n"
        "• Сопровождаем 14-дневной программой\n\n"
        "*Как это работает:*\n"
        "1. Проходите простой тест\n"
        "2. Заказываете анализ со скидкой\n"
        "3. Получаете набор для сбора анализов\n"
        "4. Собираете образцы по инструкции\n"
        "5. Получаете подробный отчет\n"
        "6. Начинаете программу восстановления\n\n"
        "*📞 Свяжитесь с нами для консультации!*"
    )
    await message.answer(about_text, parse_mode="Markdown")

# ========== СБОР КОНТАКТОВ И ЧАСОВОГО ПОЯСА ==========

@dp.message(OrderStates.waiting_contacts, F.contact)
async def contact_received_handler(message: types.Message, state: FSMContext):
    """Обработчик получения контакта"""
    phone = message.contact.phone_number
    
    # Сохраняем телефон
    async with AsyncSessionLocal() as session:
        user = await get_user_by_tg_id(message.from_user.id)
        if user:
            db_user = await session.get(User, user.id)
            db_user.phone = phone
            await session.commit()
    
    # Предлагаем выбрать часовой пояс
    timezone_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Москва (+3)"), KeyboardButton(text="Калининград (+2)")],
            [KeyboardButton(text="Екатеринбург (+5)"), KeyboardButton(text="Определить по городу")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ *Телефон сохранен:* {phone}\n\n"
        "🕐 *Теперь выберите ваш часовой пояс:*\n\n"
        "Это нужно для:\n"
        "• Напоминаний о сборе анализов\n"
        "• Планирования времени курьера\n"
        "• Утренних уведомлений",
        parse_mode="Markdown",
        reply_markup=timezone_keyboard
    )
    
    await state.set_state(OrderStates.waiting_timezone)

@dp.message(OrderStates.waiting_contacts)
async def wrong_contact_handler(message: types.Message):
    """Обрабатывает некорректные сообщения в состоянии ожидания контакта"""
    await message.answer(
        "❌ Пожалуйста, нажмите кнопку '📞 Оставить контакты' для отправки телефона"
    )

@dp.message(OrderStates.waiting_timezone)
async def timezone_handler(message: types.Message, state: FSMContext):
    """Обработчик выбора часового пояса"""
    timezone_map = {
        "Москва (+3)": "Europe/Moscow",
        "Калининград (+2)": "Europe/Kaliningrad", 
        "Екатеринбург (+5)": "Asia/Yekaterinburg",
        "Определить по городу": "auto"
    }
    
    if message.text in timezone_map:
        timezone = timezone_map[message.text]
        
        # Сохраняем часовой пояс
        async with AsyncSessionLocal() as session:
            user = await get_user_by_tg_id(message.from_user.id)
            if user:
                db_user = await session.get(User, user.id)
                db_user.timezone = timezone
                
                if message.text == "Определить по городу":
                    await message.answer("📍 *Введите ваш город для определения часового пояса:*", parse_mode="Markdown")
                    await state.set_state(OrderStates.waiting_city)
                    return
                else:
                    db_user.city = message.text.split(' ')[0]  # Берем название города
                    await session.commit()
                    
                    # Завершаем процесс
                    await finish_order_process(message, state, db_user)
    else:
        await message.answer("❌ Пожалуйста, выберите вариант из списка")

@dp.message(OrderStates.waiting_city)
async def city_handler(message: types.Message, state: FSMContext):
    """Обработчик ввода города"""
    city = message.text
    
    # Сохраняем город
    async with AsyncSessionLocal() as session:
        user = await get_user_by_tg_id(message.from_user.id)
        if user:
            db_user = await session.get(User, user.id)
            db_user.city = city
            await session.commit()
            
            # Завершаем процесс
            await finish_order_process(message, state, db_user)

async def finish_order_process(message: types.Message, state: FSMContext, user: User):
    """Завершает процесс оформления заказа"""
    main_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Статус заказа"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🎊 *Поздравляем с покупкой!*\n\n"
        "✅ *Ваш заказ оформлен!*\n\n"
        "*Что дальше:*\n"
        "1. В ближайшее время менеджер свяжется для уточнения деталей доставки\n"
        "2. Вы получите набор для сбора анализов\n"
        "3. После сбора образцов курьер заберет их\n"
        "4. Через 7-10 дней вы получите подробный отчет\n\n"
        "📞 *По всем вопросам обращайтесь к менеджеру*",
        parse_mode="Markdown",
        reply_markup=main_keyboard
    )
    
    await state.clear()
    
    # Уведомление менеджеру о новом заказе
    await notify_managers(
        f"🆕 *НОВЫЙ ЗАКАЗ!*\n\n"
        f"👤 *Клиент:* {user.first_name} (@{user.username})\n"
        f"📞 *Телефон:* {user.phone}\n"
        f"📍 *Город:* {user.city}\n"
        f"🕐 *Часовой пояс:* {user.timezone}\n"
        f"🔗 *Источник:* {user.source}\n\n"
        f"💵 *Сумма:* 2 990 руб\n"
        f"🆔 *ID заказа:* {user.id}"
    )

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def save_quiz_answer(tg_id: int, question_id: str, answer: str):
    """Сохраняет ответ на вопрос квиза"""
    try:
        user = await get_user_by_tg_id(tg_id)
        if user:
            async with AsyncSessionLocal() as session:
                quiz_answer = QuizAnswer(
                    user_id=user.id,
                    question_id=question_id,
                    answer=answer
                )
                session.add(quiz_answer)
                await session.commit()
                logger.info(f"💾 Сохранен ответ: {question_id} = {answer}")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения ответа: {e}")

async def analyze_quiz_answers(tg_id: int) -> str:
    """Анализирует ответы квиза и возвращает рекомендацию"""
    user = await get_user_by_tg_id(tg_id)
    if not user:
        return "Рекомендуем пройти полный анализ для оценки состояния здоровья."
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(QuizAnswer).where(QuizAnswer.user_id == user.id)
        )
        answers = result.scalars().all()
    
    # Простой анализ на основе ответов
    energy_issues = any('😫' in answer.answer or '😐' in answer.answer for answer in answers if answer.question_id == 'energy_level')
    sleep_issues = any('🛌' in answer.answer or '⏰' in answer.answer or '💤' in answer.answer for answer in answers if answer.question_id == 'sleep_quality')
    activity_low = any('🧘' in answer.answer or '🚫' in answer.answer for answer in answers if answer.question_id == 'activity_level')
    
    if energy_issues and sleep_issues:
        return "На основе ваших ответов мы видим признаки нарушения энергетического баланса и качества сна. Это может быть связано с гормональным дисбалансом."
    elif energy_issues:
        return "Вы часто чувствуете усталость, что может указывать на необходимость коррекции режима дня и питания."
    elif sleep_issues:
        return "Проблемы со сном могут влиять на общее состояние здоровья и уровень энергии."
    else:
        return "Ваши ответы указывают на хорошее общее состояние, но мы рекомендуем профилактический анализ для поддержания здоровья."

async def notify_managers(message: str):
    """Отправляет уведомление менеджерам"""
    try:
        if config.MANAGER_GROUP_ID:
            await bot.send_message(config.MANAGER_GROUP_ID, message, parse_mode="Markdown")
        else:
            # Если группа не настроена, отправляем админу
            await bot.send_message(config.ADMIN_ID, f"📢 {message}", parse_mode="Markdown")
        logger.info("📢 Уведомление отправлено менеджерам")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления менеджерам: {e}")

# ========== АДМИН КОМАНДЫ ==========

@dp.message(Command("cleanup"))
async def cleanup_command(message: types.Message):
    """Очистка дублирующихся пользователей (только для админа)"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
        
    await cleanup_duplicate_users()
    await message.answer("✅ Дублирующиеся пользователи очищены")

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    """Статистика бота (только для админа)"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import text
        
        # Статистика пользователей
        users_count = await session.execute(text("SELECT COUNT(*) FROM users"))
        users_total = users_count.scalar()
        
        paid_users = await session.execute(text("SELECT COUNT(*) FROM users WHERE status = 'paid'"))
        paid_total = paid_users.scalar()
        
        # Статистика заказов
        orders_count = await session.execute(text("SELECT COUNT(*) FROM orders"))
        orders_total = orders_count.scalar()
        
        paid_orders = await session.execute(text("SELECT COUNT(*) FROM orders WHERE payment_status = 'paid'"))
        paid_orders_total = paid_orders.scalar()
        
        # Статистика квизов
        quiz_count = await session.execute(text("SELECT COUNT(DISTINCT user_id) FROM quiz_answers"))
        quiz_total = quiz_count.scalar()
    
    conversion = round((paid_total/users_total)*100, 2) if users_total > 0 else 0
    quiz_conversion = round((paid_total/quiz_total)*100, 2) if quiz_total > 0 else 0
    
    stats_text = (
        f"📊 *Статистика бота:*\n\n"
        f"👥 *Пользователи:* {users_total}\n"
        f"🧪 *Прошли квиз:* {quiz_total}\n"
        f"💰 *Оплатившие:* {paid_total}\n"
        f"📦 *Заказы:* {orders_total}\n"
        f"✅ *Оплаченные заказы:* {paid_orders_total}\n"
        f"💵 *Общая конверсия:* {conversion}%\n"
        f"🎯 *Конверсия из квиза:* {quiz_conversion}%"
    )
    
    await message.answer(stats_text, parse_mode="Markdown")

# ========== ОБРАБОТЧИК НЕИЗВЕСТНЫХ СООБЩЕНИЙ ==========

@dp.message()
async def unknown_message_handler(message: types.Message):
    """Обработчик неизвестных сообщений"""
    logger.info(f"❓ Неизвестное сообщение от {message.from_user.id}: {message.text}")
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать 60-секундный тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🤔 *Используйте кнопки меню для навигации:*\n\n"
        "• 🧪 *Начать тест* - пройти опрос и получить скидку\n"
        "• 💰 *Оплатить анализ* - сразу перейти к оплате\n" 
        "• 👤 *Профиль* - посмотреть ваши данные\n"
        "• 🔗 *Моя реф ссылка* - пригласить друзей\n"
        "• ℹ️ *О проекте* - узнать о GenoLife\n"
        "• 📦 *Статус заказа* - отследить ваш заказ",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

async def main():
    logger.info("🚀 Запуск бота GenoLife...")
    
    try:
        await create_tables()
        logger.info("✅ База данных настроена")
        
        # Загружаем контент
        content_manager.load_content()
        logger.info("✅ Контент загружен")
        
        # Тестовое сообщение админу
        await bot.send_message(config.ADMIN_ID, "🤖 Бот GenoLife запущен и готов к работе!")
        
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
