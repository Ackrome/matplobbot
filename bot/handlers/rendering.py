import logging
from aiogram import Router
from aiogram.types import Message, ReplyKeyboardRemove, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from .. import keyboards as kb, database
from ..services import document_renderer
from ..i18n import translator

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
    lang = await translator.get_user_language(message.from_user.id)
    await state.set_state(LatexRender.formula)
    await message.answer(
        translator.gettext(lang, "latex_prompt"),
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(LatexRender.formula)
async def process_latex_formula(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    formula = message.text
    
    status_msg = await message.answer(translator.gettext(lang, "latex_rendering"))
    await message.bot.send_chat_action(message.chat.id, "upload_photo") 
    try:
        settings = await database.get_user_settings(user_id)
        padding = settings['latex_padding']
        dpi = settings['latex_dpi']
        image_buffer = await document_renderer.render_latex_to_image(formula, padding, dpi)
        
        await status_msg.delete()
        await message.answer_photo(
            photo=BufferedInputFile(image_buffer.read(), filename="formula.png"),
            caption=translator.gettext(lang, "latex_your_formula", formula=formula),
            parse_mode='markdown'
        )
        await message.answer(translator.gettext(lang, "choose_next_command"), reply_markup=await kb.get_main_reply_keyboard(user_id))

    except (ValueError, RuntimeError, FileNotFoundError) as e:
        logging.error(f"Ошибка при рендеринге LaTeX для '{formula}': {e}", exc_info=True)
        # Используем Markdown для форматирования ошибки
        error_text = translator.gettext(lang, "latex_render_error", error=e)
        await status_msg.edit_text(error_text, parse_mode='markdown')
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при рендеринге LaTeX для '{formula}': {e}", exc_info=True)
        await status_msg.edit_text(
            translator.gettext(lang, "latex_unexpected_error", error=e)
        )

##################################################################################################
# MERMAID
##################################################################################################

@router.message(Command('mermaid'))
async def mermaid_command(message: Message, state: FSMContext):
    """Handles the /mermaid command for rendering diagrams."""
    lang = await translator.get_user_language(message.from_user.id)
    await state.set_state(MermaidRender.code)
    await message.answer(
        translator.gettext(lang, "mermaid_prompt"),
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(MermaidRender.code)
async def process_mermaid_code(message: Message, state: FSMContext):
    """Renders the received Mermaid code into a PNG image."""
    await state.clear()
    user_id = message.from_user.id
    lang = await translator.get_user_language(user_id)
    mermaid_code = message.text
    
    status_msg = await message.answer(translator.gettext(lang, "mermaid_rendering"))
    await message.bot.send_chat_action(message.chat.id, "upload_photo")
    try:
        image_buffer = await document_renderer.render_mermaid_to_image(mermaid_code)
        
        await status_msg.delete()
        await message.answer_photo(
            photo=BufferedInputFile(image_buffer.read(), filename="diagram.png"),
            caption=translator.gettext(lang, "mermaid_your_diagram")
        )
        await message.answer(translator.gettext(lang, "choose_next_command"), reply_markup=await kb.get_main_reply_keyboard(user_id))

    except (ValueError, RuntimeError) as e:
        error_text = translator.gettext(lang, "mermaid_render_error", error=e)
        await status_msg.edit_text(error_text, parse_mode='markdown')
