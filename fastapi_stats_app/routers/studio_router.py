from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import asyncio
import logging

from shared_lib.tasks import compile_full_latex_task, render_pdf_task, render_mermaid
from ..auth import get_current_user

router = APIRouter(prefix="/studio", tags=["studio"])
logger = logging.getLogger(__name__)

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