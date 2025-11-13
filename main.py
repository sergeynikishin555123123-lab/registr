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
    waiting_address = State()

class QuizStates(StatesGroup):
    answering_questions = State()

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
        buttons = welcome_content.get('buttons', [])
    else:
        welcome_text = "🎉 Добро пожаловать в GenoLife!"
        buttons = ['🧪 Начать тест', '💰 Оплатить анализ', '👤 Профиль', '🔗 Моя реф ссылка', 'ℹ️ О проекте']
    
    # Создаем клавиатуру
    keyboard_buttons = []
    for i in range(0, len(buttons), 2):
        row = buttons[i:i+2]
        keyboard_buttons.append([KeyboardButton(text=btn) for btn in row])
    
    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    
    await message.answer(welcome_text, reply_markup=keyboard)
    logger.info(f"🔗 Пользователь {user.first_name} пришел из: {source}, сценарий: {scenario}")

# ========== ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ ==========

@dp.message(F.text == "🔗 Моя реф ссылка")
async def my_referral_handler(message: types.Message):
    """Генерация реферальной ссылки"""
    bot_username = (await bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
    
    await message.answer(
        f"🔗 Ваша реферальная ссылка:\n\n"
        f"`{referral_link}`\n\n"
        f"Поделитесь этой ссылкой с друзьями!",
        parse_mode="Markdown"
    )

@dp.message(F.text == "💰 Оплатить анализ")
async def payment_handler(message: types.Message, state: FSMContext):
    """Обработчик оплаты анализа"""
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return
    
    # Получаем контент оплаты
    payment_content = content_manager.get('payment_description')
    payment_text = payment_content['text'] if payment_content else "💰 Оплата анализа"
    
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
    
    # Тестовая оплата для MVP
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Тестовая оплата", callback_data=f"test_pay:{order.id}")],
            [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"confirm_pay:{order.id}")]
        ]
    )
    
    await message.answer(payment_text, reply_markup=keyboard)

@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: types.Message):
    """Показывает профиль пользователя"""
    user = await get_user_by_tg_id(message.from_user.id)
    
    if not user:
        await message.answer("❌ Профиль не найден. Напишите /start")
        return
    
    profile_text = (
        f"👤 Ваш профиль:\n"
        f"Имя: {user.first_name or 'Не указано'}\n"
        f"Username: @{user.username or 'Не указан'}\n"
        f"Телефон: {user.phone or 'Не указан'}\n"
        f"Город: {user.city or 'Не указан'}\n"
        f"Часовой пояс: {user.timezone or 'Не указан'}\n"
        f"Статус: {user.status}\n"
        f"Источник: {user.source or 'Не указан'}\n"
        f"Сценарий: {getattr(user, 'scenario', 'default')}\n"
    )
    
    await message.answer(profile_text)

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
                'paid': '✅ Оплачен',
                'shipped': '🚚 Отправлен',
                'delivered': '📦 Доставлен'
            }
            
            status = status_map.get(order.payment_status, order.payment_status)
            
            await message.answer(
                f"📦 Ваш заказ #{order.id}\n"
                f"Статус: {status}\n"
                f"Сумма: {order.amount} руб\n"
                f"Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            await message.answer("❌ У вас нет заказов")

@dp.message(F.text == "ℹ️ О проекте")
async def about_handler(message: types.Message):
    """Информация о проекте"""
    about_text = (
        "🏥 GenoLife - современная система анализа здоровья\n\n"
        "Мы помогаем:\n"
        "• Пройти генетический анализ\n"
        "• Получить персональные рекомендации\n" 
        "• Улучшить качество жизни\n"
        "• Восстановить энергетический баланс\n\n"
        "📞 Свяжитесь с нами для консультации!"
    )
    await message.answer(about_text)

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
                order.transaction_id = f"TEST_{order_id}"
                
                # Обновляем пользователя
                user = await session.get(User, order.user_id)
                user.status = 'paid'
                
                await session.commit()
                
                # Получаем контент успешной оплаты
                success_content = content_manager.get('payment_success')
                success_text = success_content['text'] if success_content else "🎉 Оплата подтверждена!"
                
                await callback.message.answer(
                    success_text,
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
                
                user = await session.get(User, order.user_id)
                user.status = 'paid'
                
                await session.commit()
                
                await callback.message.answer(
                    "🎉 Оплата подтверждена! Спасибо за заказ!\n\n"
                    "Теперь нам нужны ваши контактные данные для доставки набора.",
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

# ========== СБОР КОНТАКТОВ И АДРЕСА ==========

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
        f"✅ Телефон сохранен: {phone}\n\n"
        "Теперь выберите ваш часовой пояс:",
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
                    await message.answer("📍 Введите ваш город:")
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
            [KeyboardButton(text="🧪 Начать тест")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Статус заказа")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🎊 Поздравляем с покупкой! Ваш набор будет отправлен в ближайшее время.\n\n"
        "Менеджер свяжется с вами для уточнения деталей доставки.",
        reply_markup=main_keyboard
    )
    
    await state.clear()
    
    # Уведомление менеджеру о новом заказе
    await notify_managers(
        f"🆕 Новый заказ!\n"
        f"Клиент: {user.first_name} (@{user.username})\n"
        f"Телефон: {user.phone}\n"
        f"Город: {user.city}\n"
        f"Часовой пояс: {user.timezone}"
    )

# ========== СИСТЕМА КВИЗА ==========

@dp.message(F.text == "🧪 Начать тест")
async def start_quiz_handler(message: types.Message, state: FSMContext):
    """Начало квиза"""
    await message.answer(
        "🧪 Отлично! Начинаем тест...\n\n"
        "❓ Вопрос 1: Как часто вы чувствуете усталость?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😫 Часто"), KeyboardButton(text="😐 Иногда")],
                [KeyboardButton(text="😊 Редко"), KeyboardButton(text="🎉 Никогда")],
                [KeyboardButton(text="🔙 Назад в меню")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.answering_questions)
    await state.update_data(current_question=1)

@dp.message(QuizStates.answering_questions, F.text.in_(["😫 Часто", "😐 Иногда", "😊 Редко", "🎉 Никогда"]))
async def question1_handler(message: types.Message, state: FSMContext):
    """Обработчик первого вопроса"""
    user_data = await state.get_data()
    current_question = user_data.get('current_question', 1)
    
    # Сохраняем ответ
    await save_quiz_answer(message.from_user.id, f"question{current_question}_fatigue", message.text)
    
    await message.answer(
        f"✅ Ответ сохранен: {message.text}\n\n"
        "❓ Вопрос 2: Какой у вас обычно сон?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="😴 Крепкий"), KeyboardButton(text="🛌 Беспокойный")],
                [KeyboardButton(text="⏰ Прерывистый"), KeyboardButton(text="💤 Бессонница")],
                [KeyboardButton(text="🔙 Назад в меню")]
            ],
            resize_keyboard=True
        )
    )
    
    await state.update_data(current_question=2)

@dp.message(QuizStates.answering_questions, F.text.in_(["😴 Крепкий", "🛌 Беспокойный", "⏰ Прерывистый", "💤 Бессонница"]))
async def question2_handler(message: types.Message, state: FSMContext):
    """Обработчик второго вопроса"""
    user_data = await state.get_data()
    current_question = user_data.get('current_question', 2)
    
    # Сохраняем ответ
    await save_quiz_answer(message.from_user.id, f"question{current_question}_sleep", message.text)
    
    await message.answer(
        f"✅ Ответ сохранен: {message.text}\n\n"
        "❓ Вопрос 3: Как часто вы занимаетесь спортом?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💪 Регулярно"), KeyboardButton(text="🚶 Иногда")],
                [KeyboardButton(text="🧘 Редко"), KeyboardButton(text="🚫 Никогда")],
                [KeyboardButton(text="🔙 Назад в меню")]
            ],
            resize_keyboard=True
        )
    )
    
    await state.update_data(current_question=3)

@dp.message(QuizStates.answering_questions, F.text.in_(["💪 Регулярно", "🚶 Иногда", "🧘 Редко", "🚫 Никогда"]))
async def question3_handler(message: types.Message, state: FSMContext):
    """Обработчик третьего вопроса - завершение квиза"""
    # Сохраняем ответ
    await save_quiz_answer(message.from_user.id, "question3_sport", message.text)
    
    # Главное меню
    main_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ Ответ сохранен: {message.text}\n\n"
        "🎉 Тест завершен! Спасибо за ответы!\n\n"
        "На основе ваших ответов мы подготовим персональные рекомендации.",
        reply_markup=main_keyboard
    )
    
    await state.clear()

@dp.message(F.text == "🔙 Назад в меню")
async def back_to_menu_handler(message: types.Message, state: FSMContext):
    """Возврат в главное меню из любого состояния"""
    await state.clear()
    
    main_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("Главное меню:", reply_markup=main_keyboard)

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

async def notify_managers(message: str):
    """Отправляет уведомление менеджерам"""
    try:
        if config.MANAGER_GROUP_ID:
            await bot.send_message(config.MANAGER_GROUP_ID, message)
        else:
            # Если группа не настроена, отправляем админу
            await bot.send_message(config.ADMIN_ID, f"📢 {message}")
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
        from sqlalchemy import select, text
        
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
    
    conversion = round((paid_total/users_total)*100, 2) if users_total > 0 else 0
    
    stats_text = (
        f"📊 Статистика бота:\n\n"
        f"👥 Пользователи: {users_total}\n"
        f"💰 Оплатившие: {paid_total}\n"
        f"📦 Заказы: {orders_total}\n"
        f"✅ Оплаченные заказы: {paid_orders_total}\n"
        f"💵 Конверсия: {conversion}%"
    )
    
    await message.answer(stats_text)

@dp.message(Command("upload_content"))
async def upload_content_handler(message: types.Message):
    """Загрузка контента из файла (только для админа)"""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    
    if message.document:
        try:
            file_info = await bot.get_file(message.document.file_id)
            downloaded_file = await bot.download_file(file_info.file_path)
            
            with open("content_upload.csv", "wb") as new_file:
                new_file.write(downloaded_file.read())
            
            # Обновляем контент
            content_manager.load_content()
            await message.answer("✅ Контент успешно обновлен!")
            
        except Exception as e:
            await message.answer(f"❌ Ошибка загрузки: {e}")
    else:
        await message.answer("📎 Отправьте CSV файл с контентом")

# ========== ОБРАБОТЧИК НЕИЗВЕСТНЫХ СООБЩЕНИЙ ==========

@dp.message()
async def unknown_message_handler(message: types.Message):
    """Обработчик неизвестных сообщений"""
    logger.info(f"❓ Неизвестное сообщение от {message.from_user.id}: {message.text}")
    
    main_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🤔 Используйте кнопки меню для навигации:\n\n"
        "• 🧪 Начать тест - пройти опрос о здоровье\n"
        "• 💰 Оплатить анализ - оформить заказ\n" 
        "• 👤 Профиль - посмотреть ваши данные\n"
        "• 🔗 Моя реф ссылка - пригласить друзей\n"
        "• ℹ️ О проекте - узнать о GenoLife",
        reply_markup=main_keyboard
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
