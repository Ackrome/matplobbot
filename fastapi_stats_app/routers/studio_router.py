from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
import asyncio
import logging
import io
import zipfile
import base64

from shared_lib.tasks import compile_project_task, render_pdf_task, render_mermaid, compile_full_latex_task
from shared_lib.database import get_db_session_dependency
from shared_lib.models import Project, ProjectFile
from ..auth import get_current_user

router = APIRouter(prefix="/studio", tags=["studio"])
logger = logging.getLogger(__name__)

class ProjectCreate(BaseModel):
    name: str
    project_type: str = "latex"

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


class CompileRequest(BaseModel):
    type: str     # 'latex', 'markdown', 'mermaid'
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
            task = render_pdf_task.delay(req.content, "Document", current_user['username'], "Today")
        elif req.type == "mermaid":
            # Используем существующий рендерер Mermaid -> PNG
            task = render_mermaid.delay(req.content)
        else:
            raise HTTPException(status_code=400, detail="Unknown document type")

        # Ждем выполнения задачи в фоне
        result = await asyncio.to_thread(task.get, timeout=55)

        if result.get('status') == 'error':
            raise HTTPException(status_code=400, detail=result.get('error', 'Unknown compilation error'))

        return result

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Compilation timed out.")
    except Exception as e:
        logger.error(f"Studio Compile Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/projects")
async def get_projects(db: AsyncSession = Depends(get_db_session_dependency), current_user: dict = Depends(get_current_user)):
    result = await db.execute(select(Project).where(Project.owner_id == current_user['id']).order_by(Project.updated_at.desc()))
    projects = result.scalars().all()
    return[{"id": p.id, "name": p.name, "type": p.project_type} for p in projects]

@router.post("/projects")
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db_session_dependency), current_user: dict = Depends(get_current_user)):
    new_proj = Project(owner_id=current_user['id'], name=data.name, project_type=data.project_type)
    db.add(new_proj)
    await db.flush() # Получаем ID

    # Создаем дефолтный файл
    main_file = ProjectFile(
        project_id=new_proj.id, 
        file_path="main.tex" if data.project_type == 'latex' else "main.md",
        content_text=DEFAULT_LATEX if data.project_type == 'latex' else "# Hello",
        is_main=True
    )
    db.add(main_file)
    await db.commit()
    return {"id": new_proj.id, "name": new_proj.name}

@router.get("/projects/{project_id}")
async def get_project_files(project_id: int, db: AsyncSession = Depends(get_db_session_dependency), current_user: dict = Depends(get_current_user)):
    # Проверка прав (в идеале нужно всегда проверять owner_id)
    result = await db.execute(select(ProjectFile).where(ProjectFile.project_id == project_id).order_by(ProjectFile.file_path))
    files = result.scalars().all()
    
    return[{
        "id": f.id, 
        "path": f.file_path, 
        "is_main": f.is_main, 
        "is_binary": f.content_binary is not None,
        "content": f.content_text
    } for f in files]

@router.put("/projects/{project_id}/files/{file_id}")
async def save_file(project_id: int, file_id: int, data: FileSave, db: AsyncSession = Depends(get_db_session_dependency), current_user: dict = Depends(get_current_user)):
    await db.execute(update(ProjectFile).where(ProjectFile.id == file_id).values(content_text=data.content))
    await db.commit()
    return {"status": "success"}

@router.post("/projects/{project_id}/upload")
async def upload_asset(project_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db_session_dependency), current_user: dict = Depends(get_current_user)):
    content = await file.read()
    if len(content) > 5 * 1024 * 1024: # Лимит 5 МБ
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    stmt = pg_insert(ProjectFile).values(
        project_id=project_id,
        file_path=file.filename,
        content_binary=content,
        is_main=False
    ).on_conflict_do_update(
        constraint='uq_project_file_path',
        set_=dict(content_binary=content)
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "success", "filename": file.filename}

@router.post("/projects/{project_id}/compile")
async def compile_project(project_id: int, db: AsyncSession = Depends(get_db_session_dependency), current_user: dict = Depends(get_current_user)):
    # 1. Извлекаем все файлы проекта
    result = await db.execute(select(ProjectFile).where(ProjectFile.project_id == project_id))
    files = result.scalars().all()

    if not files:
        raise HTTPException(status_code=400, detail="Project is empty")

    # 2. Формируем Payload для Celery
    payload =[]
    main_file_path = "main.tex"
    
    for f in files:
        if f.is_main:
            main_file_path = f.file_path
            
        file_data = {"path": f.file_path}
        if f.content_binary:
            file_data["binary"] = base64.b64encode(f.content_binary).decode('utf-8')
        else:
            file_data["text"] = f.content_text or ""
        payload.append(file_data)

    try:
        # 3. Отправляем в Celery
        task = compile_project_task.delay(payload, main_file_path)
        # Ждем результат (в MVP синхронно)
        res = await asyncio.to_thread(task.get, timeout=55)

        if res.get('status') == 'error':
            raise HTTPException(status_code=400, detail=res.get('error', 'Compilation error'))

        return res

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Compilation timed out.")
    
    
    
@router.delete("/projects/{project_id}/files/{file_id}")
async def delete_file(project_id: int, file_id: int, db: AsyncSession = Depends(get_db_session_dependency), current_user: dict = Depends(get_current_user)):
    # Проверяем, не является ли файл главным (main.tex)
    result = await db.execute(select(ProjectFile).where(ProjectFile.id == file_id, ProjectFile.project_id == project_id))
    file_obj = result.scalar_one_or_none()
    
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    if file_obj.is_main:
        raise HTTPException(status_code=400, detail="Cannot delete the main project file")

    await db.execute(delete(ProjectFile).where(ProjectFile.id == file_id))
    await db.commit()
    return {"status": "success"}

@router.put("/projects/{project_id}/files/{file_id}/rename")
async def rename_file(project_id: int, file_id: int, data: FileRename, db: AsyncSession = Depends(get_db_session_dependency), current_user: dict = Depends(get_current_user)):
    if not data.new_name.strip():
        raise HTTPException(status_code=400, detail="Filename cannot be empty")
        
    try:
        await db.execute(
            update(ProjectFile)
            .where(ProjectFile.id == file_id, ProjectFile.project_id == project_id)
            .values(file_path=data.new_name.strip())
        )
        await db.commit()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Filename might already exist or invalid")

@router.get("/projects/{project_id}/export/zip")
async def export_project_zip(project_id: int, db: AsyncSession = Depends(get_db_session_dependency), current_user: dict = Depends(get_current_user)):
    # 1. Получаем проект и файлы
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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