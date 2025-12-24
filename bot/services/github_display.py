import tempfile
import re
import os
import hashlib
from urllib.parse import quote
import aiohttp
import aiofiles
from aiogram.types import Message, FSInputFile, BufferedInputFile, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

from .. import database, keyboards as kb, github_service
from . import document_renderer
from shared_lib.i18n import translator


logger = logging.getLogger(__name__)

async def send_as_plain_text(message: Message, user_id: int, file_path: str, content: str):
    """Helper to send content as plain text, handling long messages."""
    lang = await translator.get_language(user_id, message.chat.id)
    header = translator.gettext(lang, "github_file_header_plain", file_path=file_path) + "\n\n"
    
    await message.answer(header, parse_mode='markdown')
    
    if len(content) == 0:
        await message.answer(translator.gettext(lang, "github_file_empty"), parse_mode='markdown')
        return

    # Send content in chunks
    for x in range(0, len(content), 4000): 
        chunk = content[x:x+4000]
        # Attach main keyboard to the last chunk
        markup = None
        if x + 4000 >= len(content):
             markup = await kb.get_main_reply_keyboard(user_id)
             
        await message.answer(f"```\n{chunk}\n```", parse_mode='markdown', reply_markup=markup)

async def send_as_document_from_url(message: Message, user_id: int, file_url: str, file_path: str):
    """Downloads a file from a URL by chunks and sends it as a document."""
    lang = await translator.get_language(user_id, message.chat.id)
    file_name = os.path.basename(file_path)
    status_msg = await message.answer(translator.gettext(lang, "github_downloading_file", file_name=file_name), parse_mode='markdown')
    
    temp_file_path = None
    try:
        # Create a temporary file to store the download
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as tmp_file:
            temp_file_path = tmp_file.name

        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                response.raise_for_status() 
                
                async with aiofiles.open(temp_file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
        
        # Send the downloaded file with the main keyboard
        await message.answer_document(
            document=FSInputFile(temp_file_path, filename=file_name),
            caption=translator.gettext(lang, "github_file_caption", file_path=file_path),
            parse_mode='markdown',
            reply_markup=await kb.get_main_reply_keyboard(user_id)
        )
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Failed to download/send file from {file_url}: {e}", exc_info=True)
        await status_msg.edit_text(translator.gettext(lang, "github_download_error", file_name=file_name, error=e))
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

async def _resolve_wikilinks(content: str, repo_path: str, all_repo_files: list[str], target_format: str = 'md') -> str:
    """Resolves [[wikilinks]] to standard Markdown links."""
    if not all_repo_files or '[[' not in content:
        return content

    file_map = {os.path.splitext(os.path.basename(f))[0].lower(): f for f in all_repo_files}

    def replace_wikilink(match):
        inner_content = match.group(1).strip()
        parts = inner_content.split('|', 1)
        file_name_part = parts[0].strip()
        display_text = parts[1].strip() if len(parts) > 1 else file_name_part
        found_path = file_map.get(file_name_part.lower())

        if found_path:
            url = f"https://github.com/{repo_path}/blob/{github_service.MD_SEARCH_BRANCH}/{quote(found_path)}"
            return f"[{display_text}]({url})"
        else:
            return f"_{display_text}_"

    wikilink_regex = r"\[\[([^\]]+)\]\]"
    # Regex to skip math blocks when replacing links
    math_env_regex = r'(\$\$.*?\$\$|\$[^$\n]*?\$|\\\[.*?\\\]|\\\(.*?\\\)|\\begin\{(?:equation|align|gather|math|displaymath|matrix|pmatrix|array)[\*]?\}.*?\\end\{(?:equation|align|gather|math|displaymath|matrix|pmatrix|array)[\*]?\})'
    
    parts = re.split(math_env_regex, content, flags=re.DOTALL)

    processed_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            processed_parts.append(re.sub(wikilink_regex, replace_wikilink, part))
        else:
            processed_parts.append(part)

    return "".join(processed_parts)


async def display_github_file(message: Message, user_id: int, repo_path: str, file_path: str, status_msg_to_delete: Message | None = None):
    """Fetches a file from GitHub and displays it."""
    lang = await translator.get_language(user_id, message.chat.id)
    raw_url = f"https://raw.githubusercontent.com/{repo_path}/{github_service.MD_SEARCH_BRANCH}/{file_path}"

    if file_path.lower().endswith('.md'):
        content = github_service.github_content_cache.get(file_path)
        if content is not None:
            logger.info(f"Cache hit for file content: {file_path}")
        else:
            logger.info(f"Cache miss for file content: {file_path}. Fetching from GitHub.")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(raw_url) as response:
                        if response.status == 200:
                            content = await response.text(encoding='utf-8', errors='ignore')
                            github_service.github_content_cache[file_path] = content
                        else:
                            await message.answer(translator.gettext(lang, "github_fetch_error", status_code=response.status))
                            return
            except Exception as e:
                await message.answer(translator.gettext(lang, "github_fetch_exception", error=e))
                return

        if content is None:
            await message.answer(translator.gettext(lang, "github_content_error"))
            return

        settings = await database.get_user_settings(user_id)
        md_mode = settings.get('md_display_mode', 'md_file')
        
        await message.bot.send_chat_action(message.chat.id, "upload_document")
        main_kb = await kb.get_main_reply_keyboard(user_id)
        
        if md_mode == 'md_file':
            file_name = file_path.split('/')[-1]
            file_bytes = content.encode('utf-8')
            await message.answer_document(
                document=BufferedInputFile(file_bytes, filename=file_name),
                caption=translator.gettext(lang, "github_caption_md", file_path=file_path),
                parse_mode='markdown',
                reply_markup=main_kb
            )

        elif md_mode == 'pdf_file':
            try:
                page_title = file_path.split('/')[-1].replace('.md', '')
                file_name = f"{page_title}.pdf"

                async with aiohttp.ClientSession() as session:
                    all_repo_files = await github_service.get_all_repo_files_cached(repo_path, session)
                    resolved_content = await _resolve_wikilinks(content, repo_path, all_repo_files, target_format='latex')
                    contributors = await github_service.get_repo_contributors(repo_path, session)
                    last_modified_date = await github_service.get_file_last_modified_date(repo_path, file_path, session)
                    pdf_buffer = await document_renderer.convert_md_to_pdf_pandoc(resolved_content, page_title, contributors, last_modified_date)

                await message.answer_document(
                    document=BufferedInputFile(pdf_buffer.getvalue(), filename=file_name),
                    caption=translator.gettext(lang, "github_caption_pdf", file_path=file_path),
                    parse_mode='markdown',
                    reply_markup=main_kb
                )
            except Exception as e:
                logger.error(f"Ошибка при создании PDF для '{file_path}': {e}", exc_info=True)
                error_message = str(e)
                max_len = 3900 
                if len(error_message) > max_len:
                    truncated_error = error_message[:max_len] + "\n\n... (сообщение об ошибке было сокращено)"
                else:
                    truncated_error = error_message
                await message.answer(translator.gettext(lang, "github_pdf_error", error=truncated_error))
                await send_as_plain_text(message, user_id, file_path, content) 

        elif md_mode == 'html_file':
            try:
                page_title = file_path.split('/')[-1].replace('.md', '')
                async with aiohttp.ClientSession() as session:
                    all_repo_files = await github_service.get_all_repo_files_cached(repo_path, session)
                resolved_content = await _resolve_wikilinks(content, repo_path, all_repo_files, target_format='md')
                full_html_doc = await document_renderer._prepare_html_with_katex(resolved_content, page_title)

                file_bytes = full_html_doc.encode('utf-8')
                file_name = f"{page_title}.html"
                await message.answer_document(
                    document=BufferedInputFile(file_bytes, filename=file_name),
                    caption=translator.gettext(lang, "github_caption_html", file_path=file_path),
                    parse_mode='markdown',
                    reply_markup=main_kb
                )
            except Exception as e:
                logger.error(f"Ошибка при создании HTML-файла с KaTeX для '{file_path}': {e}", exc_info=True)
                await message.answer(translator.gettext(lang, "github_html_error", error=e))
                await send_as_plain_text(message, user_id, file_path, content) 
        
        else:
            logger.warning(f"Unknown md_display_mode '{md_mode}' for user {user_id}. Falling back to plain text.")
            await send_as_plain_text(message, user_id, file_path, content)
    else:
        await send_as_document_from_url(message, user_id, raw_url, file_path)
    
    if status_msg_to_delete:
        try:
            await status_msg_to_delete.delete()
        except TelegramBadRequest:
            pass 

async def display_lec_all_path(message: Message, repo_path: str, path: str, is_edit: bool = False, user_id: int | None = None):
    """Helper to fetch and display contents of a path in the lec_all repo."""
    effective_user_id = user_id or message.from_user.id
    lang = await translator.get_language(effective_user_id, message.chat.id)
    status_msg = None
    if is_edit:
        pass
    else:
        loading_key = "github_loading_contents" if path else "github_loading_root"
        status_msg = await message.answer(translator.gettext(lang, loading_key, path=path, repo_path=repo_path), parse_mode='markdown')

    contents = await github_service.get_github_repo_contents(repo_path, path)

    if contents is None:
        error_text = translator.gettext(lang, "github_repo_content_error")
        if status_msg:
            await status_msg.edit_text(error_text)
        elif is_edit:
            await message.edit_text(error_text, reply_markup=None)
        else:
            await message.answer(error_text)
        return

    builder = InlineKeyboardBuilder()

    if path:
        parent_dir = path.rsplit('/', 1) if '/' in path else ""
        parent_path = f"{repo_path}/{parent_dir}" if parent_dir else repo_path
        path_hash = hashlib.sha1(parent_path.encode()).hexdigest()[:16]
        kb.code_path_cache[path_hash] = parent_path
        builder.row(InlineKeyboardButton(text="⬅️ .. (Назад)", callback_data=f"abs_nav_hash:{path_hash}"))

    if isinstance(contents, list):
        for item in contents:
            if item['type'] == 'dir':
                full_item_path = f"{repo_path}/{item['path']}"
                path_hash = hashlib.sha1(full_item_path.encode()).hexdigest()[:16]
                kb.code_path_cache[path_hash] = full_item_path
                builder.row(InlineKeyboardButton(
                    text=f"📁 {item['name']}",
                    callback_data=f"abs_nav_hash:{path_hash}"
                ))
            elif item['type'] == 'file':
                full_item_path = f"{repo_path}/{item['path']}"
                path_hash = hashlib.sha1(full_item_path.encode()).hexdigest()[:16]
                kb.code_path_cache[path_hash] = full_item_path
                builder.row(InlineKeyboardButton(
                    text=f"📄 {item['name']}",
                    callback_data=f"abs_show_hash:{path_hash}"
                ))
    
    message_text = translator.gettext(lang, "github_repo_contents_of", path=path, repo_path=repo_path) if path else translator.gettext(lang, "github_repo_contents_of_root", repo_path=repo_path)
    
    if not contents and not path: 
        message_text = translator.gettext(lang, "github_repo_empty")
    elif not contents and path: 
        message_text = translator.gettext(lang, "github_folder_empty", path=path)

    reply_markup = builder.as_markup() if builder.buttons else None

    if is_edit:
        try:
            await message.edit_text(message_text, reply_markup=reply_markup, parse_mode='markdown')
        except TelegramBadRequest as e:
            if "message is not modified" not in e.message:
                raise
    elif status_msg:
        await status_msg.edit_text(message_text, reply_markup=reply_markup, parse_mode='markdown')
    else:
        await message.answer(message_text, reply_markup=reply_markup, parse_mode='markdown')