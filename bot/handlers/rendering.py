import logging
from aiogram import Router
from aiogram.types import Message, ReplyKeyboardRemove, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from .. import keyboards as kb, database
from ..services import rendering_display

router = Router()

class LatexRender(StatesGroup):
    formula = State()

class MermaidRender(StatesGroup):
    code = State()

##################################################################################################
# LATEX
##################################################################################################

@router.message(Command('latex'))
async def latex_command(message: Message, state: FSMContext):
    await state.set_state(LatexRender.formula)
    await message.answer(
        "Пожалуйста, отправьте вашу формулу в синтаксисе LaTeX (можно без внешних `$...`):",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(LatexRender.formula)
async def process_latex_formula(message: Message, state: FSMContext):
    await state.clear()
    formula = message.text
    
    status_msg = await message.answer("🖼️ Рендеринг формулы...")
    await message.bot.send_chat_action(message.chat.id, "upload_photo") 
    try:
        settings = await database.get_user_settings(message.from_user.id)
        padding = settings['latex_padding']
        dpi = settings['latex_dpi']
        image_buffer = await rendering_display.render_latex_to_image(formula, padding, dpi)
        
        await status_msg.delete()
        await message.answer_photo(
            photo=BufferedInputFile(image_buffer.read(), filename="formula.png"),
            caption=f"Ваша формула:\n`{formula}`",
            parse_mode='markdown'
        )
        await message.answer("Готово! Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))

    except (ValueError, RuntimeError, FileNotFoundError) as e:
        logging.error(f"Ошибка при рендеринге LaTeX для '{formula}': {e}", exc_info=True)
        # Используем Markdown для форматирования ошибки
        error_text = f"Не удалось отрендерить формулу.\n\n**Ошибка:**\n```\n{e}\n```\n\nУбедитесь, что синтаксис корректен."
        await status_msg.edit_text(error_text, parse_mode='markdown')
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при рендеринге LaTeX для '{formula}': {e}", exc_info=True)
        await status_msg.edit_text(
            f"Произошла непредвиденная ошибка: {e}"
        )

##################################################################################################
# MERMAID
##################################################################################################

@router.message(Command('mermaid'))
async def mermaid_command(message: Message, state: FSMContext):
    """Handles the /mermaid command for rendering diagrams."""
    await state.set_state(MermaidRender.code)
    await message.answer(
        "Пожалуйста, отправьте код диаграммы в синтаксисе Mermaid:",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(MermaidRender.code)
async def process_mermaid_code(message: Message, state: FSMContext):
    """Renders the received Mermaid code into a PNG image."""
    await state.clear()
    mermaid_code = message.text
    
    status_msg = await message.answer("🎨 Рендеринг диаграммы...")
    await message.bot.send_chat_action(message.chat.id, "upload_photo")
    try:
        image_buffer = await rendering_display.render_mermaid_to_image(mermaid_code)
        
        await status_msg.delete()
        await message.answer_photo(
            photo=BufferedInputFile(image_buffer.read(), filename="diagram.png"),
            caption=f"Ваша диаграмма Mermaid."
        )
        await message.answer("Готово! Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))

    except (ValueError, RuntimeError) as e:
        error_text = f"Не удалось отрендерить диаграмму.\n\n**Ошибка:**\n```\n{e}\n```"
        await status_msg.edit_text(error_text, parse_mode='markdown')

