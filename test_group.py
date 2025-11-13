import asyncio
import logging
from aiogram import Bot
from config import config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_group():
    """Тестирует отправку сообщений в группу менеджеров"""
    bot = Bot(token=config.BOT_TOKEN)
    
    try:
        logger.info("🧪 Тестирование отправки в группу менеджеров...")
        
        if config.MANAGER_GROUP_ID:
            # Отправляем тестовое сообщение в группу
            await bot.send_message(
                chat_id=config.MANAGER_GROUP_ID,
                text="🧪 *Тестовое сообщение от бота GenoLife*\n\n"
                     "✅ Группа менеджеров успешно настроена!\n\n"
                     "Теперь все уведомления о новых заказах и карточки клиентов "
                     "будут приходить в эту группу.",
                parse_mode="Markdown"
            )
            logger.info(f"✅ Тестовое сообщение отправлено в группу {config.MANAGER_GROUP_ID}")
        else:
            logger.error("❌ MANAGER_GROUP_ID не настроен!")
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки тестового сообщения: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test_group())
