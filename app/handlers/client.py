from aiogram import Router, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardRemove

router = Router()

@router.message(CommandStart())
async def start_command(message: types.Message):
    await message.answer(
        "🎉 Добро пожаловать в GenoLife!\n\n"
        "Я помогу вам пройти анализ и улучшить здоровье.",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer("Помощь по боту...")
