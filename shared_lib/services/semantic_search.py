import logging
import json
import re
from sqlalchemy import select, delete, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from shared_lib.database import get_session
from shared_lib.models import SearchDocument

logger = logging.getLogger(__name__)

class TextSearchEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TextSearchEngine, cls).__new__(cls)
        return cls._instance

    async def upsert_document(self, source_type: str, path: str, content: str, metadata: dict):
        """
        Вставляет документ для полнотекстового поиска (FTS).
        """
        async with get_session() as session:
            stmt = pg_insert(SearchDocument).values(
                source_type=source_type,
                source_path=path,
                content=content,
                metadata_=metadata # Используем алиас из модели
            ).on_conflict_do_update(
                constraint='uq_search_doc_path',
                set_=dict(
                    content=content,
                    metadata_=metadata,
                    created_at=func.now()
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def search(self, query: str, source_type: str = None, top_k: int = 10) -> list[dict]:
        """
        Выполняет быстрый полнотекстовый поиск (FTS) средствами PostgreSQL + SQLAlchemy.
        """
        clean_query = re.sub(r'[^\w\s]', '', query).strip()
        if not clean_query:
            return []
            
        ts_query_str = ' & '.join(clean_query.split())
        
        # Используем func.to_tsvector и func.to_tsquery
        # Поскольку мы не храним content_ts в модели явно (используем on-the-fly или индекс в БД),
        # мы вызываем to_tsvector(content) прямо в запросе.
        
        ts_query_func = func.to_tsquery('russian', ts_query_str)
        ts_vector_func = func.to_tsvector('russian', SearchDocument.content)
        
        rank_col = func.ts_rank_cd(ts_vector_func, ts_query_func).label("rank")
        
        stmt = (
            select(SearchDocument.source_path, SearchDocument.content, SearchDocument.metadata_, rank_col)
            .where(ts_vector_func.op("@@")(ts_query_func))
        )
        
        if source_type:
            stmt = stmt.where(SearchDocument.source_type == source_type)
            
        stmt = stmt.order_by(rank_col.desc()).limit(top_k)
        
        async with get_session() as session:
            try:
                result = await session.execute(stmt)
                rows = result.all()
            except Exception as e:
                logger.error(f"Text search failed: {e}")
                return []

        results = []
        for row in rows:
            # row is (source_path, content, metadata, rank)
            meta = row.metadata_ # Из-за алиаса
            if isinstance(meta, str):
                meta = json.loads(meta)
            elif meta is None:
                meta = {}
            
            results.append({
                'path': row.source_path,
                'content': row.content,
                'metadata': meta,
                'score': row.rank
            })
            
        return results

    async def clear_index(self, source_type: str = None):
        async with get_session() as session:
            if source_type:
                await session.execute(delete(SearchDocument).where(SearchDocument.source_type == source_type))
            else:
                await session.execute(delete(SearchDocument))
            await session.commit()

search_engine = TextSearchEngine()