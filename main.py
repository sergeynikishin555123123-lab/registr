import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

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
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=btn)] for btn in buttons],
        resize_keyboard=True
    )
    
    await message.answer(welcome_text, reply_markup=keyboard)
    logger.info(f"🔗 Пользователь {user.first_name} пришел из: {source}, сценарий: {scenario}")

# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========

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

# ========== СИСТЕМА ОПЛАТЫ ==========

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
                
    except Exception as e:
        logger.error(f"❌ Ошибка тестовой оплаты: {e}")
        await callback.answer("❌ Ошибка оплаты")

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

# ========== ПРОФИЛЬ И СТАТУС ==========

@dp.message(Command("profile"))
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
        f"Сценарий: {user.scenario or 'default'}\n"
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
        order = await session.execute(
            f"SELECT * FROM orders WHERE user_id = {user.id} ORDER BY created_at DESC LIMIT 1"
        )
        order_data = order.fetchone()
        
        if order_data:
            status_map = {
                'new': '🆕 Новый',
                'pending': '⏳ Ожидает оплаты', 
                'paid': '✅ Оплачен',
                'shipped': '🚚 Отправлен',
                'delivered': '📦 Доставлен'
            }
            
            status = status_map.get(order_data.payment_status, order_data.payment_status)
            
            await message.answer(
                f"📦 Ваш заказ #{order_data.id}\n"
                f"Статус: {status}\n"
                f"Сумма: {order_data.amount} руб\n"
                f"Дата: {order_data.created_at.strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            await message.answer("❌ У вас нет заказов")

# ========== УВЕДОМЛЕНИЯ МЕНЕДЖЕРАМ ==========

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
        # Статистика пользователей
        users_count = await session.execute("SELECT COUNT(*) FROM users")
        users_total = users_count.scalar()
        
        paid_users = await session.execute("SELECT COUNT(*) FROM users WHERE status = 'paid'")
        paid_total = paid_users.scalar()
        
        # Статистика заказов
        orders_count = await session.execute("SELECT COUNT(*) FROM orders")
        orders_total = orders_count.scalar()
        
        paid_orders = await session.execute("SELECT COUNT(*) FROM orders WHERE payment_status = 'paid'")
        paid_orders_total = paid_orders.scalar()
    
    stats_text = (
        f"📊 Статистика бота:\n\n"
        f"👥 Пользователи: {users_total}\n"
        f"💰 Оплатившие: {paid_total}\n"
        f"📦 Заказы: {orders_total}\n"
        f"✅ Оплаченные заказы: {paid_orders_total}\n"
        f"💵 Конверсия: {round((paid_total/users_total)*100, 2) if users_total > 0 else 0}%"
    )
    
    await message.answer(stats_text)

# ========== ЗАГРУЗЧИК КОНТЕНТА ==========

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

# ========== ОБРАБОТЧИКИ КВИЗА ==========

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
                [KeyboardButton(text="🔙 Назад")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(QuizStates.answering_questions)

# Добавьте обработчики для вопросов квиза аналогично предыдущей версии

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

async def main():
    logger.info("🚀 Запуск бота GenoLife...")
    
    try:
        await create_tables()
        logger.info("✅ База данных настроена")
        
        # Загружаем контент
        content_manager.load_content()
        logger.info("✅ Контент загружен")
        
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
