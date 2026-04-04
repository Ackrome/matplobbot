import asyncio
import base64
import io
import logging
import mimetypes
import os
import zipfile

import aiohttp
from aiohttp_socks import ProxyConnector
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database import get_db_session_dependency
from shared_lib.models import Project, ProjectFile
from shared_lib.tasks import (
    compile_full_latex_task,
    compile_project_task,
    render_mermaid,
    render_pdf_task,
)

from ..auth import get_current_user

router = APIRouter(prefix="/studio", tags=["studio"])
logger = logging.getLogger(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN")


async def get_owned_project_or_404(db: AsyncSession, project_id: int, owner_id: int) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


class ProjectCreate(BaseModel):
    name: str
    project_type: str = "latex"
    template_id: str = "latex_blank"


class FileSave(BaseModel):
    content: str


class FileRename(BaseModel):
    new_name: str


DEFAULT_LATEX = r"""\documentclass[12pt, a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T2A]{fontenc}
\usepackage[russian]{babel}
\usepackage{amsmath, amssymb, graphicx}

\begin{document}
\section{Новый проект}
Ваш текст здесь. Вы можете загружать картинки слева и вставлять их через \verb|\includegraphics{image.png}|.
\end{document}
"""

DEFAULT_TEMPLATES = {
    "latex_blank": (
        "main.tex",
        "\\documentclass[12pt, a4paper]{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage[T2A]{fontenc}\n\\usepackage[russian]{babel}\n\\usepackage{amsmath, amssymb, graphicx}\n\n\\begin{document}\n\\section{Новый проект}\nВаш текст здесь.\n\\end{document}",
    ),
    "latex_beamer": (
        "main.tex",
        "\\documentclass{beamer}\n\\usepackage[utf8]{inputenc}\n\\usepackage[T2A]{fontenc}\n\\usepackage[russian]{babel}\n\n\\usetheme{Madrid}\n\n\\title{Моя Презентация}\n\\author{Студент}\n\\date{\\today}\n\n\\begin{document}\n\\frame{\\titlepage}\n\n\\begin{frame}{Первый слайд}\n\\begin{itemize}\n\\item Пункт 1\n\\item Пункт 2\n\\end{itemize}\n\\end{frame}\n\\end{document}",
    ),
    "latex_report": (
        "main.tex",
        "\\documentclass[14pt, a4paper]{extreport}\n\\usepackage[utf8]{inputenc}\n\\usepackage[T2A]{fontenc}\n\\usepackage[russian]{babel}\n\\usepackage[left=3cm,right=1.5cm,top=2cm,bottom=2cm]{geometry}\n\n\\begin{document}\n\\tableofcontents\n\\chapter{Введение}\nТекст введения по ГОСТ...\n\\end{document}",
    ),
    "markdown": (
        "main.md",
        "# Заголовок\n\nТекст с формулой: $$E = mc^2$$\n\n`![Описание](image.png)`",
    ),
    "mermaid": (
        "main.mmd",
        "graph TD;\n    A[Начало] --> B{Работает?};\n    B -- Да --> C[Отлично!];\n    B -- Нет --> D[Ищем баг];",
    ),
}


class CompileRequest(BaseModel):
    type: str  # 'latex', 'markdown', 'mermaid'
    content: str  # Исходный код


@router.post("/compile")
async def compile_document(req: CompileRequest, current_user: dict = Depends(get_current_user)):
    """
    Отправляет документ на компиляцию в Celery и дожидается результата.
    Для Фазы 1 реализовано синхронное ожидание (до 60 сек).
    """
    try:
        if req.type == "latex":
            task = compile_full_latex_task.delay(req.content)
        elif req.type == "markdown":
            # Используем существующий рендерер Markdown -> PDF
            task = render_pdf_task.delay(req.content, "Document", current_user["username"], "Today")
        elif req.type == "mermaid":
            # Используем существующий рендерер Mermaid -> PNG
            task = render_mermaid.delay(req.content)
        else:
            raise HTTPException(status_code=400, detail="Unknown document type")

        # Ждем выполнения задачи в фоне
        result = await asyncio.to_thread(task.get, timeout=55)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=400, detail=result.get("error", "Unknown compilation error")
            )

        return result

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Compilation timed out.")
    except Exception as e:
        logger.error(f"Studio Compile Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects")
async def get_projects(
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(Project)
        .where(Project.owner_id == current_user["id"])
        .order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()
    return [{"id": p.id, "name": p.name, "type": p.project_type} for p in projects]


@router.post("/projects")
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    new_proj = Project(owner_id=current_user["id"], name=data.name, project_type=data.project_type)
    db.add(new_proj)
    await db.flush()

    # Выбираем шаблон (если шаблон не найден, берем blank)
    file_path, content_text = DEFAULT_TEMPLATES.get(
        data.template_id, DEFAULT_TEMPLATES["latex_blank"]
    )

    main_file = ProjectFile(
        project_id=new_proj.id, file_path=file_path, content_text=content_text, is_main=True
    )
    db.add(main_file)
    await db.commit()
    return {"id": new_proj.id, "name": new_proj.name, "type": new_proj.project_type}


@router.get("/projects/{project_id}")
async def get_project_files(
    project_id: int,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    # Проверка прав (в идеале нужно всегда проверять owner_id)
    await get_owned_project_or_404(db, project_id, current_user["id"])
    result = await db.execute(
        select(ProjectFile)
        .where(ProjectFile.project_id == project_id)
        .order_by(ProjectFile.file_path)
    )
    files = result.scalars().all()

    return [
        {
            "id": f.id,
            "path": f.file_path,
            "is_main": f.is_main,
            "is_binary": f.content_binary is not None,
            "content": f.content_text,
        }
        for f in files
    ]


@router.put("/projects/{project_id}/files/{file_id}")
async def save_file(
    project_id: int,
    file_id: int,
    data: FileSave,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    await get_owned_project_or_404(db, project_id, current_user["id"])
    result = await db.execute(
        update(ProjectFile)
        .where(ProjectFile.id == file_id, ProjectFile.project_id == project_id)
        .values(content_text=data.content)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="File not found")
    await db.commit()
    return {"status": "success"}


@router.post("/projects/{project_id}/upload")
async def upload_asset(
    project_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    await get_owned_project_or_404(db, project_id, current_user["id"])
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # Лимит 5 МБ
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    stmt = (
        pg_insert(ProjectFile)
        .values(
            project_id=project_id, file_path=file.filename, content_binary=content, is_main=False
        )
        .on_conflict_do_update(constraint="uq_project_file_path", set_=dict(content_binary=content))
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "success", "filename": file.filename}


@router.post("/projects/{project_id}/compile")
async def compile_project(
    project_id: int,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    # Получаем проект, чтобы достать старый кэш
    project = await get_owned_project_or_404(db, project_id, current_user["id"])

    build_cache_b64 = (
        base64.b64encode(project.build_cache).decode("utf-8") if project.build_cache else None
    )

    # Извлекаем все файлы проекта
    result = await db.execute(select(ProjectFile).where(ProjectFile.project_id == project_id))
    files = result.scalars().all()

    if not files:
        raise HTTPException(status_code=400, detail="Project is empty")

    payload = []
    main_file_path = "main.tex"

    for f in files:
        if f.is_main:
            main_file_path = f.file_path

        file_data = {"path": f.file_path}
        if f.content_binary:
            file_data["binary"] = base64.b64encode(f.content_binary).decode("utf-8")
        else:
            file_data["text"] = f.content_text or ""
        payload.append(file_data)

    try:
        # Передаем build_cache в Celery
        task = compile_project_task.delay(payload, main_file_path, build_cache_b64)
        res = await asyncio.to_thread(task.get, timeout=55)

        # Если воркер вернул новый кэш - сохраняем его в БД
        if res.get("build_cache"):
            project.build_cache = base64.b64decode(res["build_cache"])
            await db.commit()

        if res.get("status") == "error":
            raise HTTPException(status_code=400, detail=res.get("error", "Compilation error"))

        return res

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Compilation timed out.")


@router.delete("/projects/{project_id}/files/{file_id}")
async def delete_file(
    project_id: int,
    file_id: int,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    # Проверяем, не является ли файл главным (main.tex)
    await get_owned_project_or_404(db, project_id, current_user["id"])
    result = await db.execute(
        select(ProjectFile).where(ProjectFile.id == file_id, ProjectFile.project_id == project_id)
    )
    file_obj = result.scalar_one_or_none()

    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    if file_obj.is_main:
        raise HTTPException(status_code=400, detail="Cannot delete the main project file")

    await db.execute(
        delete(ProjectFile).where(ProjectFile.id == file_id, ProjectFile.project_id == project_id)
    )
    await db.commit()
    return {"status": "success"}


@router.put("/projects/{project_id}/files/{file_id}/rename")
async def rename_file(
    project_id: int,
    file_id: int,
    data: FileRename,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    await get_owned_project_or_404(db, project_id, current_user["id"])
    if not data.new_name.strip():
        raise HTTPException(status_code=400, detail="Filename cannot be empty")

    try:
        result = await db.execute(
            update(ProjectFile)
            .where(ProjectFile.id == file_id, ProjectFile.project_id == project_id)
            .values(file_path=data.new_name.strip())
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="File not found")
        await db.commit()
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Filename might already exist or invalid")


@router.get("/projects/{project_id}/export/zip")
async def export_project_zip(
    project_id: int,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    # 1. Получаем проект и файлы
    project = await get_owned_project_or_404(db, project_id, current_user["id"])

    files_result = await db.execute(select(ProjectFile).where(ProjectFile.project_id == project_id))
    files = files_result.scalars().all()

    # 2. Создаем ZIP архив в памяти
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for f in files:
            if f.content_binary:
                zip_file.writestr(f.file_path, f.content_binary)
            else:
                zip_file.writestr(f.file_path, f.content_text or "")

    zip_buffer.seek(0)

    safe_name = "".join([c if c.isalnum() else "_" for c in project.name])
    headers = {"Content-Disposition": f"attachment; filename={safe_name}_export.zip"}

    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)


# --- Эндпоинт для локальных картинок в Markdown ---
@router.get("/projects/{project_id}/assets/{file_path:path}")
async def get_project_asset(
    project_id: int,
    file_path: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db_session_dependency),
):
    # Верификация токена вручную, т.к. img src не поддерживает заголовки
    try:
        user = await get_current_user(token, db)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid token")
    await get_owned_project_or_404(db, project_id, user["id"])

    result = await db.execute(
        select(ProjectFile).where(
            ProjectFile.project_id == project_id, ProjectFile.file_path == file_path
        )
    )
    file_obj = result.scalar_one_or_none()

    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")

    content = (
        file_obj.content_binary
        if file_obj.content_binary
        else (file_obj.content_text.encode("utf-8") if file_obj.content_text else b"")
    )
    mime_type, _ = mimetypes.guess_type(file_path)

    return Response(content=content, media_type=mime_type or "application/octet-stream")


@router.post("/projects/{project_id}/send_telegram")
async def send_project_to_telegram(
    project_id: int,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: dict = Depends(get_current_user),
):
    # 1. Проверяем, привязан ли Telegram
    telegram_id = current_user["db_obj"].telegram_id
    if not telegram_id:
        raise HTTPException(
            status_code=400, detail="Аккаунт Telegram не привязан. Войдите через Telegram."
        )

    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN не настроен на сервере.")

    # 2. Получаем проект и собираем его (компилируем)
    project = await get_owned_project_or_404(db, project_id, current_user["id"])

    build_cache_b64 = (
        base64.b64encode(project.build_cache).decode("utf-8") if project.build_cache else None
    )

    files_result = await db.execute(select(ProjectFile).where(ProjectFile.project_id == project_id))
    files = files_result.scalars().all()

    payload = []
    main_file_path = "main.tex"
    for f in files:
        if f.is_main:
            main_file_path = f.file_path
        file_data = {"path": f.file_path}
        if f.content_binary:
            file_data["binary"] = base64.b64encode(f.content_binary).decode("utf-8")
        else:
            file_data["text"] = f.content_text or ""
        payload.append(file_data)

    # Запускаем сборку
    task = compile_project_task.delay(payload, main_file_path, build_cache_b64)
    res = await asyncio.to_thread(task.get, timeout=55)

    if res.get("status") == "error" or not res.get("pdf"):
        raise HTTPException(
            status_code=400, detail="Ошибка компиляции. Исправьте ошибки перед отправкой."
        )

    # 3. Подготовка полей для Telegram
    pdf_bytes = base64.b64decode(res["pdf"])
    safe_name = "".join([c if c.isalnum() or c in " -_" else "_" for c in project.name])

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

    # ИСПРАВЛЕНИЕ: parse_mode добавляем как отдельное поле, а не аргумент add_field
    form_data = aiohttp.FormData()
    form_data.add_field("chat_id", str(telegram_id))
    form_data.add_field(
        "document", pdf_bytes, filename=f"{safe_name}.pdf", content_type="application/pdf"
    )
    form_data.add_field("caption", f"📄 Ваш проект: <b>{project.name}</b>")
    form_data.add_field("parse_mode", "HTML")

    PROXY_URL = os.getenv("PROXY_URL")

    # Настраиваем коннектор для SOCKS5 если нужно
    connector = None
    if PROXY_URL and PROXY_URL.startswith("socks"):
        connector = ProxyConnector.from_url(PROXY_URL)

    try:
        # Если прокси SOCKS, используем connector. Если HTTP, можно через параметр proxy.
        # Для универсальности лучше использовать connector
        async with aiohttp.ClientSession(connector=connector) as session:
            # Если прокси HTTP, aiohttp_socks сам это поймет.
            # Если прокси нет, connector будет None и aiohttp сработает напрямую.
            post_kwargs = {"data": form_data, "timeout": 60}

            # Если это обычный HTTP прокси, а не SOCKS:
            if PROXY_URL and not PROXY_URL.startswith("socks"):
                post_kwargs["proxy"] = PROXY_URL

            async with session.post(url, **post_kwargs) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    logger.error(f"Telegram API Error: {err_text}")
                    raise HTTPException(
                        status_code=500, detail="Ошибка при отправке файла в Telegram."
                    )
    except Exception as e:
        logger.error(f"Network error during Telegram send: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сети: {str(e)}")

    return {"status": "success", "message": "Файл успешно отправлен в Telegram!"}
