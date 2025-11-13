import logging
from typing import Dict, List
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import AsyncSessionLocal, User, Order, get_user_by_tg_id
from sqlalchemy import select, text
from config import config

logger = logging.getLogger(__name__)

class ManagerBot:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.managers_cache = {}

    async def notify_managers(self, message: str, parse_mode="Markdown"):
        """Отправляет уведомление менеджерам"""
        try:
            if config.MANAGER_GROUP_ID:
                await self.bot.send_message(config.MANAGER_GROUP_ID, message, parse_mode=parse_mode)
            else:
                # Если группа не настроена, отправляем админу
                await self.bot.send_message(config.ADMIN_ID, f"📢 {message}", parse_mode=parse_mode)
            logger.info("📢 Уведомление отправлено менеджерам")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления менеджерам: {e}")

    async def send_user_card(self, user_id: int, order_id: int = None):
        """Отправляет карточку клиента менеджерам"""
        try:
            async with AsyncSessionLocal() as session:
                # Получаем данные пользователя
                user = await session.get(User, user_id)
                if not user:
                    return

                # Получаем заказы пользователя
                orders = await session.execute(
                    select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
                )
                orders_list = orders.scalars().all()

                # Получаем ответы квиза
                quiz_answers = await session.execute(
                    text("SELECT question_id, answer FROM quiz_answers WHERE user_id = :user_id"),
                    {"user_id": user_id}
                )
                quiz_data = quiz_answers.fetchall()

                # Формируем карточку клиента
                card_text = self._format_user_card(user, orders_list, quiz_data)
                
                # Создаем клавиатуру с командами менеджера
                keyboard = self._create_manager_keyboard(user_id, order_id)

                if config.MANAGER_GROUP_ID:
                    await self.bot.send_message(
                        config.MANAGER_GROUP_ID,
                        card_text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    await self.bot.send_message(
                        config.ADMIN_ID,
                        card_text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )

        except Exception as e:
            logger.error(f"❌ Ошибка отправки карточки клиента: {e}")

    def _format_user_card(self, user: User, orders: List[Order], quiz_data: List) -> str:
        """Форматирует карточку клиента"""
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
            f"*Сценарий:* {getattr(user, 'scenario', 'default')}\n"
            f"*Зарегистрирован:* {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        )

        # Добавляем информацию о заказах
        if orders:
            card_text += f"\n*📦 Заказы ({len(orders)}):*\n"
            for order in orders[:3]:  # Показываем последние 3 заказа
                status_map = {
                    'new': '🆕 Новый',
                    'pending': '⏳ Ожидает оплаты',
                    'paid': '✅ Оплачен',
                    'shipped': '🚚 Отправлен',
                    'delivered': '📦 Доставлен'
                }
                status = status_map.get(order.payment_status, order.payment_status)
                card_text += f"• #{order.id}: {status} - {order.amount} руб\n"

        # Добавляем ответы квиза
        if quiz_data:
            card_text += f"\n*🧪 Ответы квиза ({len(quiz_data)}):*\n"
            for question_id, answer in quiz_data[:5]:  # Показываем первые 5 ответов
                card_text += f"• {question_id}: {answer}\n"

        return card_text

    def _create_manager_keyboard(self, user_id: int, order_id: int = None) -> InlineKeyboardMarkup:
        """Создает клавиатуру с командами менеджера"""
        keyboard = []

        # Основные команды
        basic_commands = [
            ("📦 Отправить набор", f"send_kit:{user_id}"),
            ("🚚 Назначить курьера", f"courier:{user_id}"),
            ("🧪 В лаборатории", f"in_lab:{user_id}"),
            ("📄 Результаты готовы", f"results_ready:{user_id}"),
        ]

        for text, callback in basic_commands:
            keyboard.append([InlineKeyboardButton(text=text, callback_data=callback)])

        # Дополнительные команды
        extra_commands = [
            ("💬 Консультация", f"consult:{user_id}"),
            ("🌱 Запустить программу", f"start_program:{user_id}"),
            ("🔁 Повторить сбор", f"fail_collect:{user_id}"),
        ]

        for text, callback in extra_commands:
            keyboard.append([InlineKeyboardButton(text=text, callback_data=callback)])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def handle_manager_command(self, callback_data: str, manager_tg_id: int):
        """Обрабатывает команды менеджера"""
        try:
            command, user_id = callback_data.split(":")
            user_id = int(user_id)

            # Проверяем права менеджера
            if not await self.is_manager(manager_tg_id):
                return "⛔ Доступ запрещен"

            async with AsyncSessionLocal() as session:
                user = await session.get(User, user_id)
                if not user:
                    return "❌ Клиент не найден"

                # Обрабатываем команды
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
                elif command == "fail_collect":
                    return await self._handle_fail_collect(user, session)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки команды менеджера: {e}")
            return "❌ Ошибка выполнения команды"

    async def _handle_send_kit(self, user: User, session):
        """Обработчик отправки набора"""
        # Здесь будет логика отправки набора
        user.status = 'kit_sent'
        await session.commit()
        
        # Уведомляем клиента
        await self.bot.send_message(
            user.tg_id,
            "📦 *Ваш набор для анализов отправлен!*\n\n"
            "Скоро вы получите трек-номер для отслеживания.",
            parse_mode="Markdown"
        )
        
        return f"✅ Набор отправлен клиенту {user.first_name}"

    async def _handle_courier(self, user: User, session):
        """Обработчик назначения курьера"""
        user.status = 'courier_scheduled'
        await session.commit()
        
        await self.bot.send_message(
            user.tg_id,
            "🚚 *Курьер назначен!*\n\n"
            "Скоро с вами свяжутся для уточнения времени визита.",
            parse_mode="Markdown"
        )
        
        return f"✅ Курьер назначен для {user.first_name}"

    async def _handle_in_lab(self, user: User, session):
        """Обработчик статуса 'В лаборатории'"""
        user.status = 'in_lab'
        await session.commit()
        
        await self.bot.send_message(
            user.tg_id,
            "🧪 *Ваши образцы в лаборатории!*\n\n"
            "Анализы находятся в обработке. Результаты будут готовы через 7-10 дней.",
            parse_mode="Markdown"
        )
        
        return f"✅ Статус обновлен: в лаборатории ({user.first_name})"

    async def _handle_results_ready(self, user: User, session):
        """Обработчик готовности результатов"""
        user.status = 'results_ready'
        await session.commit()
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="📊 Скачать отчет", callback_data="get_report"),
                InlineKeyboardButton(text="💬 Консультация", callback_data="book_consult")
            ]]
        )
        
        await self.bot.send_message(
            user.tg_id,
            "🎉 *Ваши результаты готовы!*\n\n"
            "Вы можете скачать отчет или записаться на консультацию с врачом.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        return f"✅ Результаты готовы для {user.first_name}"

    async def _handle_consult(self, user: User, session):
        """Обработчик предложения консультации"""
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="💬 Записаться на консультацию", callback_data="book_consult")
            ]]
        )
        
        await self.bot.send_message(
            user.tg_id,
            "💬 *Хотите глубже понять ваши результаты?*\n\n"
            "Наш врач-эксперт проведет онлайн-разбор вашего отчета и объяснит, "
            "что именно влияет на сон, настроение и восстановление.\n\n"
            "*После консультации вы получите:*\n"
            "• Персональные рекомендации\n"
            "• Понимание вашего гормонального ритма\n"
            "• План восстановления энергии",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        return f"✅ Предложение консультации отправлено {user.first_name}"

    async def _handle_start_program(self, user: User, session):
        """Обработчик запуска 14-дневной программы"""
        user.status = 'program_started'
        await session.commit()
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🌱 Начать программу", callback_data="start_program")
            ]]
        )
        
        await self.bot.send_message(
            user.tg_id,
            "🌱 *Готовы начать 14-дневную программу восстановления?*\n\n"
            "Каждый день бот будет давать короткие задания и напоминания, "
            "помогающие вернуть естественный ритм энергии, сна и спокойствия.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        return f"✅ Программа предложена {user.first_name}"

    async def _handle_fail_collect(self, user: User, session):
        """Обработчик повторного сбора"""
        user.status = 'collect_retry'
        await session.commit()
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🔄 Повторить сбор завтра", callback_data="retry_collect"),
                InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="contact_manager")
            ]]
        )
        
        await self.bot.send_message(
            user.tg_id,
            "🔄 *Давайте попробуем собрать анализы еще раз!*\n\n"
            "Вы можете запланировать сбор на другой день. "
            "Если нужна помощь - свяжитесь с менеджером.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        return f"✅ Предложение повторного сбора отправлено {user.first_name}"

    async def is_manager(self, tg_id: int) -> bool:
        """Проверяет, является ли пользователь менеджером"""
        # В MVP считаем админа менеджером
        return tg_id == config.ADMIN_ID

# Создаем глобальный экземпляр
manager_bot = None

def init_manager_bot(bot: Bot):
    """Инициализирует менеджерский бот"""
    global manager_bot
    manager_bot = ManagerBot(bot)
    return manager_bot
