import logging
import json
import re
from shared_lib.database import get_db_connection_obj

logger = logging.getLogger(__name__)

class TextSearchEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TextSearchEngine, cls).__new__(cls)
        return cls._instance

    async def upsert_document(self, source_type: str, path: str, content: str, metadata: dict):
        """
        Inserts document for standard text search (No vectors/embeddings).
        """
        metadata_json = json.dumps(metadata)

        # We pass an empty vector or null for the embedding column to satisfy the schema, 
        # or we just ignore it if the column allows nulls. 
        # Assuming the schema requires it, we pass a zero-vector or modify the query.
        # Since we are stripping RAG, we rely purely on 'content_ts' (TSVECTOR).
        
        # Note: We fill 'embedding' with a dummy zero vector to avoid SQL errors 
        # if you haven't migrated the column to be nullable. 
        # 384 is the dimension of the previous model.
        dummy_vector = "[0]" * 384 
        
        async with get_db_connection_obj() as conn:
            await conn.execute("""
                INSERT INTO search_documents (source_type, source_path, content, metadata, embedding, content_ts)
                VALUES ($1, $2, $3, $4, '[0]', to_tsvector('russian', $3))
                ON CONFLICT (source_type, source_path) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    content_ts = to_tsvector('russian', EXCLUDED.content),
                    created_at = CURRENT_TIMESTAMP
            """, source_type, path, content, metadata_json)

    async def search(self, query: str, source_type: str = None, top_k: int = 5) -> list[dict]:
        """
        Performs standard Full-Text Search using PostgreSQL.
        """
        # Prepare keyword query: replace spaces with & for PG boolean search
        clean_query = re.sub(r'[^\w\s]', '', query).strip()
        if not clean_query:
            return []
            
        ts_query = ' & '.join(clean_query.split())

        filter_clause = "AND source_type = $2" if source_type else ""
        args = [ts_query]
        if source_type:
            args.append(source_type)

        sql = f"""
            SELECT 
                source_path, content, metadata,
                ts_rank_cd(content_ts, to_tsquery('russian', $1)) as rank
            FROM search_documents
            WHERE 
                content_ts @@ to_tsquery('russian', $1)
            {filter_clause}
            ORDER BY rank DESC
            LIMIT {top_k}
        """
        
        async with get_db_connection_obj() as conn:
            try:
                rows = await conn.fetch(sql, *args)
            except Exception as e:
                logger.error(f"Text search failed: {e}")
                return []

        results = []
        for row in rows:
            meta = row['metadata']
            if isinstance(meta, str):
                meta = json.loads(meta)
            elif meta is None:
                meta = {}
            
            results.append({
                'path': row['source_path'],
                'content': row['content'],
                'metadata': meta,
                'score': row['rank']
            })
            
        return results

    async def clear_index(self, source_type: str = None):
        async with get_db_connection_obj() as conn:
            if source_type:
                await conn.execute("DELETE FROM search_documents WHERE source_type = $1", source_type)
            else:
                await conn.execute("TRUNCATE search_documents")

search_engine = TextSearchEngine()