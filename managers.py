import logging
from typing import Dict, List
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from database import AsyncSessionLocal, User, Order, get_user_by_tg_id, update_user_status
from sqlalchemy import select, text
from config import config

logger = logging.getLogger(__name__)

class ManagerBot:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._check_config()

    def _check_config(self):
        """Проверяет конфигурацию менеджерского бота"""
        if not config.MANAGER_GROUP_ID:
            logger.warning("⚠️ MANAGER_GROUP_ID не настроен! Все уведомления будут отправляться админу.")
        else:
            logger.info(f"✅ MANAGER_GROUP_ID настроен: {config.MANAGER_GROUP_ID}")

    async def notify_managers(self, message: str, parse_mode="Markdown"):
        """Отправляет уведомление менеджерам"""
        try:
            logger.info(f"📢 Отправка уведомления менеджерам: {message[:100]}...")
            
            if config.MANAGER_GROUP_ID:
                # Отправляем в группу менеджеров
                await self.bot.send_message(
                    chat_id=config.MANAGER_GROUP_ID, 
                    text=message, 
                    parse_mode=parse_mode
                )
                logger.info(f"✅ Уведомление отправлено в группу менеджеров {config.MANAGER_GROUP_ID}")
            else:
                # Отправляем админу с пометкой
                await self.bot.send_message(
                    chat_id=config.ADMIN_ID, 
                    text=f"👨‍💼 [Менеджер] {message}", 
                    parse_mode=parse_mode
                )
                logger.info(f"✅ Уведомление отправлено админу {config.ADMIN_ID} (группа не настроена)")
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления менеджерам: {e}")

    async def send_user_card(self, user_id: int, order_id: int = None):
        """Отправляет карточку клиента менеджерам"""
        try:
            logger.info(f"📋 Формирование карточки клиента {user_id}")
            
            async with AsyncSessionLocal() as session:
                # Получаем данные пользователя
                user = await session.get(User, user_id)
                if not user:
                    logger.error(f"❌ Пользователь {user_id} не найден")
                    return

                # Получаем заказы пользователя
                orders_result = await session.execute(
                    select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
                )
                orders_list = orders_result.scalars().all()

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

                # Отправляем карточку
                if config.MANAGER_GROUP_ID:
                    await self.bot.send_message(
                        chat_id=config.MANAGER_GROUP_ID,
                        text=card_text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                    logger.info(f"✅ Карточка клиента {user_id} отправлена в группу менеджеров")
                else:
                    await self.bot.send_message(
                        chat_id=config.ADMIN_ID,
                        text=f"👨‍💼 [Карточка клиента]\n\n{card_text}",
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                    logger.info(f"✅ Карточка клиента {user_id} отправлена админу (группа не настроена)")

        except Exception as e:
            logger.error(f"❌ Ошибка отправки карточки клиента: {e}")

    def _format_user_card(self, user: User, orders: List[Order], quiz_data: List) -> str:
        """Форматирует карточку клиента"""
        # Добавляем пометку для группы менеджеров
        if config.MANAGER_GROUP_ID:
            card_text = "👤 *Карточка клиента*\n\n"
        else:
            card_text = "👤 *Карточка клиента* (отправлено админу, т.к. группа не настроена)\n\n"
            
        card_text += (
            f"*ID:* {user.id}\n"
            f"*Telegram ID:* {user.tg_id}\n"
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
            for order in orders[:3]:
                status_map = {
                    'new': '🆕 Новый',
                    'pending': '⏳ Ожидает оплаты',
                    'paid': '✅ Оплачен',
                    'shipped': '🚚 Отправлен',
                    'delivered': '📦 Доставлен'
                }
                status = status_map.get(order.payment_status, order.payment_status)
                card_text += f"• *#{order.id}:* {status} - {order.amount} руб\n"
        else:
            card_text += f"\n*📦 Заказы:* Нет заказов\n"

        # Добавляем ответы квиза
        if quiz_data:
            card_text += f"\n*🧪 Ответы квиза ({len(quiz_data)}):*\n"
            for question_id, answer in quiz_data[:5]:
                question_name = question_id.replace('_', ' ').title()
                card_text += f"• *{question_name}:* {answer}\n"
        else:
            card_text += f"\n*🧪 Ответы квиза:* Нет данных\n"

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
            logger.info(f"🛠 Обработка команды менеджера: {callback_data} от {manager_tg_id}")
            
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
        try:
            user.status = 'kit_sent'
            await session.commit()
            
            # Уведомляем клиента
            await self.bot.send_message(
                user.tg_id,
                "📦 *Ваш набор для анализов отправлен!*\n\n"
                "Скоро вы получите трек-номер для отслеживания.\n\n"
                "Ожидайте доставку в ближайшие дни!",
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Набор отправлен клиенту {user.first_name} (ID: {user.id})")
            return f"✅ Набор отправлен клиенту {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки набора: {e}")
            return f"❌ Ошибка отправки набора"

    async def _handle_courier(self, user: User, session):
        """Обработчик назначения курьера"""
        try:
            user.status = 'courier_scheduled'
            await session.commit()
            
            await self.bot.send_message(
                user.tg_id,
                "🚚 *Курьер назначен!*\n\n"
                "Скоро с вами свяжутся для уточнения времени визита курьера "
                "для забора образцов анализов.\n\n"
                "Пожалуйста, будьте на связи!",
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Курьер назначен для {user.first_name} (ID: {user.id})")
            return f"✅ Курьер назначен для {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка назначения курьера: {e}")
            return f"❌ Ошибка назначения курьера"

    async def _handle_in_lab(self, user: User, session):
        """Обработчик статуса 'В лаборатории'"""
        try:
            user.status = 'in_lab'
            await session.commit()
            
            await self.bot.send_message(
                user.tg_id,
                "🧪 *Ваши образцы в лаборатории!*\n\n"
                "Анализы находятся в обработке. Результаты будут готовы через 7-10 дней.\n\n"
                "Мы сообщим вам, когда отчет будет готов!",
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Статус обновлен: в лаборатории ({user.first_name}, ID: {user.id})")
            return f"✅ Статус обновлен: в лаборатории ({user.first_name})"
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса лаборатории: {e}")
            return f"❌ Ошибка обновления статуса"

    async def _handle_results_ready(self, user: User, session):
        """Обработчик готовности результатов"""
        try:
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
                "Вы можете скачать отчет или записаться на консультацию с врачом-экспертом "
                "для подробного разбора ваших анализов.\n\n"
                "*Консультация поможет:*\n"
                "• Понять причины вашего состояния\n"
                "• Получить персональные рекомендации\n"
                "• Начать эффективное восстановление",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Результаты готовы для {user.first_name} (ID: {user.id})")
            return f"✅ Результаты готовы для {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления о результатах: {e}")
            return f"❌ Ошибка уведомления"

    async def _handle_consult(self, user: User, session):
        """Обработчик предложения консультации"""
        try:
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
                "• План восстановления энергии\n"
                "• Ответы на все ваши вопросы\n\n"
                "🎁 *Специальное предложение:* 30% скидка на первую консультацию!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Консультация предложена {user.first_name} (ID: {user.id})")
            return f"✅ Предложение консультации отправлено {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка предложения консультации: {e}")
            return f"❌ Ошибка отправки предложения"

    async def _handle_start_program(self, user: User, session):
        """Обработчик запуска 14-дневной программы"""
        try:
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
                "помогающие вернуть естественный ритм энергии, сна и спокойствия.\n\n"
                "*Что вас ждет:*\n"
                "• Ежедневные практики для баланса\n"
                "• Персональные рекомендации\n"
                "• Поддержка на каждом этапе\n"
                "• Измеримые результаты\n\n"
                "Начните свой путь к лучшему самочувствию уже сегодня!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Программа предложена {user.first_name} (ID: {user.id})")
            return f"✅ Программа предложена {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска программы: {e}")
            return f"❌ Ошибка предложения программы"

    async def _handle_fail_collect(self, user: User, session):
        """Обработчик повторного сбора"""
        try:
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
                "Если нужна помощь или есть вопросы - свяжитесь с менеджером.\n\n"
                "*Советы для успешного сбора:*\n"
                "• Следуйте инструкции\n"
                "• Выберите удобное время\n"
                "• Подготовьте все необходимое заранее",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Повторный сбор предложен {user.first_name} (ID: {user.id})")
            return f"✅ Предложение повторного сбора отправлено {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка предложения повторного сбора: {e}")
            return f"❌ Ошибка предложения повторного сбора"

    async def is_manager(self, tg_id: int) -> bool:
        """Проверяет, является ли пользователь менеджером"""
        # В MVP считаем админа менеджером
        is_manager = tg_id == config.ADMIN_ID
        logger.info(f"🔐 Проверка прав менеджера: {tg_id} -> {is_manager}")
        return is_manager

# Создаем глобальный экземпляр
manager_bot = None

def init_manager_bot(bot: Bot):
    """Инициализирует менеджерский бот"""
    global manager_bot
    manager_bot = ManagerBot(bot)
    logger.info("✅ Менеджерский бот инициализирован")
    return manager_bot
