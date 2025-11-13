import logging
from datetime import datetime, timedelta
from database import AsyncSessionLocal, ProgramProgress
from sqlalchemy import select

logger = logging.getLogger(__name__)

class ProgramManager:
    def __init__(self, bot):
        self.bot = bot
        self.program_content = {
            1: "🌱 *День 1: Осознание дыхания*\n\nСегодня просто наблюдайте за своим дыханием. 3 раза в день по 2 минуты.\n\n*Задание:* Сядьте удобно и просто дышите, не меняя ритм.",
            2: "🌱 *День 2: Утренний ритуал*\n\nНачните день со стакана теплой воды. Это запустит метаболизм.\n\n*Задание:* Выпейте стакан теплой воды сразу после пробуждения.",
            3: "🌱 *День 3: Цифровой детокс*\n\nОтдохните от экранов за 1 час до сна.\n\n*Задание:* Отложите гаджеты за час до сна.",
            # ... остальные дни программы
            14: "🎉 *День 14: Завершение программы*\n\nПоздравляем! Вы прошли 14-дневную программу.\n\nРекомендуем повторить анализ через 3 месяца."
        }
    
    async def start_program(self, user_id: int):
        """Запускает 14-дневную программу"""
        async with AsyncSessionLocal() as session:
            # Запускаем с дня 1
            progress = ProgramProgress(user_id=user_id, day_number=1)
            session.add(progress)
            await session.commit()
            
            # Отправляем первый день
            await self.send_day_message(user_id, 1)
            
        logger.info(f"✅ 14-дневная программа запущена для пользователя {user_id}")
    
    async def send_day_message(self, user_id: int, day: int):
        """Отправляет сообщение дня"""
        try:
            from database import get_user_by_tg_id
            user = await get_user_by_tg_id(user_id)
            if user and day in self.program_content:
                message = self.program_content[day]
                await self.bot.send_message(user.tg_id, message, parse_mode="Markdown")
                logger.info(f"✅ Сообщение дня {day} отправлено пользователю {user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения дня: {e}")
    
    async def mark_day_completed(self, user_id: int, day: int):
        """Отмечает день как выполненный"""
        async with AsyncSessionLocal() as session:
            progress = await session.execute(
                select(ProgramProgress).where(
                    ProgramProgress.user_id == user_id,
                    ProgramProgress.day_number == day
                )
            )
            progress_obj = progress.scalar_one_or_none()
            
            if progress_obj:
                progress_obj.completed = True
                progress_obj.completed_at = datetime.utcnow()
                await session.commit()
                
                # Запускаем следующий день
                if day < 14:
                    next_day_progress = ProgramProgress(
                        user_id=user_id,
                        day_number=day + 1
                    )
                    session.add(next_day_progress)
                    await session.commit()
                    
                    # Отправляем сообщение следующего дня
                    await self.send_day_message(user_id, day + 1)
                
                logger.info(f"✅ День {day} отмечен как выполненный для пользователя {user_id}")
