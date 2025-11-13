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
    update_user_contact, update_user_timezone, get_user_orders
)
from managers import init_manager_bot, manager_bot
from notifications import NotificationManager
from programs import ProgramManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

manager_bot = init_manager_bot(bot)
notification_manager = NotificationManager(bot)
program_manager = ProgramManager(bot)

class OrderStates(StatesGroup):
    waiting_contacts = State()
    waiting_timezone = State()

class QuizStates(StatesGroup):
    question1 = State()
    question2 = State() 
    question3 = State()

# ========== МЕНЕДЖЕРСКИЕ КОМАНДЫ ==========

@dp.callback_query(F.data.startswith(("send_kit:", "courier:", "in_lab:", "results_ready:", "consult:", "start_program:")))
async def handle_manager_commands(callback: types.CallbackQuery):
    try:
        result = await manager_bot.handle_manager_command(callback.data, callback.from_user.id)
        await callback.answer(result)
        user_id = int(callback.data.split(":")[1])
        await manager_bot.send_user_card(user_id)
    except Exception as e:
        logger.error(f"❌ Ошибка обработки команды менеджера: {e}")
        await callback.answer("❌ Ошибка")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========

@dp.message(CommandStart())
async def start_command(message: types.Message):
    logger.info(f"📥 /start от {message.from_user.id}")
    
    source = 'direct'
    scenario = 'default'
    
    if len(message.text.split()) > 1:
        source_param = message.text.split()[1]
        source = source_param
        if source_param.startswith('src_'):
            scenario = source_param[4:]
        elif source_param.startswith('ref_'):
            scenario = 'referral'
        elif source_param.startswith('blogger'):
            scenario = source_param
    
    user = await get_or_create_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        source=source
    )
    
    if not user:
        await message.answer("❌ Ошибка регистрации")
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать 60-секундный тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("🎉 Добро пожаловать в GenoLife!", reply_markup=keyboard)

@dp.message(F.text == "🧪 Начать 60-секундный тест")
async def start_quiz_handler(message: types.Message, state: FSMContext):
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала /start")
        return
    
    await message.answer(
        "🧪 *60-секундный тест*\n\n❓ *Вопрос 1/3:* Как часто вы чувствуете усталость?",
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
    user = await get_user_by_tg_id(message.from_user.id)
    if user:
        await save_quiz_answer(user.id, "energy_level", message.text)
    
    await message.answer(
        "✅ *Ответ сохранен*\n\n❓ *Вопрос 2/3:* Как вы оцениваете качество сна?",
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
    user = await get_user_by_tg_id(message.from_user.id)
    if user:
        await save_quiz_answer(user.id, "sleep_quality", message.text)
    
    await message.answer(
        "✅ *Ответ сохранен*\n\n❓ *Вопрос 3/3:* Как часто занимаетесь спортом?",
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
    user = await get_user_by_tg_id(message.from_user.id)
    if user:
        await save_quiz_answer(user.id, "activity_level", message.text)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 Заказать анализ со скидкой")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="ℹ️ О проекте")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "🎉 *Тест завершен!*\n\n*Специальное предложение:* Полный анализ со скидкой 20% - 2 990 руб!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await state.clear()

@dp.message(F.text == "💳 Заказать анализ со скидкой")
async def offer_payment_after_quiz_handler(message: types.Message):
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала /start")
        return
    
    order = await create_order(user.id, 2990.00)
    if not order:
        await message.answer("❌ Ошибка создания заказа")
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Тестовая оплата", callback_data=f"test_pay:{order.id}")],
            [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"confirm_pay:{order.id}")]
        ]
    )
    
    await message.answer(
        "💰 *Специальное предложение после теста!*\n\n🎁 *Полный анализ со скидкой 20%*\n\n*💵 Стоимость:* ~~3 737 руб~~ *2 990 руб*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("test_pay:"))
async def test_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        order_id = int(callback.data.split(":")[1])
        success = await update_order_payment(order_id, 'paid', f"TEST_{uuid.uuid4().hex[:8]}")
        if not success:
            await callback.answer("❌ Заказ не найден")
            return
        
        user = await get_user_by_tg_id(callback.from_user.id)
        if user:
            await update_user_status(user.id, 'paid')
        
        await callback.message.answer(
            "🎉 *Оплата подтверждена!*\n\nТеперь нам нужны ваши контактные данные.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📞 Оставить контакты", request_contact=True)]],
                resize_keyboard=True
            )
        )
        
        await state.set_state(OrderStates.waiting_contacts)
        await callback.answer("✅ Тестовая оплата подтверждена!")
        
        if user:
            await manager_bot.notify_managers(
                f"💰 *НОВАЯ ОПЛАТА!*\n👤 *Клиент:* {user.first_name}\n💵 *Сумма:* 2 990 руб"
            )
            await manager_bot.send_user_card(user.id, order_id)
            
    except Exception as e:
        logger.error(f"❌ Ошибка оплаты: {e}")
        await callback.answer("❌ Ошибка")

@dp.message(OrderStates.waiting_contacts, F.contact)
async def contact_received_handler(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    user = await get_user_by_tg_id(message.from_user.id)
    if user:
        await update_user_contact(user.id, phone)
    
    timezone_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Москва (+3)"), KeyboardButton(text="Екатеринбург (+5)")],
            [KeyboardButton(text="Определить по городу")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ *Телефон сохранен:* {phone}\n\n🕐 *Выберите часовой пояс:*",
        parse_mode="Markdown",
        reply_markup=timezone_keyboard
    )
    
    await state.set_state(OrderStates.waiting_timezone)

@dp.message(OrderStates.waiting_timezone)
async def timezone_handler(message: types.Message, state: FSMContext):
    timezone_map = {
        "Москва (+3)": "Europe/Moscow",
        "Екатеринбург (+5)": "Asia/Yekaterinburg", 
        "Определить по городу": "auto"
    }
    
    if message.text in timezone_map:
        timezone = timezone_map[message.text]
        user = await get_user_by_tg_id(message.from_user.id)
        if user:
            city = None
            if message.text == "Определить по городу":
                city = "auto"
            else:
                city = message.text.split(' ')[0]
            
            await update_user_timezone(user.id, timezone, city)
        
        main_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📦 Статус заказа"), KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="🔗 Моя реф ссылка"), KeyboardButton(text="ℹ️ О проекте")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            "🎊 *Поздравляем с покупкой!*\n\n✅ *Ваш заказ оформлен!*",
            parse_mode="Markdown",
            reply_markup=main_keyboard
        )
        
        await state.clear()
        
        if user:
            await manager_bot.notify_managers(
                f"🆕 *НОВЫЙ ЗАКАЗ!*\n👤 {user.first_name}\n📞 {user.phone}\n📍 {city or 'Не указан'}\n🕐 {timezone}"
            )

# ========== ДОПОЛНИТЕЛЬНЫЕ ОБРАБОТЧИКИ ==========

@dp.message(F.text == "🔗 Моя реф ссылка")
async def my_referral_handler(message: types.Message):
    bot_username = (await bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
    await message.answer(f"🔗 *Ваша реферальная ссылка:*\n\n`{referral_link}`", parse_mode="Markdown")

@dp.message(F.text == "💰 Оплатить анализ")
async def direct_payment_handler(message: types.Message):
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала /start")
        return
    
    order = await create_order(user.id, 2990.00)
    if not order:
        await message.answer("❌ Ошибка создания заказа")
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Тестовая оплата", callback_data=f"test_pay:{order.id}")],
            [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"confirm_pay:{order.id}")]
        ]
    )
    
    await message.answer("💰 *Оплата анализа* - 2 990 руб", parse_mode="Markdown", reply_markup=keyboard)

@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: types.Message):
    user = await get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("❌ Профиль не найден")
        return
    
    orders = await get_user_orders(user.id)
    profile_text = f"👤 *Профиль:*\nИмя: {user.first_name}\nТелефон: {user.phone or 'Не указан'}\nСтатус: {user.status}"
    
    if orders:
        last_order = orders[0]
        status_map = {'new': '🆕', 'pending': '⏳', 'paid': '✅'}
        profile_text += f"\nЗаказ: #{last_order.id} ({status_map.get(last_order.payment_status, last_order.payment_status)})"
    
    await message.answer(profile_text, parse_mode="Markdown")

@dp.message(F.text == "ℹ️ О проекте")
async def about_handler(message: types.Message):
    await message.answer("🏥 *GenoLife* - система анализа здоровья")

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    await message.answer("📊 Статистика бота")

@dp.message()
async def unknown_message_handler(message: types.Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧪 Начать 60-секундный тест")],
            [KeyboardButton(text="💰 Оплатить анализ"), KeyboardButton(text="👤 Профиль")],
        ],
        resize_keyboard=True
    )
    await message.answer("🤔 Используйте кнопки меню", reply_markup=keyboard)

async def main():
    logger.info("🚀 Запуск бота GenoLife...")
    await create_tables()
    await bot.send_message(config.ADMIN_ID, "🤖 Бот GenoLife запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
