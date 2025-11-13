import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime, timedelta
import uuid

from config import config
from database import (
    get_user_by_tg_id, get_or_create_user, create_tables, 
    create_order, save_quiz_answer, update_order_payment, update_user_status,
    update_user_contact, update_user_timezone, get_user_orders,
    get_user_quiz_answers, start_program_for_user
)
from managers import init_manager_bot, manager_bot
from notifications import NotificationManager
from programs import ProgramManager
from content_manager import content_manager
from scheduler import init_scheduler, scheduler_manager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Инициализация менеджеров
manager_bot = init_manager_bot(bot)
notification_manager = NotificationManager(bot)
program_manager = ProgramManager(bot)
scheduler_manager = init_scheduler(bot)

# ========== СОСТОЯНИЯ FSM ==========

class OrderStates(StatesGroup):
    waiting_contacts = State()
    waiting_timezone = State()
    waiting_address = State()

class QuizStates(StatesGroup):
    question1 = State()
    question2 = State() 
    question3 = State()

class CollectionStates(StatesGroup):
    planning = State()
    confirming = State()

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========

@dp.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    """Обработчик команды /start с реферальными ссылками"""
    logger.info(f"📥 /start от {message.from_user.id} - {message.from_user.first_name}")
    
    try:
        # Очищаем состояние
        await state.clear()
        
        # Парсим параметры старта
        source = 'direct'
        scenario = 'default'
        
        if len(message.text.split()) > 1:
            start_params = message.text.split()[1]
            source = start_params
            
            # Определяем сценарий по источнику
            if start_params.startswith('src_'):
                scenario = start_params[4:]  # Убираем 'src_'
            elif start_params.startswith('ref_'):
                scenario = 'referral'
            elif start_params.startswith('blogger'):
                scenario = start_params
            
            logger.info(f"🔗 Источник: {source}, сценарий: {scenario}")

        # Получаем или создаем пользователя
        user = await get_or_create_user(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            source=source,
            scenario=scenario
        )
        
        if not user:
            await message.answer("❌ Ошибка регистрации. Попробуйте еще раз.")
            return

        # Получаем контент для приветствия
        welcome_content = content_manager.get('welcome', scenario=scenario)
        if not welcome_content:
            welcome_content = content_manager.get('welcome_default')
        
        # Создаем клавиатуру из контента
        keyboard = ReplyKeyboardMarkup(
            keyboard=welcome_content['buttons'],
            resize_keyboard=True
        )
        
        await message.answer(welcome_content['text'], reply_markup=keyboard)
        
        # Уведомляем менеджеров о новом лиде
        await manager_bot.notify_managers(
            f"🆕 *Новый лид!*\n"
            f"👤 {user.first_name} (@{user.username})\n"
            f"🔗 Источник: {source}\n"
            f"🎯 Сценарий: {scenario}"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /start: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте еще раз.")

@dp.message(F.text == "🧪 Начать 60-секундный тест")
async def start_quiz_handler(message: types.Message, state: FSMContext):
    """Запуск квиза"""
    try:
        user = await get_user_by_tg_id(message.from_user.id)
        if not user:
            await message.answer("❌ Сначала напишите /start")
            return
        
        quiz_content = content_manager.get('quiz_welcome')
        if not quiz_content:
            await message.answer("🧪 Начинаем тест...")
            quiz_content = {"text": "🧪 *60-секундный тест*", "buttons": []}
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=quiz_content['buttons'] or [[KeyboardButton(text="✅ Начать тест")]],
            resize_keyboard=True
        )
        
        await message.answer(quiz_content['text'], reply_markup=keyboard, parse_mode="Markdown")
        await state.set_state(QuizStates.question1)
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска квиза: {e}")
        await message.answer("❌ Ошибка запуска теста")

@dp.message(QuizStates.question1)
async def quiz_question1_handler(message: types.Message, state: FSMContext):
    """Первый вопрос квиза"""
    try:
        if message.text == "🔙 Назад":
            await start_command(message, state)
            return
            
        user = await get_user_by_tg_id(message.from_user.id)
        if user:
            await save_quiz_answer(user.id, "energy_level", message.text)
        
        question_content = content_manager.get('quiz_question1')
        if not question_content:
            question_content = {
                "text": "❓ *Вопрос 1/3:* Как часто вы чувствуете усталость?",
                "buttons": [
                    [KeyboardButton(text="😫 Постоянно"), KeyboardButton(text="😐 Часто")],
                    [KeyboardButton(text="😊 Иногда"), KeyboardButton(text="🎉 Редко")],
                    [KeyboardButton(text="🔙 Назад")]
                ]
            }
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=question_content['buttons'],
            resize_keyboard=True
        )
        
        await message.answer(question_content['text'], reply_markup=keyboard, parse_mode="Markdown")
        await state.set_state(QuizStates.question2)
        
    except Exception as e:
        logger.error(f"❌ Ошибка вопроса 1: {e}")
        await message.answer("❌ Ошибка сохранения ответа")

@dp.message(QuizStates.question2)
async def quiz_question2_handler(message: types.Message, state: FSMContext):
    """Второй вопрос квиза"""
    try:
        if message.text == "🔙 Назад":
            await state.set_state(QuizStates.question1)
            await quiz_question1_handler(message, state)
            return
            
        user = await get_user_by_tg_id(message.from_user.id)
        if user:
            await save_quiz_answer(user.id, "sleep_quality", message.text)
        
        question_content = content_manager.get('quiz_question2')
        if not question_content:
            question_content = {
                "text": "✅ *Ответ сохранен*\n\n❓ *Вопрос 2/3:* Как вы оцениваете качество сна?",
                "buttons": [
                    [KeyboardButton(text="😴 Отлично"), KeyboardButton(text="🛌 Нормально")],
                    [KeyboardButton(text="⏰ Плохо"), KeyboardButton(text="💤 Бессонница")],
                    [KeyboardButton(text="🔙 Назад")]
                ]
            }
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=question_content['buttons'],
            resize_keyboard=True
        )
        
        await message.answer(question_content['text'], reply_markup=keyboard, parse_mode="Markdown")
        await state.set_state(QuizStates.question3)
        
    except Exception as e:
        logger.error(f"❌ Ошибка вопроса 2: {e}")
        await message.answer("❌ Ошибка сохранения ответа")

@dp.message(QuizStates.question3)
async def quiz_question3_handler(message: types.Message, state: FSMContext):
    """Третий вопрос квиза и завершение"""
    try:
        if message.text == "🔙 Назад":
            await state.set_state(QuizStates.question2)
            await quiz_question2_handler(message, state)
            return
            
        user = await get_user_by_tg_id(message.from_user.id)
        if user:
            await save_quiz_answer(user.id, "activity_level", message.text)
            
            # Уведомляем менеджеров о завершении квиза
            await manager_bot.notify_managers(
                f"🧪 *Квиз завершен!*\n"
                f"👤 {user.first_name} (@{user.username})\n"
                f"💬 Ответы сохранены"
            )
        
        complete_content = content_manager.get('quiz_complete')
        if not complete_content:
            complete_content = {
                "text": "🎉 *Тест завершен!*\n\nНа основе ваших ответов мы подготовили специальное предложение.\n\n*Полный анализ со скидкой 20%* - 2 990 руб вместо 3 737 руб!",
                "buttons": [
                    [KeyboardButton(text="💳 Заказать со скидкой")],
                    [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="ℹ️ О проекте")]
                ]
            }
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=complete_content['buttons'],
            resize_keyboard=True
        )
        
        await message.answer(complete_content['text'], reply_markup=keyboard, parse_mode="Markdown")
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ Ошибка вопроса 3: {e}")
        await message.answer("❌ Ошибка завершения теста")

@dp.message(F.text == "💳 Заказать со скидкой")
@dp.message(F.text == "💰 Оплатить анализ")
async def payment_handler(message: types.Message, state: FSMContext):
    """Обработчик оплаты"""
    try:
        user = await get_user_by_tg_id(message.from_user.id)
        if not user:
            await message.answer("❌ Сначала напишите /start")
            return
        
        # Создаем заказ
        order = await create_order(user.id, 2990.00)
        if not order:
            await message.answer("❌ Ошибка создания заказа")
            return
        
        payment_content = content_manager.get('payment_description')
        if not payment_content:
            payment_content = {
                "text": "💰 *Оплата анализа*\n\nСтоимость полного анализа: 2 990 руб.",
                "buttons": []
            }
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Тестовая оплата", callback_data=f"test_pay:{order.id}")],
                [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"confirm_pay:{order.id}")]
            ]
        )
        
        await message.answer(
            payment_content['text'],
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки оплаты: {e}")
        await message.answer("❌ Ошибка создания заказа")

@dp.callback_query(F.data.startswith("test_pay:"))
async def test_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    """Тестовая оплата (для демонстрации)"""
    try:
        order_id = int(callback.data.split(":")[1])
        
        # Обновляем статус заказа
        success = await update_order_payment(order_id, 'paid', f"TEST_{uuid.uuid4().hex[:8]}")
        if not success:
            await callback.answer("❌ Заказ не найден")
            return
        
        user = await get_user_by_tg_id(callback.from_user.id)
        if user:
            await update_user_status(user.id, 'paid')
            
            # Уведомляем менеджеров
            await manager_bot.notify_managers(
                f"💰 *НОВАЯ ОПЛАТА!*\n"
                f"👤 {user.first_name} (@{user.username})\n"
                f"💵 Сумма: 2 990 руб\n"
                f"🆔 Заказ: #{order_id}"
            )
            
            # Отправляем карточку клиента менеджерам
            await manager_bot.send_user_card(user.id, order_id)
        
        success_content = content_manager.get('payment_success')
        if not success_content:
            success_content = {
                "text": "🎉 *Оплата подтверждена!*\n\nСпасибо за заказ! Теперь нам нужны ваши контактные данные для доставки набора.",
                "buttons": [[KeyboardButton(text="📞 Оставить контакты", request_contact=True)]]
            }
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=success_content['buttons'],
            resize_keyboard=True
        )
        
        await callback.message.answer(success_content['text'], reply_markup=keyboard, parse_mode="Markdown")
        await state.set_state(OrderStates.waiting_contacts)
        await callback.answer("✅ Тестовая оплата подтверждена!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестовой оплаты: {e}")
        await callback.answer("❌ Ошибка оплаты")

@dp.message(OrderStates.waiting_contacts, F.contact)
async def contact_received_handler(message: types.Message, state: FSMContext):
    """Обработчик получения контактов"""
    try:
        phone = message.contact.phone_number
        user = await get_user_by_tg_id(message.from_user.id)
        if user:
            await update_user_contact(user.id, phone)
            
            await manager_bot.notify_managers(
                f"📞 *Контакты получены!*\n"
                f"👤 {user.first_name}\n"
                f"📱 Телефон: {phone}"
            )
        
        timezone_content = content_manager.get('timezone_selection')
        if not timezone_content:
            timezone_content = {
                "text": "🕐 *Выберите ваш часовой пояс:*",
                "buttons": [
                    [KeyboardButton(text="Москва (+3)"), KeyboardButton(text="Екатеринбург (+5)")],
                    [KeyboardButton(text="Калининград (+2)"), KeyboardButton(text="Определить по городу")]
                ]
            }
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=timezone_content['buttons'],
            resize_keyboard=True
        )
        
        await message.answer(
            f"✅ *Телефон сохранен:* {phone}\n\n{timezone_content['text']}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await state.set_state(OrderStates.waiting_timezone)
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки контактов: {e}")
        await message.answer("❌ Ошибка сохранения контактов")

@dp.message(OrderStates.waiting_timezone)
async def timezone_handler(message: types.Message, state: FSMContext):
    """Обработчик выбора часового пояса"""
    try:
        timezone_map = {
            "Москва (+3)": "Europe/Moscow",
            "Екатеринбург (+5)": "Asia/Yekaterinburg", 
            "Калининград (+2)": "Europe/Kaliningrad",
            "Определить по городу": "auto"
        }
        
        if message.text not in timezone_map:
            await message.answer("❌ Пожалуйста, выберите вариант из списка")
            return
        
        timezone = timezone_map[message.text]
        user = await get_user_by_tg_id(message.from_user.id)
        
        if user:
            city = None
            if message.text == "Определить по городу":
                city = "auto"
                await state.set_state(OrderStates.waiting_address)
                await message.answer(
                    "📍 *Введите ваш город:*",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
                return
            else:
                city = message.text.split(' ')[0]
            
            await update_user_timezone(user.id, timezone, city)
            
            await manager_bot.notify_managers(
                f"📍 *Данные для доставки!*\n"
                f"👤 {user.first_name}\n"
                f"🏙️ Город: {city}\n"
                f"🕐 Часовой пояс: {timezone}"
            )
        
        main_content = content_manager.get('welcome_default')
        keyboard = ReplyKeyboardMarkup(
            keyboard=main_content['buttons'],
            resize_keyboard=True
        )
        
        await message.answer(
            "🎊 *Поздравляем с покупкой!*\n\n"
            "✅ *Ваш заказ оформлен!*\n\n"
            "📦 Набор будет отправлен в ближайшее время.\n"
            "📞 Менеджер свяжется с вами для уточнения деталей доставки.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки часового пояса: {e}")
        await message.answer("❌ Ошибка сохранения данных")

@dp.message(OrderStates.waiting_address)
async def city_handler(message: types.Message, state: FSMContext):
    """Обработчик ввода города"""
    try:
        user = await get_user_by_tg_id(message.from_user.id)
        if user:
            await update_user_timezone(user.id, "auto", message.text)
            
            await manager_bot.notify_managers(
                f"📍 *Город определен!*\n"
                f"👤 {user.first_name}\n"
                f"🏙️ Город: {message.text}"
            )
        
        main_content = content_manager.get('welcome_default')
        keyboard = ReplyKeyboardMarkup(
            keyboard=main_content['buttons'],
            resize_keyboard=True
        )
        
        await message.answer(
            f"✅ *Город сохранен:* {message.text}\n\n"
            "🎊 *Поздравляем с покупкой!*\n\n"
            "✅ *Ваш заказ оформлен!*\n\n"
            "📦 Набор будет отправлен в ближайшее время.\n"
            "📞 Менеджер свяжется с вами для уточнения деталей доставки.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки города: {e}")
        await message.answer("❌ Ошибка сохранения города")

# ========== ОБРАБОТЧИКИ СБОРА АНАЛИЗОВ ==========

@dp.message(F.text == "📦 Статус заказа")
async def order_status_handler(message: types.Message):
    """Показывает статус заказа"""
    try:
        user = await get_user_by_tg_id(message.from_user.id)
        if not user:
            await message.answer("❌ Сначала напишите /start")
            return
        
        orders = await get_user_orders(user.id)
        if not orders:
            await message.answer("📦 У вас нет заказов")
            return
        
        last_order = orders[0]
        status_map = {
            'new': '🆕 Новый',
            'pending': '⏳ Ожидает оплаты', 
            'paid': '✅ Оплачен',
            'shipped': '🚚 Отправлен',
            'delivered': '📦 Доставлен'
        }
        
        status_text = status_map.get(last_order.payment_status, last_order.payment_status)
        
        response = (
            f"📦 *Ваш заказ #{last_order.id}*\n\n"
            f"*Статус:* {status_text}\n"
            f"*Сумма:* {last_order.amount} руб\n"
            f"*Дата:* {last_order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        )
        
        if last_order.payment_status == 'paid':
            response += "\n💡 *Следующие шаги:*\n• Ожидайте доставку набора\n• Менеджер свяжется с вами"
        
        await message.answer(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса заказа: {e}")
        await message.answer("❌ Ошибка получения информации о заказе")

@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: types.Message):
    """Показывает профиль пользователя"""
    try:
        user = await get_user_by_tg_id(message.from_user.id)
        if not user:
            await message.answer("❌ Профиль не найден. Напишите /start")
            return
        
        orders = await get_user_orders(user.id, limit=1)
        quiz_answers = await get_user_quiz_answers(user.id)
        
        profile_text = (
            f"👤 *Ваш профиль*\n\n"
            f"*Имя:* {user.first_name or 'Не указано'}\n"
            f"*Username:* @{user.username or 'Не указан'}\n"
            f"*Телефон:* {user.phone or 'Не указан'}\n"
            f"*Город:* {user.city or 'Не указан'}\n"
            f"*Статус:* {user.status}\n"
        )
        
        if orders:
            last_order = orders[0]
            profile_text += f"*Последний заказ:* #{last_order.id} ({last_order.payment_status})\n"
        
        if quiz_answers:
            profile_text += f"*Прошел тест:* ✅ ({len(quiz_answers)} ответов)\n"
        
        profile_text += f"*Зарегистрирован:* {user.created_at.strftime('%d.%m.%Y')}"
        
        await message.answer(profile_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения профиля: {e}")
        await message.answer("❌ Ошибка получения профиля")

@dp.message(F.text == "🔗 Моя реф ссылка")
async def referral_handler(message: types.Message):
    """Показывает реферальную ссылку"""
    try:
        bot_username = (await bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
        
        await message.answer(
            f"🔗 *Ваша реферальная ссылка:*\n\n"
            f"`{referral_link}`\n\n"
            f"Поделитесь этой ссылкой с друзьями!",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания реферальной ссылки: {e}")
        await message.answer("❌ Ошибка создания ссылки")

@dp.message(F.text == "ℹ️ О проекте")
async def about_handler(message: types.Message):
    """Информация о проекте"""
    about_text = (
        "🏥 *GenoLife - современная система анализа здоровья*\n\n"
        "*Что мы предлагаем:*\n"
        "• 🧪 Комплексный анализ организма\n"
        "• 📊 Подробный отчет с интерпретацией\n"
        "• 💡 Персональные рекомендации\n"
        "• 🌱 14-дневную программу восстановления\n\n"
        "*Как это работает:*\n"
        "1. Проходите простой тест\n"
        "2. Получаете набор для анализа\n"
        "3. Собираете образцы\n"
        "4. Получаете отчет и рекомендации\n\n"
        "Начните свой путь к здоровью уже сегодня! 🚀"
    )
    
    await message.answer(about_text, parse_mode="Markdown")

# ========== МЕНЕДЖЕРСКИЕ КОМАНДЫ ==========

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    """Статистика для админов/менеджеров"""
    try:
        from database import get_statistics
        
        stats = await get_statistics()
        stats_text = (
            "📊 *Статистика бота*\n\n"
            f"👥 *Пользователи:* {stats['total_users']}\n"
            f"💰 *Оплатившие:* {stats['paid_users']}\n"
            f"📦 *Заказы:* {stats['total_orders']}\n"
            f"✅ *Оплаченные заказы:* {stats['paid_orders']}\n"
            f"🧪 *Прошли квиз:* {stats['quiz_users']}\n"
            f"🌱 *В программе:* {stats['program_users']}\n"
            f"📈 *Конверсия:* {stats['conversion_rate']}%\n"
        )
        
        await message.answer(stats_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        await message.answer("❌ Ошибка получения статистики")

@dp.message(F.text.startswith("/"))
async def manager_commands_handler(message: types.Message):
    """Обработчик текстовых команд менеджеров"""
    try:
        result = await manager_bot.handle_text_command(message)
        await message.answer(result)
    except Exception as e:
        logger.error(f"❌ Ошибка обработки команды менеджера: {e}")
        await message.answer("❌ Ошибка выполнения команды")

# ========== CALLBACK ОБРАБОТЧИКИ ==========

@dp.callback_query(F.data.startswith(("send_kit:", "courier:", "in_lab:", "results_ready:", "consult:", "start_program:")))
async def manager_callbacks_handler(callback: types.CallbackQuery):
    """Обработчик callback от кнопок менеджеров"""
    try:
        result = await manager_bot.handle_manager_command(callback.data, callback.from_user.id)
        await callback.answer(result)
        
        # Обновляем карточку клиента
        user_id = int(callback.data.split(":")[1])
        await manager_bot.send_user_card(user_id)
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки callback менеджера: {e}")
        await callback.answer("❌ Ошибка выполнения")

@dp.callback_query(F.data == "get_report")
async def get_report_handler(callback: types.CallbackQuery):
    """Обработчик скачивания отчета"""
    try:
        # Здесь будет логика отправки отчета
        await callback.answer("📊 Отчет будет отправлен менеджером")
        
        # Предлагаем консультацию через 5 минут
        await asyncio.sleep(300)  # 5 минут
        
        user = await get_user_by_tg_id(callback.from_user.id)
        if user:
            await notification_manager.send_consultation_offer(user.id)
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки запроса отчета: {e}")
        await callback.answer("❌ Ошибка")

@dp.callback_query(F.data == "book_consult")
async def book_consult_handler(callback: types.CallbackQuery):
    """Обработчик записи на консультацию"""
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💳 Оплатить консультацию", callback_data="pay_consultation"),
            InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="contact_manager")
        ]])
        
        await callback.message.answer(
            "💬 *Запись на консультацию*\n\n"
            "Консультация врача-эксперта включает:\n"
            "• Подробный разбор вашего отчета\n"
            "• Объяснение причин и последствий\n"
            "• Персональные рекомендации\n"
            "• План действий на 14 дней\n\n"
            "Стоимость: 4 990 руб (со скидкой 30% - 3 493 руб)",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Ошибка записи на консультацию: {e}")
        await callback.answer("❌ Ошибка")

@dp.callback_query(F.data == "start_program")
async def start_program_handler(callback: types.CallbackQuery):
    """Обработчик запуска программы"""
    try:
        user = await get_user_by_tg_id(callback.from_user.id)
        if user:
            success = await program_manager.start_program(user.id)
            if success:
                await callback.answer("🌱 Программа запущена!")
            else:
                await callback.answer("❌ Ошибка запуска программы")
        else:
            await callback.answer("❌ Пользователь не найден")
            
    except Exception as e:
        logger.error(f"❌ Ошибка запуска программы: {e}")
        await callback.answer("❌ Ошибка запуска")

@dp.callback_query(F.data.startswith("program_done:"))
async def program_done_handler(callback: types.CallbackQuery):
    """Обработчик завершения дня программы"""
    try:
        day = int(callback.data.split(":")[1])
        user = await get_user_by_tg_id(callback.from_user.id)
        if user:
            await program_manager.mark_day_completed(user.id, day)
            await callback.answer(f"✅ День {day} завершен!")
        else:
            await callback.answer("❌ Ошибка")
            
    except Exception as e:
        logger.error(f"❌ Ошибка завершения дня программы: {e}")
        await callback.answer("❌ Ошибка")

# ========== ЗАПУСК БОТА ==========

@dp.message()
async def unknown_message_handler(message: types.Message):
    """Обработчик неизвестных сообщений"""
    welcome_content = content_manager.get('welcome_default')
    keyboard = ReplyKeyboardMarkup(
        keyboard=welcome_content['buttons'],
        resize_keyboard=True
    )
    
    await message.answer(
        "🤔 Используйте кнопки меню для навигации:",
        reply_markup=keyboard
    )

async def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск бота GenoLife...")
    
    try:
        # Создаем таблицы в БД
        await create_tables()
        logger.info("✅ База данных инициализирована")
        
        # Запускаем планировщик
        await scheduler_manager.start_scheduler()
        logger.info("✅ Планировщик запущен")
        
        # Уведомляем админа о запуске
        await bot.send_message(config.ADMIN_ID, "🤖 Бот GenoLife запущен и готов к работе!")
        
        # Запускаем бота
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        # Останавливаем планировщик
        scheduler_manager.stop_scheduler()
        await bot.session.close()
        logger.info("🛑 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())
