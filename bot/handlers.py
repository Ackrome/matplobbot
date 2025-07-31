import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database
import asyncio
import sys
import matplobblib
import os
import pkg_resources
import io
import contextlib
import tempfile # Для создания временных директорий
import shutil   # Для удаления временных директорий
import glob # Для поиска файлов по шаблону
import traceback

# from main import logging

import keyboards as kb

async def update_library_async(library_name):
    try:
        process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pip", "install", "--upgrade", library_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            print(f"Библиотека '{library_name}' успешно обновлена! {stdout.decode()}")
            return True, f"Библиотека '{library_name}' успешно обновлена! Текущая версия: {pkg_resources.get_distribution('matplobblib').version}"
        else:
            print(f"Ошибка при обновлении библиотеки '{library_name}': {stderr.decode()}")
            return False, f"Ошибка при обновлении библиотеки '{library_name}': {stderr.decode()}"
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        return False, f"Произошла непредвиденная ошибка: {e}"


router = Router()

# --- User Settings Defaults ---
# Эти настройки используются по умолчанию, если для пользователя нет записи в БД
# или если конкретная настройка отсутствует в его записи.
DEFAULT_SETTINGS = {
    'show_docstring': True,
}

# Теперь эта функция асинхронная, так как обращается к БД
async def get_user_settings(user_id: int) -> dict:
    """Получает настройки для пользователя из БД, объединяя их с настройками по умолчанию."""
    db_settings = await database.get_user_settings_db(user_id)
    merged_settings = DEFAULT_SETTINGS.copy()
    merged_settings.update(db_settings) # Настройки из БД переопределяют дефолтные
    return merged_settings


@router.message(CommandStart())
async def comand_start(message: Message):
    await message.answer(
        f'Привет, {message.from_user.full_name}!',
        reply_markup=kb.get_main_reply_keyboard(message.from_user.id)
    )
    
@router.message(Command('help'))
async def comand_help(message: Message):
    await message.answer(
        'Это бот для поиска примеров кода по библиотеке matplobblib.\n\n'
        'Нажмите на кнопку, чтобы выполнить команду:',
        reply_markup=kb.get_help_inline_keyboard(message.from_user.id)
    )

##################################################################################################
# ASK
##################################################################################################
class Search(StatesGroup):
    submodule = State()
    topic = State()
    code = State()


@router.message(Command('ask'))
async def ask(message: Message, state: FSMContext):
    await state.set_state(Search.submodule)
    await message.answer('Введите ваш вопрос', reply_markup=kb.get_submodules_reply_keyboard(message.from_user.id))

@router.message(Search.submodule)
async def process_submodule(message: Message, state: FSMContext):
    # Проверяем, что введённый подмодуль является ожидаемым
    if message.text not in matplobblib.submodules:
        await message.answer("Неверный выбор. Попробуйте еще раз.", reply_markup=kb.get_submodules_reply_keyboard(message.from_user.id))
        return
    await state.update_data(submodule=message.text)
    # Импортируем модуль для получения списка тем
    module = matplobblib._importlib.import_module(f'matplobblib.{message.text}')

    settings = await get_user_settings(message.from_user.id) # Теперь асинхронный вызов
    # В зависимости от настроек пользователя, выбираем нужный словарь в библиотеке
    dict_name = 'themes_list_dicts_full' if settings.get('show_docstring', True) else 'themes_list_dicts_full_nd'
    code_dictionary = getattr(module, dict_name)
    topics = list(code_dictionary.keys())
    await state.set_state(Search.topic)
    await message.answer("Введите тему", reply_markup=kb.get_topics_reply_keyboard(message.from_user.id, message.text))

@router.message(Search.topic)
async def process_topic(message: Message, state: FSMContext):
    data = await state.get_data()
    submodule = data["submodule"]
    module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')

    settings = await get_user_settings(message.from_user.id) # Теперь асинхронный вызов
    dict_name = 'themes_list_dicts_full' if settings.get('show_docstring', True) else 'themes_list_dicts_full_nd'
    code_dictionary = getattr(module, dict_name)
    topics = list(code_dictionary.keys())
    # Если тема не входит в ожидаемые, просим попробовать снова
    if message.text not in topics:
        await message.answer("Неверный выбор. Попробуйте еще раз.", reply_markup=kb.get_topics_reply_keyboard(message.from_user.id, submodule))
        return
    await state.update_data(topic=message.text)
    await state.set_state(Search.code)
    await message.answer("Выберите задачу", reply_markup=kb.get_codes_reply_keyboard(message.from_user.id, submodule, message.text))

@router.message(Search.code)
async def process_code(message: Message, state: FSMContext):
    data = await state.get_data()
    submodule = data["submodule"]
    topic = data["topic"]
    module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')

    settings = await get_user_settings(message.from_user.id) # Теперь асинхронный вызов
    # В зависимости от настроек пользователя, выбираем нужный словарь в библиотеке
    dict_name = 'themes_list_dicts_full' if settings.get('show_docstring', True) else 'themes_list_dicts_full_nd'
    code_dictionary = getattr(module, dict_name)

    possible_codes = list(code_dictionary[topic].keys())
    # Если выбранная задача не входит в ожидаемые, просим повторить выбор
    if message.text not in possible_codes:
        await message.answer("Неверный выбор. Попробуйте еще раз.", reply_markup=kb.get_codes_reply_keyboard(message.from_user.id, submodule, topic))
        return
    await state.update_data(code=message.text)
    data = await state.get_data()
    await message.answer(f'Ваш запрос: \n{submodule} \n{topic} \n{data["code"]}')
    repl = code_dictionary[topic][data["code"]]
    if len(repl) > 4096:
        await message.answer('Сообщение будет отправлено в нескольких частях')
        for x in range(0, len(repl), 4096):
            await message.answer(f'''```python\n{repl[x:x+4096]}\n```''', parse_mode='markdown', reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
    else:
        await message.answer(f'''```python\n{repl}\n```''', parse_mode='markdown', reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
    await state.clear()
##################################################################################################
# UPDATE
##################################################################################################
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))

@router.message(Command('update'))
async def update(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("У вас нет прав на использование этой команды.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    status_msg = await message.answer("Начинаю обновление библиотеки `matplobblib`...")
    # Можно добавить 
    # await message.answer_chat_action("typing")
    success, status_message_text = await update_library_async('matplobblib')
    if success:
        # Перезагрузка модуля matplobblib, если это необходимо для немедленного применения изменений
        import importlib
        importlib.reload(matplobblib) # Может быть сложным и иметь побочные эффекты
        await status_msg.edit_text(status_message_text) # Убран reply_markup
    else:
        await status_msg.edit_text(status_message_text) # Убран reply_markup

##################################################################################################
# EXECUTE
##################################################################################################
class Execution(StatesGroup):
    code = State()
EXECUTE_HELP_TEXT = (
    "Пожалуйста, отправьте код Python для выполнения. Если ваш код генерирует изображения (например, с помощью `matplotlib.pyplot.savefig`), они будут отправлены вам.\n\n"
    "**Поддерживаемый вывод:**\n"
    "1.  **Текстовый вывод** (stdout/stderr).\n"
    "2.  **Изображения**, сохраненные в файл (png, jpg, jpeg, gif).\n"
    "3.  **Форматированный текст** (Markdown/HTML).\n\n"
    "**Пример с Matplotlib:**\n"
    "```python\n"
    "import matplotlib.pyplot as plt\n"
    "plt.plot([1, 2, 3], [1, 4, 9])\n"
    "plt.savefig('my_plot.png')\n"
    "plt.close()\n"
    "```\n\n"
    "**Пример с форматированным текстом:**\n"
    "Функции `display`, `Markdown`, `HTML` доступны без импорта.\n"
    "```python\n"
    "display(Markdown('# Заголовок 1\\n## Заголовок 2\\n*Курсив*'))\n"
    "```"
)

@router.message(Command('execute'))
async def execute_command(message: Message, state: FSMContext):
    """Handles the /execute command"""#, admin-only."""
    # if message.from_user.id != ADMIN_USER_ID:
    #     await message.reply("У вас нет прав на использование этой команды.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
    #     return

    await state.set_state(Execution.code)
    await message.answer(
        EXECUTE_HELP_TEXT,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='markdown'
    )

@router.message(Execution.code)
async def process_execution(message: Message, state: FSMContext):
    """Executes the received Python code and sends back the output, including images and rich display objects."""
    await state.clear()
    code_to_execute = message.text
    output_capture = io.StringIO()
    execution_error = None
    temp_dir = None
    original_cwd = os.getcwd() # Сохраняем текущую рабочую директорию
    rich_outputs = []

    # 1. Подготовка изолированного окружения (globals) для выполнения кода
    exec_globals = { 
        "asyncio": asyncio,
        "message": message,
        "os": os,
        "sys": sys,
        "__builtins__": __builtins__,
    }
    def convert_html_to_telegram_html(html_content: str) -> str:
        """Converts generic HTML to Telegram-supported HTML."""
        # Headers to bold
        for i in range(1, 7):
            html_content = html_content.replace(f'<h{i}>', '<b>').replace(f'</h{i}>', '</b>')

        # Paragraphs to newlines
        html_content = html_content.replace('<p>', '').replace('</p>', '\n')

        # Lists
        html_content = html_content.replace('<ul>', '').replace('</ul>', '')
        html_content = html_content.replace('<ol>', '').replace('</ol>', '')
        html_content = html_content.replace('<li>', '• ').replace('</li>', '\n')

        # Other replacements
        html_content = html_content.replace('<em>', '<i>').replace('</em>', '</i>')
        html_content = html_content.replace('<strong>', '<b>').replace('</strong>', '</b>')

        # Clean up extra newlines and spaces
        lines = [line.strip() for line in html_content.split('\n')]
        return '\n'.join(filter(None, lines))

    # 2. Попытка импорта "rich display" библиотек и внедрение кастомных функций
    try:
        from IPython.display import display as ipython_display, Markdown, HTML
        import markdown

        def custom_display(*objs, **kwargs):
            """Перехватывает вызовы display, обрабатывает Markdown/HTML и делегирует остальное."""
            for obj in objs:
                if isinstance(obj, Markdown):
                    html_content = markdown.markdown(obj.data, extensions=['fenced_code'])
                    tg_html = convert_html_to_telegram_html(html_content)
                    rich_outputs.append({'type': 'html', 'content': tg_html})
                elif isinstance(obj, HTML):
                    tg_html = convert_html_to_telegram_html(obj.data)
                    rich_outputs.append({'type': 'html', 'content': tg_html})
                else:
                    # Для других объектов используем стандартный display,
                    # который выведет их текстовое представление в stdout (который мы перехватываем)
                    # For other objects, capture their string representation.
                    # This avoids unexpected behavior from ipython_display outside an IPython kernel.
                    output_capture.write(repr(obj) + '\n')

        # Внедряем наши функции и классы в окружение для выполнения 
        exec_globals['display'] = custom_display 
        exec_globals['Markdown'] = Markdown
        exec_globals['HTML'] = HTML

    except ImportError:
        logging.warning("IPython или markdown не установлены. Rich display отключен для /execute.")
        pass

    # 3. Выполнение кода пользователя в контролируемом окружении
    try:
        temp_dir = tempfile.mkdtemp()
        os.chdir(temp_dir)

        with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(output_capture):
            local_scope = {} # Словарь для получения результата exec (самой функции)
            wrapped_code = f"async def __exec_code():\n"
            wrapped_code += "".join([f"    {line}\n" for line in code_to_execute.splitlines()])
            
            exec(wrapped_code, exec_globals, local_scope)
            await local_scope["__exec_code"]()
            
    except Exception:
        execution_error = f"--- ОШИБКА ВЫПОЛНЕНИЯ ---\n{traceback.format_exc()}"
    finally:
        os.chdir(original_cwd)

        # --- Отправка результатов ---
        if execution_error:
            await message.answer(f"```\n{execution_error}\n```", parse_mode='markdown')

        # Отправляем rich-вывод (HTML)
        for output in rich_outputs: 
            content_to_send = output['content'] # This is the raw HTML or Markdown string
            parse_mode = None # Default to no parse mode, will be set based on type

            if output['type'] == 'markdown':
                # Convert Markdown to HTML first
                content_to_send = markdown.markdown(content_to_send, extensions=['fenced_code'])
                # Then apply Telegram-specific HTML conversion for basic tags
                content_to_send = convert_html_to_telegram_html(content_to_send)
                parse_mode = 'HTML'
            elif output['type'] == 'html':
                # For explicit HTML objects, try to send raw HTML and let Telegram parse it.
                # convert_html_to_telegram_html is NOT applied here, relying on Telegram's parser.
                parse_mode = 'HTML'

            if content_to_send:
                try:
                    await message.answer(content_to_send, parse_mode=parse_mode)
                except TelegramBadRequest as e:
                    logging.warning(f"TelegramBadRequest when sending rich output (type: {output['type']}): {e}. Attempting to send as file.")
                    # If Telegram HTML fails, save as .html file and send
                    file_name = f"output_{output['type']}_{len(rich_outputs)}.html"
                    file_path = os.path.join(temp_dir, file_name)
                    
                    # Ensure the content written to file is the original, full HTML
                    # For markdown, this would be the markdown-converted HTML
                    # For HTML, this would be the raw HTML from obj.data
                    content_to_write = output['content'] # Original content
                    if output['type'] == 'markdown':
                        content_to_write = markdown.markdown(content_to_write, extensions=['fenced_code'])

                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content_to_write)
                    try:
                        await message.answer_document(
                            document=FSInputFile(file_path),
                            caption=f"Вывод ({output['type']}) был отправлен как файл, так как он слишком сложен для отображения в Telegram."
                        )
                    except Exception as file_e:
                        logging.error(f"Failed to send rich output as file {file_path}: {file_e}")
                        await message.answer(f"Не удалось отправить rich-вывод как файл: {file_e}")
                except Exception as e:
                    logging.error(f"Unexpected error when sending rich output: {e}")
                    await message.answer(f"Произошла ошибка при отправке rich-вывода: {e}")

        # Ищем и отправляем сгенерированные изображения 
        image_files = [] 
        if temp_dir: 
            for ext in ['*.png', '*.jpg', '*.jpeg', '*.gif']:
                image_files.extend(glob.glob(os.path.join(temp_dir, ext)))
            
            for img_path in image_files:
                try:
                    await message.answer_photo(photo=FSInputFile(img_path))
                except Exception as e:
                    logging.error(f"Failed to send photo {img_path}: {e}")
                    await message.answer(f"Не удалось отправить изображение {os.path.basename(img_path)}: {e}")

        # Отправляем текстовый вывод, если он есть
        text_output = output_capture.getvalue()
        if text_output:
            if len(text_output) > 4096:
                await message.answer('Текстовый вывод слишком длинный, отправляю частями.')
                for x in range(0, len(text_output), 4096):
                    await message.answer(f"```\n{text_output[x:x+4096]}\n```", parse_mode='markdown')
            else:
                await message.answer(f"```\n{text_output}\n```", parse_mode='markdown')

        # Сообщение, если не было ни вывода, ни картинок, ни ошибок
        if not execution_error and not image_files and not text_output and not rich_outputs:
            await message.answer("Код выполнен успешно без какого-либо вывода.")

        # Очищаем временную директорию
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logging.error(f"Ошибка при удалении временной директории {temp_dir}: {e}")

        # Возвращаем основную клавиатуру
        await message.answer("Выполнение завершено.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))

##################################################################################################
# SETTINGS
##################################################################################################

# Теперь эта функция асинхронная, так как обращается к БД
async def get_settings_keyboard(user_id: int) -> InlineKeyboardBuilder:
    """Создает инлайн-клавиатуру для настроек пользователя."""
    settings = await get_user_settings(user_id) # Теперь асинхронный вызов
    builder = InlineKeyboardBuilder()

    show_docstring_status = "✅ Вкл" if settings.get('show_docstring', True) else "❌ Выкл"

    builder.row(
        InlineKeyboardButton(
            text=f"Показывать описание: {show_docstring_status}",
            callback_data="settings_toggle_docstring"
        )
    )
    # Здесь можно добавлять новые настройки
    return builder

@router.message(Command('settings'))
async def command_settings(message: Message):
    """Обработчик команды /settings."""
    keyboard = await get_settings_keyboard(message.from_user.id) # Теперь асинхронный вызов
    await message.answer(
        "⚙️ Настройки пользователя:",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data == "settings_toggle_docstring")
async def cq_toggle_docstring(callback: CallbackQuery):
    """Обработчик для переключения настройки 'show_docstring'."""
    user_id = callback.from_user.id
    settings = await get_user_settings(user_id) # Теперь асинхронный вызов
    settings['show_docstring'] = not settings.get('show_docstring', True)
    await database.update_user_settings_db(user_id, settings) # Сохраняем обновленные настройки в БД
    keyboard = await get_settings_keyboard(user_id) # Теперь асинхронный вызов
    await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    await callback.answer("Настройка 'Показывать описание' обновлена.")

##################################################################################################
# HELP COMMAND CALLBACKS
##################################################################################################

@router.callback_query(F.data == "help_cmd_ask")
async def cq_help_cmd_ask(callback: CallbackQuery, state: FSMContext):
    """Handler for '/ask' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /ask
    await state.set_state(Search.submodule)
    await callback.message.answer('Введите ваш вопрос', reply_markup=kb.get_submodules_reply_keyboard(callback.from_user.id))

@router.callback_query(F.data == "help_cmd_settings")
async def cq_help_cmd_settings(callback: CallbackQuery):
    """Handler for '/settings' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /settings
    keyboard = await get_settings_keyboard(callback.from_user.id)
    await callback.message.answer(
        "⚙️ Настройки пользователя:",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data == "help_cmd_update")
async def cq_help_cmd_update(callback: CallbackQuery):
    """Handler for '/update' button from help menu."""
    if callback.from_user.id != ADMIN_USER_ID:
        await callback.answer("У вас нет прав на использование этой команды.", show_alert=True)
        return

    await callback.answer("Начинаю обновление...")
    
    # Повторяем логику команды /update
    status_msg = await callback.message.answer("Начинаю обновление библиотеки `matplobblib`...")
    success, status_message_text = await update_library_async('matplobblib')
    if success:
        import importlib
        importlib.reload(matplobblib)
        await status_msg.edit_text(status_message_text)
    else:
        await status_msg.edit_text(status_message_text)

@router.callback_query(F.data == "help_cmd_execute")
async def cq_help_cmd_execute(callback: CallbackQuery, state: FSMContext):
    """Handler for '/execute' button from help menu."""
    #if callback.from_user.id != ADMIN_USER_ID:
        #await callback.answer("У вас нет прав на использование этой команды.", show_alert=True)
        #return

    await callback.answer()
    # Повторяем логику команды /execute
    await state.set_state(Execution.code)
    await callback.message.answer(
        EXECUTE_HELP_TEXT,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='markdown'
    )

@router.callback_query(F.data == "help_cmd_help")
async def cq_help_cmd_help(callback: CallbackQuery):
    """Handler for '/help' button from help menu. Edits the message."""
    try:
        # Пытаемся отредактировать сообщение, чтобы обновить его до актуального состояния
        await callback.message.edit_text(
            'Это бот для поиска примеров кода по библиотеке matplobblib.\n\n'
            'Нажмите на кнопку, чтобы выполнить команду:',
            reply_markup=kb.get_help_inline_keyboard(callback.from_user.id)
        )
        await callback.answer()
    except TelegramBadRequest as e:
        # Если сообщение не изменилось, Telegram выдаст ошибку.
        # Мы просто отвечаем на колбэк, чтобы убрать "часики" с кнопки.
        if "message is not modified" in e.message:
            await callback.answer("Вы уже в меню помощи.")
        else:
            # Перевыбрасываем другие, непредвиденные ошибки
            raise