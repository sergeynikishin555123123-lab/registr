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
    create_order, save_quiz_answer, update_order_payment, update_user_status,
    get_user_orders, cleanup_duplicate_users, AsyncSessionLocal
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

class QuizStates(StatesGroup):
    question1 = State()
    question2 = State()
    question3 = State()

# ========== ОБРАБОТЧИК КНОПКИ ОПЛАТЫ ПОСЛЕ КВИЗА ==========

@dp.message(F.text == "💳 Заказать анализ со скидкой")
async def offer_payment_after_quiz_handler(message: types.Message):
    """Обработчик кнопки оплаты после квиза"""
    logger.info(f"💳 Получена кнопка оплаты после квиза от {message.from_user.id}")
    
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return
    
    # Создаем заказ в БД
    order = await create_order(user.id, 2990.00)
    if not order:
        await message.answer("❌ Ошибка создания заказа. Попробуйте еще раз.")
        return
    
    # Инлайн клавиатура для оплаты
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Тестовая оплата", callback_data=f"test_pay:{order.id}")],
            [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"confirm_pay:{order.id}")]
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
    
    if not user:
        await message.answer("❌ Ошибка регистрации. Попробуйте еще раз.")
        return
    
    # Главное меню
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать 60-секундный тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    welcome_text = "🎉 Добро пожаловать в GenoLife!\n\nЯ помогу вам пройти анализ и улучшить здоровье."
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
        "Ответьте на 3 простых вопроса, чтобы узнать больше о вашем здоровье.\n\n"
        "❓ *Вопрос 1/3:* Как часто вы чувствуете усталость?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😫 Постоянно"), KeyboardButton(text="😐 Часто")],
                [KeyboardButton(text="😊 Иногда"), KeyboardButton(text="🎉 Редко")],
                [KeyboardButton(text="🔙 Отменить тест")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.question1)

@dp.message(QuizStates.question1, F.text.in_(["😫 Постоянно", "😐 Часто", "😊 Иногда", "🎉 Редко"]))
async def question1_handler(message: types.Message, state: FSMContext):
    """Обработчик первого вопроса"""
    user = await get_user_by_tg_id(message.from_user.id)
    if user:
        await save_quiz_answer(user.id, "energy_level", message.text)
    
    await message.answer(
        f"✅ *Ответ сохранен*\n\n"
        "❓ *Вопрос 2/3:* Как вы оцениваете качество сна?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😴 Отлично"), KeyboardButton(text="🛌 Нормально")],
                [KeyboardButton(text="⏰ Плохо"), KeyboardButton(text="💤 Бессонница")],
                [KeyboardButton(text="🔙 Назад"), KeyboardButton(text="🔙 Отменить тест")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.question2)

@dp.message(QuizStates.question2, F.text.in_(["😴 Отлично", "🛌 Нормально", "⏰ Плохо", "💤 Бессонница"]))
async def question2_handler(message: types.Message, state: FSMContext):
    """Обработчик второго вопроса"""
    user = await get_user_by_tg_id(message.from_user.id)
    if user:
        await save_quiz_answer(user.id, "sleep_quality", message.text)
    
    await message.answer(
        f"✅ *Ответ сохранен*\n\n"
        "❓ *Вопрос 3/3:* Как часто занимаетесь спортом?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💪 Регулярно"), KeyboardButton(text="🚶 Иногда")],
                [KeyboardButton(text="🧘 Редко"), KeyboardButton(text="🚫 Никогда")],
                [KeyboardButton(text="🔙 Назад"), KeyboardButton(text="🔙 Отменить тест")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.question3)

@dp.message(QuizStates.question3, F.text.in_(["💪 Регулярно", "🚶 Иногда", "🧘 Редко", "🚫 Никогда"]))
async def question3_handler(message: types.Message, state: FSMContext):
    """Обработчик третьего вопроса - завершение квиза"""
    user = await get_user_by_tg_id(message.from_user.id)
    if user:
        await save_quiz_answer(user.id, "activity_level", message.text)
    
    # ПРЕДЛОЖЕНИЕ ОПЛАТЫ ПОСЛЕ КВИЗА
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Заказать анализ со скидкой")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🎉 *Тест завершен!*\n\n"
        "*💡 На основе ваших ответов мы рекомендуем:*\n"
        "• Пройти полный анализ гормонального фона\n"
        "• Получить персональные рекомендации\n"
        "• Начать 14-дневную программу восстановления\n\n"
        "*🎁 Специальное предложение:*\n"
        "Полный анализ со скидкой 20% - всего 2 990 руб!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

# Кнопка "Назад" в квизе
@dp.message(QuizStates.question2, F.text == "🔙 Назад")
async def back_to_question1(message: types.Message, state: FSMContext):
    """Возврат к вопросу 1"""
    await message.answer(
        "❓ *Вопрос 1/3:* Как часто вы чувствуете усталость?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😫 Постоянно"), KeyboardButton(text="😐 Часто")],
                [KeyboardButton(text="😊 Иногда"), KeyboardButton(text="🎉 Редко")],
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

# ========== СИСТЕМА ОПЛАТЫ ==========

@dp.callback_query(F.data.startswith("test_pay:"))
async def test_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик тестовой оплаты"""
    try:
        order_id = int(callback.data.split(":")[1])
        
        # Обновляем заказ
        success = await update_order_payment(order_id, 'paid', f"TEST_{uuid.uuid4().hex[:8]}")
        if not success:
            await callback.answer("❌ Заказ не найден")
            return
        
        # Обновляем пользователя
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT user_id FROM orders WHERE id = :order_id"),
                {"order_id": order_id}
            )
            order_data = result.fetchone()
            if order_data:
                user_id = order_data[0]
                await update_user_status(user_id, 'paid')
                
                # Получаем данные пользователя для уведомления
                user_result = await session.execute(
                    text("SELECT first_name, username FROM users WHERE id = :user_id"),
                    {"user_id": user_id}
                )
                user_data = user_result.fetchone()
                if user_data:
                    user_name = user_data[0]
                    user_username = user_data[1]
        
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
        if user_data:
            await notify_managers(f"💰 Новая оплата от {user_name} (@{user_username})")
            
    except Exception as e:
        logger.error(f"❌ Ошибка тестовой оплаты: {e}")
        await callback.answer("❌ Ошибка оплаты")

@dp.callback_query(F.data.startswith("confirm_pay:"))
async def confirm_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик подтверждения оплаты"""
    try:
        order_id = int(callback.data.split(":")[1])
        
        # Обновляем заказ
        success = await update_order_payment(order_id, 'paid', f"MANUAL_{uuid.uuid4().hex[:8]}")
        if not success:
            await callback.answer("❌ Заказ не найден")
            return
        
        # Обновляем пользователя
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT user_id FROM orders WHERE id = :order_id"),
                {"order_id": order_id}
            )
            order_data = result.fetchone()
            if order_data:
                user_id = order_data[0]
                await update_user_status(user_id, 'paid')
        
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
        f"*Поделитесь с друзьями!*",
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
    order = await create_order(user.id, 2990.00)
    if not order:
        await message.answer("❌ Ошибка создания заказа. Попробуйте еще раз.")
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Тестовая оплата", callback_data=f"test_pay:{order.id}")],
            [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"confirm_pay:{order.id}")]
        ]
    )
    
    await message.answer(
        "💰 *Оплата анализа GenoLife*\n\n"
        "*Что входит:*\n"
        "• Комплект для сбора анализов\n"
        "• Подробный отчет с расшифровкой\n"
        "• Персональные рекомендации\n"
        "• 14-дневная программа восстановления\n\n"
        "*💵 Стоимость:* 2 990 руб",
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
    
    # Получаем заказы пользователя
    orders = await get_user_orders(user.id)
    
    profile_text = (
        f"👤 *Ваш профиль:*\n\n"
        f"*Имя:* {user.first_name or 'Не указано'}\n"
        f"*Username:* @{user.username or 'Не указан'}\n"
        f"*Телефон:* {user.phone or 'Не указан'}\n"
        f"*Город:* {user.city or 'Не указан'}\n"
        f"*Часовой пояс:* {user.timezone or 'Не указан'}\n"
        f"*Статус:* {user.status}\n"
    )
    
    if orders:
        last_order = orders[0]
        status_map = {
            'new': '🆕 Новый',
            'pending': '⏳ Ожидает оплаты', 
            'paid': '✅ Оплачен',
        }
        profile_text += f"\n*Последний заказ:* #{last_order.id} ({status_map.get(last_order.payment_status, last_order.payment_status)})"
    
    await message.answer(profile_text, parse_mode="Markdown")

@dp.message(F.text == "ℹ️ О проекте")
async def about_handler(message: types.Message):
    """Информация о проекте"""
    about_text = (
        "🏥 *GenoLife - современная система анализа здоровья*\n\n"
        "*Что мы делаем:*\n"
        "• Анализируем гормональный профиль\n"
        "• Помогаем восстановить энергетический баланс\n"
        "• Даем персональные рекомендации\n\n"
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
            from sqlalchemy import text
            await session.execute(
                text("UPDATE users SET phone = :phone WHERE id = :user_id"),
                {"phone": phone, "user_id": user.id}
            )
            await session.commit()
    
    # Предлагаем выбрать часовой пояс
    timezone_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Москва (+3)"), KeyboardButton(text="Екатеринбург (+5)")],
            [KeyboardButton(text="Определить по городу")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ *Телефон сохранен:* {phone}\n\n"
        "🕐 *Выберите ваш часовой пояс:*",
        parse_mode="Markdown",
        reply_markup=timezone_keyboard
    )
    
    await state.set_state(OrderStates.waiting_timezone)

@dp.message(OrderStates.waiting_timezone)
async def timezone_handler(message: types.Message, state: FSMContext):
    """Обработчик выбора часового пояса"""
    timezone_map = {
        "Москва (+3)": "Europe/Moscow",
        "Екатеринбург (+5)": "Asia/Yekaterinburg",
        "Определить по городу": "auto"
    }
    
    if message.text in timezone_map:
        timezone = timezone_map[message.text]
        
        # Сохраняем часовой пояс
        async with AsyncSessionLocal() as session:
            user = await get_user_by_tg_id(message.from_user.id)
            if user:
                from sqlalchemy import text
                await session.execute(
                    text("UPDATE users SET timezone = :timezone WHERE id = :user_id"),
                    {"timezone": timezone, "user_id": user.id}
                )
                await session.commit()
        
        # Завершаем процесс
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
            "Менеджер свяжется с вами для уточнения деталей доставки.",
            parse_mode="Markdown",
            reply_markup=main_keyboard
        )
        
        await state.clear()
        
        # Уведомление менеджеру
        user = await get_user_by_tg_id(message.from_user.id)
        if user:
            await notify_managers(
                f"🆕 *НОВЫЙ ЗАКАЗ!*\n\n"
                f"👤 *Клиент:* {user.first_name}\n"
                f"📞 *Телефон:* {user.phone}\n"
                f"🕐 *Часовой пояс:* {timezone}"
            )
    else:
        await message.answer("❌ Пожалуйста, выберите вариант из списка")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

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
        "🤔 Используйте кнопки меню для навигации",
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
