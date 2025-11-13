import logging
from typing import List, Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ReplyKeyboardMarkup, KeyboardButton
from database import AsyncSessionLocal, User, Order, Manager, ReferralLink, get_user_by_tg_id, update_user_status
from sqlalchemy import select, text, and_
from config import config
import pandas as pd
from datetime import datetime
import io

logger = logging.getLogger(__name__)

class ManagerBot:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def notify_managers(self, message: str, parse_mode="Markdown", reply_markup=None):
        """Отправляет уведомление в группу менеджеров"""
        try:
            await self.bot.send_message(
                config.MANAGER_GROUP_ID, 
                message, 
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            logger.info("✅ Уведомление отправлено менеджерам")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления менеджерам: {e}")
            return False

    async def send_user_card(self, user_id: int, order_id: int = None):
        """Отправляет карточку клиента в группу менеджеров"""
        try:
            async with AsyncSessionLocal() as session:
                # Получаем пользователя
                user = await session.get(User, user_id)
                if not user:
                    logger.error(f"❌ Пользователь {user_id} не найден")
                    return False

                # Получаем заказы пользователя
                orders_result = await session.execute(
                    select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
                )
                orders_list = orders_result.scalars().all()

                # Получаем ответы на квиз
                quiz_answers = await session.execute(
                    text("""
                        SELECT question_id, answer, created_at 
                        FROM quiz_answers 
                        WHERE user_id = :user_id 
                        ORDER BY created_at
                    """),
                    {"user_id": user_id}
                )
                quiz_data = quiz_answers.fetchall()

                # Форматируем карточку
                card_text = self._format_user_card(user, orders_list, quiz_data)
                keyboard = self._create_manager_keyboard(user_id, order_id)

                await self.bot.send_message(
                    config.MANAGER_GROUP_ID,
                    card_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )

                logger.info(f"✅ Карточка пользователя {user_id} отправлена менеджерам")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка отправки карточки пользователя: {e}")
            return False

    def _format_user_card(self, user: User, orders: List[Order], quiz_data: List) -> str:
        """Форматирует карточку пользователя"""
        # Статусы для отображения
        status_emojis = {
            'lead': '🆕',
            'active': '🟢', 
            'paid': '💰',
            'kit_sent': '📦',
            'delivered': '🚚',
            'collecting': '🧪',
            'in_lab': '🔬',
            'results_ready': '📊',
            'program_started': '🌱',
            'finished': '✅'
        }

        card_text = (
            f"👤 *Карточка клиента*\n\n"
            f"*ID:* {user.id}\n"
            f"*Telegram ID:* {user.tg_id}\n"
            f"*Имя:* {user.first_name or 'Не указано'}\n"
            f"*Username:* @{user.username or 'Не указан'}\n"
            f"*Телефон:* {user.phone or 'Не указан'}\n"
            f"*Город:* {user.city or 'Не указан'}\n"
            f"*Адрес:* {user.address or 'Не указан'}\n"
            f"*Часовой пояс:* {user.timezone or 'Не указан'}\n"
            f"*Статус:* {status_emojis.get(user.status, '⚪')} {user.status}\n"
            f"*Источник:* {user.source or 'Не указан'}\n"
            f"*Сценарий:* {user.scenario or 'default'}\n"
            f"*Зарегистрирован:* {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        )

        # Информация о заказах
        if orders:
            card_text += f"\n*📦 Заказы ({len(orders)}):*\n"
            for order in orders[:3]:  # Показываем последние 3 заказа
                status_map = {
                    'new': '🆕', 
                    'pending': '⏳', 
                    'paid': '✅', 
                    'shipped': '🚚', 
                    'delivered': '📦',
                    'refunded': '↩️',
                    'failed': '❌'
                }
                status = status_map.get(order.payment_status, order.payment_status)
                card_text += f"• *#{order.id}:* {status} - {order.amount} руб\n"
                if order.payment_date:
                    card_text += f"  📅 {order.payment_date.strftime('%d.%m.%Y %H:%M')}\n"
        else:
            card_text += "\n*📦 Заказы:* Нет\n"

        # Ответы на квиз
        if quiz_data:
            card_text += f"\n*🧪 Ответы квиза ({len(quiz_data)}):*\n"
            for question_id, answer, created_at in quiz_data[:5]:  # Показываем первые 5 ответов
                card_text += f"• *{question_id}:* {answer}\n"
        else:
            card_text += "\n*🧪 Ответы квиза:* Нет\n"

        return card_text

    def _create_manager_keyboard(self, user_id: int, order_id: int = None) -> InlineKeyboardMarkup:
        """Создает клавиатуру для управления клиентом"""
        keyboard = [
            [InlineKeyboardButton(text="📦 Отправить набор", callback_data=f"send_kit:{user_id}")],
            [InlineKeyboardButton(text="🚚 Назначить курьера", callback_data=f"courier:{user_id}")],
            [InlineKeyboardButton(text="🧪 В лаборатории", callback_data=f"in_lab:{user_id}")],
            [InlineKeyboardButton(text="📄 Результаты готовы", callback_data=f"results_ready:{user_id}")],
            [InlineKeyboardButton(text="💬 Консультация", callback_data=f"consult:{user_id}")],
            [InlineKeyboardButton(text="🌱 Запустить программу", callback_data=f"start_program:{user_id}")],
        ]
        
        if order_id:
            keyboard.append([InlineKeyboardButton(text="💰 Инфо о заказе", callback_data=f"order_info:{order_id}")])
            
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def handle_manager_command(self, callback_data: str, manager_tg_id: int) -> str:
        """Обрабатывает команды менеджера"""
        try:
            command_parts = callback_data.split(":")
            command = command_parts[0]
            user_id = int(command_parts[1])
            
            # Проверяем права менеджера
            if not await self._is_manager(manager_tg_id):
                return "⛔ Доступ запрещен. Вы не менеджер."

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
                elif command == "order_info":
                    order_id = int(command_parts[1])
                    return await self._handle_order_info(order_id, session)
                else:
                    return "❌ Неизвестная команда"

        except Exception as e:
            logger.error(f"❌ Ошибка обработки команды менеджера: {e}")
            return "❌ Ошибка выполнения команды"

    async def _is_manager(self, tg_id: int) -> bool:
        """Проверяет, является ли пользователь менеджером"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Manager).where(and_(Manager.tg_id == tg_id, Manager.is_active == True))
                )
                manager = result.scalar_one_or_none()
                return manager is not None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки менеджера: {e}")
            return False

    async def _handle_send_kit(self, user: User, session) -> str:
        """Обрабатывает отправку набора"""
        try:
            user.status = 'kit_sent'
            await session.commit()
            
            # Уведомляем клиента
            await self.bot.send_message(
                user.tg_id,
                "📦 *Ваш набор отправлен!*\n\nОжидайте доставку. Мы сообщим вам трек-номер для отслеживания.",
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Набор отправлен пользователю {user.first_name} (ID: {user.id})")
            return f"✅ Набор отправлен {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки набора: {e}")
            return "❌ Ошибка отправки набора"

    async def _handle_courier(self, user: User, session) -> str:
        """Обрабатывает назначение курьера"""
        try:
            user.status = 'courier_scheduled'
            await session.commit()
            
            await self.bot.send_message(
                user.tg_id,
                "🚚 *Курьер назначен!*\n\nС вами свяжутся для согласования времени доставки.",
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Курьер назначен пользователю {user.first_name}")
            return f"✅ Курьер назначен {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка назначения курьера: {e}")
            return "❌ Ошибка назначения курьера"

    async def _handle_in_lab(self, user: User, session) -> str:
        """Обрабатывает статус 'в лаборатории'"""
        try:
            user.status = 'in_lab'
            await session.commit()
            
            await self.bot.send_message(
                user.tg_id,
                "🧪 *Образцы в лаборатории!*\n\nРезультаты будут готовы через 7-10 дней.",
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Статус 'в лаборатории' установлен для {user.first_name}")
            return f"✅ В лаборатории {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка установки статуса лаборатории: {e}")
            return "❌ Ошибка установки статуса"

    async def _handle_results_ready(self, user: User, session) -> str:
        """Обрабатывает готовность результатов"""
        try:
            user.status = 'results_ready'
            await session.commit()
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📊 Скачать отчет", callback_data="get_report"),
                InlineKeyboardButton(text="💬 Консультация", callback_data="book_consult")
            ]])
            
            await self.bot.send_message(
                user.tg_id,
                "🎉 *Результаты готовы!*\n\nВаш отчет доступен для скачивания.",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Результаты готовы для {user.first_name}")
            return f"✅ Результаты готовы {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления о результатах: {e}")
            return "❌ Ошибка уведомления"

    async def _handle_consult(self, user: User, session) -> str:
        """Обрабатывает предложение консультации"""
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="💬 Консультация", callback_data="book_consult")
            ]])
            
            await self.bot.send_message(
                user.tg_id,
                "💬 *Консультация врача*\n\nХотите получить персональную консультацию по вашим результатам?",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Консультация предложена {user.first_name}")
            return f"✅ Консультация предложена {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка предложения консультации: {e}")
            return "❌ Ошибка предложения консультации"

    async def _handle_start_program(self, user: User, session) -> str:
        """Обрабатывает запуск программы"""
        try:
            user.status = 'program_started'
            await session.commit()
            
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🌱 Начать программу", callback_data="start_program")
            ]])
            
            await self.bot.send_message(
                user.tg_id,
                "🌱 *14-дневная программа восстановления*\n\nГотовы начать путь к лучшему самочувствию?",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Программа предложена {user.first_name}")
            return f"✅ Программа предложена {user.first_name}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка предложения программы: {e}")
            return "❌ Ошибка предложения программы"

    async def _handle_order_info(self, order_id: int, session) -> str:
        """Обрабатывает запрос информации о заказе"""
        try:
            order = await session.get(Order, order_id)
            if not order:
                return "❌ Заказ не найден"
                
            user = await session.get(User, order.user_id)
            if not user:
                return "❌ Пользователь заказа не найден"
                
            order_info = (
                f"📦 *Информация о заказе #{order_id}*\n\n"
                f"*Клиент:* {user.first_name} (@{user.username})\n"
                f"*Телефон:* {user.phone or 'Не указан'}\n"
                f"*Сумма:* {order.amount} руб\n"
                f"*Статус:* {order.payment_status}\n"
                f"*Дата создания:* {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            )
            
            if order.payment_date:
                order_info += f"*Дата оплаты:* {order.payment_date.strftime('%d.%m.%Y %H:%M')}\n"
                
            await self.bot.send_message(
                config.MANAGER_GROUP_ID,
                order_info,
                parse_mode="Markdown"
            )
            
            return f"✅ Информация о заказе #{order_id} отправлена"
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о заказе: {e}")
            return "❌ Ошибка получения информации"

    async def handle_text_command(self, message: Message) -> str:
        """Обрабатывает текстовые команды менеджеров"""
        try:
            if not await self._is_manager(message.from_user.id):
                return "⛔ Доступ запрещен"

            command = message.text.split()[0].lower()
            
            if command == "/stats":
                return await self._handle_stats_command()
            elif command == "/users":
                return await self._handle_users_command(message)
            elif command == "/orders":
                return await self._handle_orders_command(message)
            elif command == "/export":
                return await self._handle_export_command(message)
            elif command.startswith("/add_manager"):
                return await self._handle_add_manager(message)
            elif command.startswith("/create_ref"):
                return await self._handle_create_referral(message)
            else:
                return "❌ Неизвестная команда. Доступные команды: /stats, /users, /orders, /export, /add_manager, /create_ref"

        except Exception as e:
            logger.error(f"❌ Ошибка обработки текстовой команды: {e}")
            return "❌ Ошибка выполнения команды"

    async def _handle_stats_command(self) -> str:
        """Обрабатывает команду статистики"""
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
            
            return stats_text
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return "❌ Ошибка получения статистики"

    async def _handle_users_command(self, message: Message) -> str:
        """Обрабатывает команду списка пользователей"""
        try:
            from database import get_all_users
            
            # Парсим параметры
            args = message.text.split()
            limit = 10
            if len(args) > 1:
                try:
                    limit = min(int(args[1]), 50)  # Максимум 50 пользователей
                except ValueError:
                    pass
            
            users = await get_all_users(limit=limit)
            
            if not users:
                return "❌ Пользователи не найдены"
            
            users_text = f"👥 *Последние {len(users)} пользователей:*\n\n"
            for user in users:
                status_emoji = {
                    'lead': '🆕', 'active': '🟢', 'paid': '💰', 
                    'kit_sent': '📦', 'program_started': '🌱'
                }.get(user.status, '⚪')
                
                users_text += (
                    f"{status_emoji} *{user.first_name}* "
                    f"(ID: {user.id}) - {user.status}\n"
                    f"📅 {user.created_at.strftime('%d.%m.%Y')}\n\n"
                )
            
            return users_text
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения пользователей: {e}")
            return "❌ Ошибка получения списка пользователей"

    async def _handle_export_command(self, message: Message) -> str:
        """Обрабатывает команду экспорта данных"""
        try:
            from database import get_all_users, get_all_orders
            
            users = await get_all_users(limit=1000)
            orders = await get_all_orders(limit=1000)
            
            # Создаем DataFrame для пользователей
            users_data = []
            for user in users:
                users_data.append({
                    'ID': user.id,
                    'Telegram ID': user.tg_id,
                    'Имя': user.first_name,
                    'Username': user.username,
                    'Телефон': user.phone,
                    'Город': user.city,
                    'Статус': user.status,
                    'Источник': user.source,
                    'Сценарий': user.scenario,
                    'Дата регистрации': user.created_at
                })
            
            users_df = pd.DataFrame(users_data)
            
            # Создаем буфер для Excel файла
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                users_df.to_excel(writer, sheet_name='Пользователи', index=False)
                
                if orders:
                    orders_data = []
                    for order in orders:
                        orders_data.append({
                            'ID заказа': order.id,
                            'ID пользователя': order.user_id,
                            'Имя пользователя': getattr(order, 'first_name', ''),
                            'Сумма': order.amount,
                            'Статус': order.payment_status,
                            'Дата создания': order.created_at
                        })
                    
                    orders_df = pd.DataFrame(orders_data)
                    orders_df.to_excel(writer, sheet_name='Заказы', index=False)
            
            buffer.seek(0)
            
            # Отправляем файл
            await self.bot.send_document(
                chat_id=message.chat.id,
                document=('export.xlsx', buffer),
                caption="📊 Экспорт данных"
            )
            
            return "✅ Файл экспорта отправлен"
            
        except Exception as e:
            logger.error(f"❌ Ошибка экспорта данных: {e}")
            return "❌ Ошибка экспорта данных"

    async def _handle_add_manager(self, message: Message) -> str:
        """Добавляет нового менеджера"""
        try:
            # Только админ может добавлять менеджеров
            if message.from_user.id != config.ADMIN_ID:
                return "⛔ Только администратор может добавлять менеджеров"
            
            args = message.text.split()
            if len(args) < 2:
                return "❌ Использование: /add_manager <telegram_id> [username]"
            
            tg_id = int(args[1])
            username = args[2] if len(args) > 2 else None
            
            async with AsyncSessionLocal() as session:
                # Проверяем, не является ли уже менеджером
                existing = await session.execute(
                    select(Manager).where(Manager.tg_id == tg_id)
                )
                if existing.scalar_one_or_none():
                    return "❌ Этот пользователь уже является менеджером"
                
                manager = Manager(
                    tg_id=tg_id,
                    username=username,
                    first_name=username or "Менеджер",
                    is_active=True,
                    can_edit_content=False
                )
                session.add(manager)
                await session.commit()
            
            return f"✅ Менеджер {tg_id} добавлен"
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления менеджера: {e}")
            return "❌ Ошибка добавления менеджера"

    async def _handle_create_referral(self, message: Message) -> str:
        """Создает реферальную ссылку"""
        try:
            if not await self._is_manager(message.from_user.id):
                return "⛔ Доступ запрещен"
            
            args = message.text.split()
            if len(args) < 3:
                return "❌ Использование: /create_ref <название> <сценарий>"
            
            name = args[1]
            scenario = args[2]
            source_code = f"src_{name.lower()}_{datetime.now().strftime('%m%d')}"
            
            async with AsyncSessionLocal() as session:
                referral = ReferralLink(
                    name=name,
                    source_code=source_code,
                    scenario=scenario,
                    is_active=True,
                    created_by=message.from_user.id
                )
                session.add(referral)
                await session.commit()
            
            bot_username = (await self.bot.get_me()).username
            referral_link = f"https://t.me/{bot_username}?start={source_code}"
            
            return f"✅ Реферальная ссылка создана:\n\n`{referral_link}`"
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания реферальной ссылки: {e}")
            return "❌ Ошибка создания реферальной ссылки"

# Глобальный экземпляр менеджера
manager_bot = None

def init_manager_bot(bot: Bot):
    """Инициализирует менеджерский бот"""
    global manager_bot
    manager_bot = ManagerBot(bot)
    return manager_bot
