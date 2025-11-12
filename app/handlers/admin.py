from aiogram import Router, types
from aiogram.filters import Command
from app.config import config

router = Router()

@router.message(Command("admin"))
async def admin_command(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    
    await message.answer("👨‍💻 Панель администратора")
