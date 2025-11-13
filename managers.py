import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import AsyncSessionLocal, User, Order, update_user_status
from sqlalchemy import select, text
from config import config

logger = logging.getLogger(__name__)

class ManagerBot:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def notify_managers(self, message: str, parse_mode="Markdown"):
        try:
            await self.bot.send_message(config.MANAGER_GROUP_ID, message, parse_mode=parse_mode)
            logger.info("✅ Уведомление отправлено менеджерам")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления: {e}")

    async def send_user_card(self, user_id: int, order_id: int = None):
        try:
            async with AsyncSessionLocal() as session:
                user = await session.get(User, user_id)
                if not user:
                    return

                orders_result = await session.execute(
                    select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
                )
                orders_list = orders_result.scalars().all()

                quiz_answers = await session.execute(
                    text("SELECT question_id, answer FROM quiz_answers WHERE user_id = :user_id"),
                    {"user_id": user_id}
                )
                quiz_data = quiz_answers.fetchall()

                card_text = self._format_user_card(user, orders_list, quiz_data)
                keyboard = self._create_manager_keyboard(user_id)

                await self.bot.send_message(
                    config.MANAGER_GROUP_ID,
                    card_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка отправки карточки: {e}")

    def _format_user_card(self, user: User, orders: List[Order], quiz_data: List) -> str:
        card_text = (
            f"👤 *Карточка клиента*\n\n"
            f"*ID:* {user.id}\n"
            f"*Имя:* {user.first_name or 'Не указано'}\n"
            f"*Username:* @{user.username or 'Не указан'}\n"
            f"*Телефон:* {user.phone or 'Не указан'}\n"
            f"*Город:* {user.city or 'Не указан'}\n"
            f"*Часовой пояс:* {user.timezone or 'Не указан'}\n"
            f"*Статус:* {user.status}\n"
            f"*Источник:* {user.source or 'Не указан'}\n"
        )

        if orders:
            card_text += f"\n*📦 Заказы ({len(orders)}):*\n"
            for order in orders[:3]:
                status_map = {'new': '🆕', 'pending': '⏳', 'paid': '✅', 'shipped': '🚚', 'delivered': '📦'}
                status = status_map.get(order.payment_status, order.payment_status)
                card_text += f"• #{order.id}: {status} - {order.amount} руб\n"

        if quiz_data:
            card_text += f"\n*🧪 Ответы квиза:*\n"
            for question_id, answer in quiz_data[:3]:
                card_text += f"• {question_id}: {answer}\n"

        return card_text

    def _create_manager_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton(text="📦 Отправить набор", callback_data=f"send_kit:{user_id}")],
            [InlineKeyboardButton(text="🚚 Назначить курьера", callback_data=f"courier:{user_id}")],
            [InlineKeyboardButton(text="🧪 В лаборатории", callback_data=f"in_lab:{user_id}")],
            [InlineKeyboardButton(text="📄 Результаты готовы", callback_data=f"results_ready:{user_id}")],
            [InlineKeyboardButton(text="💬 Консультация", callback_data=f"consult:{user_id}")],
            [InlineKeyboardButton(text="🌱 Программа", callback_data=f"start_program:{user_id}")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def handle_manager_command(self, callback_data: str, manager_tg_id: int):
        try:
            command, user_id = callback_data.split(":")
            user_id = int(user_id)

            if manager_tg_id != config.ADMIN_ID:
                return "⛔ Доступ запрещен"

            async with AsyncSessionLocal() as session:
                user = await session.get(User, user_id)
                if not user:
                    return "❌ Клиент не найден"

                if command == "send_kit":
                    return await self._handle_send_kit(user, session)
                elif command == "courier":
                    return await self._handle_courier(user, session)
                elif command == "in_lab":
                    return await self._handle_in_lab(user, session)
                elif command == "results_ready":
                    return await self._handle_results_ready(user, session)
                elif command == "consult":
                    return await self._handle_consult(user, session)
                elif command == "start_program":
                    return await self._handle_start_program(user, session)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки команды: {e}")
            return "❌ Ошибка"

    async def _handle_send_kit(self, user: User, session):
        user.status = 'kit_sent'
        await session.commit()
        await self.bot.send_message(user.tg_id, "📦 *Ваш набор отправлен!* Ожидайте доставку.", parse_mode="Markdown")
        return f"✅ Набор отправлен {user.first_name}"

    async def _handle_courier(self, user: User, session):
        user.status = 'courier_scheduled'
        await session.commit()
        await self.bot.send_message(user.tg_id, "🚚 *Курьер назначен!* С вами свяжутся.", parse_mode="Markdown")
        return f"✅ Курьер назначен {user.first_name}"

    async def _handle_in_lab(self, user: User, session):
        user.status = 'in_lab'
        await session.commit()
        await self.bot.send_message(user.tg_id, "🧪 *Образцы в лаборатории!* Результаты через 7-10 дней.", parse_mode="Markdown")
        return f"✅ В лаборатории {user.first_name}"

    async def _handle_results_ready(self, user: User, session):
        user.status = 'results_ready'
        await session.commit()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📊 Скачать отчет", callback_data="get_report"),
            InlineKeyboardButton(text="💬 Консультация", callback_data="book_consult")
        ]])
        await self.bot.send_message(user.tg_id, "🎉 *Результаты готовы!*", reply_markup=keyboard, parse_mode="Markdown")
        return f"✅ Результаты готовы {user.first_name}"

    async def _handle_consult(self, user: User, session):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💬 Консультация", callback_data="book_consult")
        ]])
        await self.bot.send_message(user.tg_id, "💬 *Консультация врача*", reply_markup=keyboard, parse_mode="Markdown")
        return f"✅ Консультация предложена {user.first_name}"

    async def _handle_start_program(self, user: User, session):
        user.status = 'program_started'
        await session.commit()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌱 Начать программу", callback_data="start_program")
        ]])
        await self.bot.send_message(user.tg_id, "🌱 *14-дневная программа*", reply_markup=keyboard, parse_mode="Markdown")
        return f"✅ Программа предложена {user.first_name}"

manager_bot = None

def init_manager_bot(bot: Bot):
    global manager_bot
    manager_bot = ManagerBot(bot)
    return manager_bot
