import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, FSInputFile
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

import hashlib
# from main import logging

import keyboards as kb

SEARCH_RESULTS_PER_PAGE = 10

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

# Cache for search results to avoid long callback_data
# {user_id: {'query': str, 'results': list}}
user_search_results_cache = {}

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
    query = State()


@router.message(Command('ask'))
async def ask(message: Message, state: FSMContext):
    await state.set_state(Search.submodule)
    await message.answer('Введите ваш вопрос', reply_markup=kb.get_submodules_reply_keyboard(message.from_user.id))

@router.message(Search.submodule)
async def process_submodule(message: Message, state: FSMContext):
    # Проверяем, что введённый подмодуль является ожидаемым
    if message.text not in kb.topics_data:
        await message.answer("Неверный выбор. Попробуйте еще раз.", reply_markup=kb.get_submodules_reply_keyboard(message.from_user.id))
        return
    await state.update_data(submodule=message.text)
    await state.set_state(Search.topic)
    await message.answer("Введите тему", reply_markup=kb.get_topics_reply_keyboard(message.from_user.id, message.text))

@router.message(Search.topic)
async def process_topic(message: Message, state: FSMContext):
    data = await state.get_data()
    submodule = data["submodule"]

    # Получаем список тем из предзагруженных данных для валидации
    topics = kb.topics_data.get(submodule, {}).get('topics', [])

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

    # Валидация из предзагруженных данных
    possible_codes = kb.topics_data.get(submodule, {}).get('codes', {}).get(topic, [])
    if message.text not in possible_codes:
        await message.answer("Неверный выбор. Попробуйте еще раз.", reply_markup=kb.get_codes_reply_keyboard(message.from_user.id, submodule, topic))
        return
    await state.update_data(code=message.text)
    data = await state.get_data()
    code_path = f'{submodule}.{topic}.{data["code"]}'

    # А теперь получаем код с учетом настроек пользователя
    module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')
    settings = await get_user_settings(message.from_user.id)
    dict_name = 'themes_list_dicts_full' if settings.get('show_docstring', True) else 'themes_list_dicts_full_nd'
    code_dictionary = getattr(module, dict_name)
    repl = code_dictionary[topic][data["code"]]

    await message.answer(f'Ваш запрос: \n{submodule} \n{topic} \n{data["code"]}', reply_markup=ReplyKeyboardRemove())
    
    if len(repl) > 4096:
        await message.answer('Сообщение будет отправлено в нескольких частях')
        for x in range(0, len(repl), 4096):
            await message.answer(f'''```python\n{repl[x:x+4096]}\n```''', parse_mode='markdown')
    else:
        await message.answer(f'''```python\n{repl}\n```''', parse_mode='markdown')
    
    await message.answer("Что делаем дальше?", reply_markup=kb.get_code_action_keyboard(code_path))
    await message.answer("Или выберите другую команду.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
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
    
    await message.answer("Обновление завершено. Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
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
    # """Handles the /execute command, admin-only."""
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
async def process_execution_from_user(message: Message, state: FSMContext):
    """Executes the received Python code and sends back the output, including images and rich display objects."""
    await state.clear()
    await _execute_code_and_send_results(message, message.text)

async def _execute_code_and_send_results(message: Message, code_to_execute: str):
    """Helper function to execute code and send results back to the user."""
    output_capture = io.StringIO()
    execution_error = None
    temp_dir = None
    original_cwd = os.getcwd()
    rich_outputs = []
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
# SEARCH & FAVORITES
##################################################################################################

async def get_search_results_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup | None:
    """Создает инлайн-клавиатуру для страницы результатов поиска с пагинацией."""
    search_data = user_search_results_cache.get(user_id)
    if not search_data or not search_data.get('results'):
        return None

    results = search_data['results']
    builder = InlineKeyboardBuilder()
    
    start = page * SEARCH_RESULTS_PER_PAGE
    end = start + SEARCH_RESULTS_PER_PAGE
    page_items = results[start:end]

    for i, result in enumerate(page_items):
        global_index = start + i
        builder.row(InlineKeyboardButton(
            text=f"▶️ {result['path']}", 
            callback_data=f"show_search_idx:{global_index}"
        ))

    # Pagination controls
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"search_page:{page - 1}"))
        
        pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))

        if end < len(results):
            pagination_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"search_page:{page + 1}"))
        
        builder.row(*pagination_buttons)

    return builder.as_markup()

async def perform_full_text_search(query: str) -> list[dict]:
    """
    Выполняет полнотекстовый поиск по всем примерам кода в matplobblib.
    Ищет в названиях подмодулей, тем, кода и в содержимом кода.
    """
    query = query.lower()
    found_items = []
    found_paths = set() # Для избежания дубликатов

    for submodule_name in matplobblib.submodules:
        try:
            module = matplobblib._importlib.import_module(f'matplobblib.{submodule_name}')
            # Ищем в полном словаре (с docstrings) для получения большего контекста
            code_dictionary = module.themes_list_dicts_full 
            
            for topic_name, codes in code_dictionary.items():
                for code_name, code_content in codes.items():
                    code_path = f"{submodule_name}.{topic_name}.{code_name}"
                    
                    if code_path in found_paths:
                        continue

                    # Создаем текстовый корпус для поиска
                    search_corpus = f"{submodule_name} {topic_name} {code_name} {code_content}".lower()
                    
                    if query in search_corpus:
                        found_items.append({
                            'path': code_path,
                            'name': code_name
                        })
                        found_paths.add(code_path)

        except Exception as e:
            logging.error(f"Ошибка при поиске в подмодуле {submodule_name}: {e}")
    
    return found_items

@router.message(Command('search'))
async def search_command(message: Message, state: FSMContext):
    await state.set_state(Search.query)
    await message.answer("Введите ключевые слова для поиска по примерам кода:", reply_markup=ReplyKeyboardRemove())

@router.message(Search.query)
async def process_search_query(message: Message, state: FSMContext):
    await state.clear()
    query = message.text
    status_msg = await message.answer(f"Идет поиск по запросу '{query}'...")
    results = await perform_full_text_search(query)

    if not results:
        await status_msg.edit_text(
            f"По вашему запросу '{query}' ничего не найдено.\n"
            "Попробуйте другие ключевые слова или воспользуйтесь командой /ask для пошагового выбора."
        )
        # Отправляем основную клавиатуру отдельным сообщением, так как edit_text не может ее использовать
        await message.answer("Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))
        return

    # Store query and results in cache for this user
    user_id = message.from_user.id
    user_search_results_cache[user_id] = {'query': query, 'results': results}

    keyboard = await get_search_results_keyboard(user_id, page=0)
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    await status_msg.edit_text(
        f"Найдено {len(results)} примеров по запросу '{query}'. Страница 1/{total_pages}:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("search_page:"))
async def cq_search_pagination(callback: CallbackQuery):
    """Обрабатывает нажатия на кнопки пагинации в результатах поиска."""
    user_id = callback.from_user.id
    search_data = user_search_results_cache.get(user_id)
    if not search_data:
        await callback.answer("Результаты поиска устарели. Пожалуйста, выполните поиск заново.", show_alert=True)
        await callback.message.delete()
        return

    page = int(callback.data.split(":", 1)[1])
    keyboard = await get_search_results_keyboard(user_id, page=page)
    
    results = search_data['results']
    query = search_data['query']
    total_pages = (len(results) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    await callback.message.edit_text(
        f"Найдено {len(results)} примеров по запросу '{query}'. Страница {page + 1}/{total_pages}:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.message(Command('favorites'))
async def favorites_command(message: Message):
    user_id = message.from_user.id
    favs = await database.get_favorites(user_id)
    if not favs:
        await message.answer("У вас пока нет избранных примеров. Вы можете добавить их, нажав на кнопку '⭐ В избранное' под примером кода.", reply_markup=kb.get_main_reply_keyboard(user_id))
        return

    builder = InlineKeyboardBuilder()
    for code_path in favs:
        path_hash = hashlib.sha1(code_path.encode()).hexdigest()[:16]
        kb.code_path_cache[path_hash] = code_path
        builder.row(
            InlineKeyboardButton(text=f"📄 {code_path}", callback_data=f"show_fav_hash:{path_hash}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"fav_del_hash:{path_hash}")
        )
    
    await message.answer("Ваши избранные примеры:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("fav_hash:"))
async def cq_add_favorite(callback: CallbackQuery):
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer("Ошибка: информация о коде устарела. Пожалуйста, запросите код заново.", show_alert=True)
        return

    success = await database.add_favorite(callback.from_user.id, code_path)
    if success:
        await callback.answer("✅ Добавлено в избранное!", show_alert=False)
    else:
        await callback.answer("Уже в избранном.", show_alert=False)

@router.callback_query(F.data.startswith("fav_del_hash:"))
async def cq_delete_favorite(callback: CallbackQuery):
    """Обрабатывает удаление примера из избранного."""
    user_id = callback.from_user.id
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)

    if not code_path:
        await callback.answer("Ошибка: информация об избранном устарела. Пожалуйста, вызовите /favorites снова.", show_alert=True)
        return

    # Удаляем из БД
    await database.remove_favorite(user_id, code_path)
    await callback.answer("Пример удален из избранного.", show_alert=False)

    # Обновляем сообщение со списком избранного
    favs = await database.get_favorites(user_id)
    if not favs:
        await callback.message.edit_text("Ваш список избранного пуст.")
        return

    # Пересобираем клавиатуру
    builder = InlineKeyboardBuilder()
    for new_code_path in favs:
        new_path_hash = hashlib.sha1(new_code_path.encode()).hexdigest()[:16]
        kb.code_path_cache[new_path_hash] = new_code_path
        builder.row(
            InlineKeyboardButton(text=f"📄 {new_code_path}", callback_data=f"show_fav_hash:{new_path_hash}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"fav_del_hash:{new_path_hash}")
        )
    
    try:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    except TelegramBadRequest as e:
        if "message is not modified" not in e.message:
            logging.error(f"Ошибка при обновлении клавиатуры избранного: {e}")
            raise

@router.callback_query(F.data == "noop")
async def cq_noop(callback: CallbackQuery):
    """Пустой обработчик для кнопок, которые не должны ничего делать (например, счетчик страниц)."""
    await callback.answer()

async def _show_code_by_path(message: Message, code_path: str, header: str):
    """Helper function to send code to the user based on its path."""
    try:
        submodule, topic, code_name = code_path.split('.')
        
        module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')

        # Определяем, показывать ли docstring, на основе настроек пользователя
        settings = await get_user_settings(message.from_user.id)
        dict_name = 'themes_list_dicts_full' if settings.get('show_docstring', True) else 'themes_list_dicts_full_nd'
        code_dictionary = getattr(module, dict_name)

        repl = code_dictionary[topic][code_name]

        await message.answer(f'{header}: \n{code_path.replace(".", " -> ")}')
        
        if len(repl) > 4096:
            await message.answer('Сообщение будет отправлено в нескольких частях')
            for x in range(0, len(repl), 4096):
                await message.answer(f'''```python\n{repl[x:x+4096]}\n```''', parse_mode='markdown')
        else:
            await message.answer(f'''```python\n{repl}\n```''', parse_mode='markdown')
        
        await message.answer("Что делаем дальше?", reply_markup=kb.get_code_action_keyboard(code_path))
        await message.answer("Или выберите другую команду.", reply_markup=kb.get_main_reply_keyboard(message.from_user.id))

    except (ValueError, KeyError, AttributeError, ImportError) as e:
        logging.error(f"Ошибка при показе кода (path: {code_path}): {e}")
        await message.answer("Не удалось найти или отобразить этот пример кода. Возможно, он был удален или перемещен.")

@router.callback_query(F.data.startswith("show_search_idx:"))
async def cq_show_search_result_by_index(callback: CallbackQuery):
    """Handles clicks on search result buttons."""
    user_id = callback.from_user.id
    search_data = user_search_results_cache.get(user_id)
    if not search_data:
        await callback.answer("Результаты поиска устарели. Пожалуйста, выполните поиск заново.", show_alert=True)
        return

    try:
        index = int(callback.data.split(":", 1)[1])
        results = search_data['results']
        
        if not (0 <= index < len(results)):
            raise IndexError("Search result index out of bounds.")

        code_path = results[index]['path']
        
        await callback.answer() # Acknowledge the callback
        await _show_code_by_path(callback.message, code_path, "Результат поиска")

    except (ValueError, IndexError) as e:
        logging.warning(f"Invalid search index from user {user_id}. Data: {callback.data}. Error: {e}")
        await callback.answer("Неверный результат поиска. Возможно, он устарел.", show_alert=True)
    except Exception as e:
        logging.error(f"Error showing search result by index for user {user_id}: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при отображении результата.", show_alert=True)

@router.callback_query(F.data.startswith("show_fav_hash:"))
async def cq_show_favorite(callback: CallbackQuery):
    """Handles clicks on favorite item buttons."""
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer("Ошибка: информация об избранном устарела. Пожалуйста, вызовите /favorites снова.", show_alert=True)
        return

    await callback.answer()
    await _show_code_by_path(callback.message, code_path, "Избранное")

@router.callback_query(F.data.startswith("run_hash:"))
async def cq_run_code_from_lib(callback: CallbackQuery):
    path_hash = callback.data.split(":", 1)[1]
    code_path = kb.code_path_cache.get(path_hash)
    if not code_path:
        await callback.answer("Ошибка: информация о коде устарела. Пожалуйста, запросите код заново.", show_alert=True)
        return

    submodule, topic, code_name = code_path.split('.')
    
    module = matplobblib._importlib.import_module(f'matplobblib.{submodule}')
    code_to_run = module.themes_list_dicts_full_nd[topic][code_name] # Берем код без docstring для корректного выполнения

    await callback.answer("▶️ Запускаю пример...")
    await _execute_code_and_send_results(callback.message, code_to_run)
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

@router.callback_query(F.data == "help_cmd_search")
async def cq_help_cmd_search(callback: CallbackQuery, state: FSMContext):
    """Handler for '/search' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /search
    await state.set_state(Search.query)
    await callback.message.answer("Введите ключевые слова для поиска по примерам кода:", reply_markup=ReplyKeyboardRemove())

@router.callback_query(F.data == "help_cmd_favorites")
async def cq_help_cmd_favorites(callback: CallbackQuery):
    """Handler for '/favorites' button from help menu."""
    await callback.answer()
    # Повторяем логику команды /favorites
    # favorites_command ожидает объект Message, callback.message подходит
    await favorites_command(callback.message)

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
    await callback.message.answer("Обновление завершено. Выберите следующую команду:", reply_markup=kb.get_main_reply_keyboard(callback.from_user.id))

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