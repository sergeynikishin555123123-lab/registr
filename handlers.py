from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

class QuizStates(StatesGroup):
    waiting_for_answer = State()

router = Router()

@router.message(Command("quiz"))
async def start_quiz(message: types.Message, state: FSMContext):
    """Начало квиза"""
    from utils import content_manager
    from main import get_user
    
    user = await get_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    text = content_manager.get_text("start_default", user.scenario)
    buttons = content_manager.get_buttons("start_default", user.scenario)
    
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=btn)] for btn in buttons],
        resize_keyboard=True
    )
    
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(QuizStates.waiting_for_answer)

@router.message(QuizStates.waiting_for_answer)
async def process_quiz_answer(message: types.Message, state: FSMContext):
    """Обработка ответов в квизе"""
    from main import save_quiz_answer
    
    # Сохраняем ответ в БД
    await save_quiz_answer(message.from_user.id, "question_1", message.text)
    
    await message.answer("✅ Ответ сохранен! Следующий вопрос...")
    await state.clear()
