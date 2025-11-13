import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from database import AsyncSessionLocal, get_pending_notifications, mark_notification_sent
from notifications import NotificationManager
from sqlalchemy import text
import pytz

logger = logging.getLogger(__name__)

class SchedulerManager:
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.notification_manager = NotificationManager(bot)
        
    async def start_scheduler(self):
        """Запускает планировщик задач"""
        try:
            # Задачи для проверки уведомлений каждые 5 минут
            self.scheduler.add_job(
                self.process_notifications,
                'interval',
                minutes=5,
                id='process_notifications',
                replace_existing=True
            )
            
            # Ежедневная очистка старых данных в 3:00
            self.scheduler.add_job(
                self.cleanup_old_data,
                'cron',
                hour=3,
                minute=0,
                id='cleanup_old_data',
                replace_existing=True
            )
            
            # Ежедневная статистика для админа в 9:00
            self.scheduler.add_job(
                self.send_daily_stats,
                'cron',
                hour=9,
                minute=0,
                id='daily_stats',
                replace_existing=True
            )
            
            # Проверка программ прогресса каждые 10 минут
            self.scheduler.add_job(
                self.check_program_progress,
                'interval',
                minutes=10,
                id='check_program_progress',
                replace_existing=True
            )
            
            self.scheduler.start()
            logger.info("✅ Планировщик задач запущен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска планировщика: {e}")
    
    async def process_notifications(self):
        """Обрабатывает ожидающие уведомления"""
        try:
            processed_count = await self.notification_manager.process_pending_notifications()
            if processed_count > 0:
                logger.info(f"✅ Обработано {processed_count} уведомлений")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки уведомлений: {e}")
    
    async def cleanup_old_data(self):
        """Очищает старые данные"""
        try:
            from database import cleanup_old_data
            success = await cleanup_old_data(days=30)
            if success:
                logger.info("✅ Старые данные очищены")
            else:
                logger.error("❌ Ошибка очистки старых данных")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки данных: {e}")
    
    async def send_daily_stats(self):
        """Отправляет ежедневную статистику админу"""
        try:
            from database import get_statistics
            from config import config
            
            stats = await get_statistics()
            
            stats_message = (
                "📊 *Ежедневная статистика*\n\n"
                f"👥 Новые пользователи (за сутки): {await self._get_new_users_count()}\n"
                f"💰 Новые оплаты (за сутки): {await self._get_new_orders_count()}\n"
                f"📦 Всего заказов: {stats['total_orders']}\n"
                f"✅ Оплаченные заказы: {stats['paid_orders']}\n"
                f"🌱 Пользователи в программе: {stats['program_users']}\n"
                f"📈 Конверсия: {stats['conversion_rate']}%\n"
            )
            
            await self.bot.send_message(config.ADMIN_ID, stats_message, parse_mode="Markdown")
            logger.info("✅ Ежедневная статистика отправлена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки статистики: {e}")
    
    async def check_program_progress(self):
        """Проверяет прогресс программ и отправляет напоминания"""
        try:
            async with AsyncSessionLocal() as session:
                # Находим пользователей с активными программами
                result = await session.execute(text("""
                    SELECT DISTINCT user_id 
                    FROM program_progress 
                    WHERE completed = false AND skipped = false
                    AND created_at >= NOW() - INTERVAL '15 days'
                """))
                active_users = result.scalars().all()
                
                for user_id in active_users:
                    await self._check_user_program_reminders(user_id)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка проверки прогресса программ: {e}")
    
    async def _check_user_program_reminders(self, user_id: int):
        """Проверяет и отправляет напоминания для программ пользователя"""
        try:
            from programs import ProgramManager
            program_manager = ProgramManager(self.bot)
            
            # Здесь можно добавить логику отправки напоминаний
            # Например, если пользователь не завершил день в течение 24 часов
            
            logger.debug(f"🔍 Проверка напоминаний программы для пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки напоминаний программы: {e}")
    
    async def _get_new_users_count(self) -> int:
        """Возвращает количество новых пользователей за последние 24 часа"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("""
                    SELECT COUNT(*) FROM users 
                    WHERE created_at >= NOW() - INTERVAL '24 hours'
                """))
                count = result.scalar()
                return count or 0
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества новых пользователей: {e}")
            return 0
    
    async def _get_new_orders_count(self) -> int:
        """Возвращает количество новых оплат за последние 24 часа"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("""
                    SELECT COUNT(*) FROM orders 
                    WHERE payment_status = 'paid' 
                    AND payment_date >= NOW() - INTERVAL '24 hours'
                """))
                count = result.scalar()
                return count or 0
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества новых оплат: {e}")
            return 0
    
    async def schedule_collection_day(self, user_id: int, collection_date: datetime):
        """Планирует день сбора анализов для пользователя"""
        try:
            # Планируем напоминания о сборе
            await self.notification_manager.schedule_collection_reminders(user_id, collection_date)
            
            # Планируем вопрос после сбора
            await self.notification_manager.schedule_followup_question(user_id, collection_date)
            
            logger.info(f"✅ День сбора запланирован для пользователя {user_id} на {collection_date}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка планирования дня сбора: {e}")
            return False
    
    async def schedule_program_day(self, user_id: int, day_number: int, send_time: datetime):
        """Планирует отправку дня программы"""
        try:
            from programs import ProgramManager
            program_manager = ProgramManager(self.bot)
            
            # Планируем отправку сообщения дня
            self.scheduler.add_job(
                program_manager.send_day_message,
                DateTrigger(run_date=send_time),
                args=[user_id, day_number],
                id=f"program_day_{user_id}_{day_number}",
                replace_existing=True
            )
            
            logger.info(f"✅ День {day_number} программы запланирован для пользователя {user_id} на {send_time}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка планирования дня программы: {e}")
            return False
    
    def stop_scheduler(self):
        """Останавливает планировщик"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
                logger.info("✅ Планировщик остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки планировщика: {e}")

# Глобальный экземпляр планировщика
scheduler_manager = None

def init_scheduler(bot):
    """Инициализирует планировщик"""
    global scheduler_manager
    scheduler_manager = SchedulerManager(bot)
    return scheduler_manager
