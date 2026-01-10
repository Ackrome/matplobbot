import logging
import json
import numpy as np
import asyncio
import re
from sentence_transformers import SentenceTransformer
from shared_lib.database import get_db_connection_obj

logger = logging.getLogger(__name__)

class SemanticSearchEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SemanticSearchEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        
        logger.info("Initializing Semantic Search Model (CPU)...")
        self.device = 'cpu'
        self.model = SentenceTransformer('all-MiniLM-L6-v2', device=self.device)
        self._initialized = True
        logger.info("Semantic Search Model loaded.")

    def encode(self, text: str) -> list[float]:
        embedding = self.model.encode(text, convert_to_numpy=True)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.tolist()

    async def upsert_document(self, source_type: str, path: str, content: str, metadata: dict):
        vector = await asyncio.to_thread(self.encode, content)
        vector_str = str(vector) 
        metadata_json = json.dumps(metadata)

        # We ensure content_ts is updated automatically using to_tsvector
        async with get_db_connection_obj() as conn:
            await conn.execute("""
                INSERT INTO search_documents (source_type, source_path, content, metadata, embedding, content_ts)
                VALUES ($1, $2, $3, $4, $5, to_tsvector('russian', $3))
                ON CONFLICT (source_type, source_path) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding,
                    content_ts = to_tsvector('russian', EXCLUDED.content),
                    created_at = CURRENT_TIMESTAMP
            """, source_type, path, content, metadata_json, vector_str)

    async def search(self, query: str, source_type: str = None, top_k: int = 5) -> list[dict]:
        """
        Performs Hybrid Search (Vector + Keyword)
        """
        query_vector = await asyncio.to_thread(self.encode, query)
        query_vector_str = str(query_vector)
        
        # Prepare keyword query: replace spaces with & for PG boolean search
        # "decision trees" -> "decision & trees"
        clean_query = re.sub(r'[^\w\s]', '', query).strip()
        ts_query = ' & '.join(clean_query.split())

        filter_clause = "AND source_type = $3" if source_type else ""
        args = [query_vector_str, ts_query]
        if source_type:
            args.append(source_type)

        # HYBRID QUERY EXPLANATION:
        # 1. semantic_rank: Cosine similarity (0 to 1)
        # 2. keyword_rank: Text search rank (0 to ~1+)
        # We normalize and combine them. If keyword match is strong, it boosts the score.
        sql = f"""
            WITH hybrid_scores AS (
                SELECT 
                    source_path, content, metadata,
                    (1 - (embedding <=> $1)) as semantic_score,
                    ts_rank_cd(content_ts, to_tsquery('russian', $2)) as keyword_score
                FROM search_documents
                WHERE 
                    (1 - (embedding <=> $1) > 0.15)  -- Lower vector threshold
                    OR 
                    (content_ts @@ to_tsquery('russian', $2)) -- OR exact keyword match
                {filter_clause}
            )
            SELECT 
                source_path, content, metadata,
                (semantic_score * 0.7 + LEAST(keyword_score, 1.0) * 0.3) as final_score
            FROM hybrid_scores
            ORDER BY final_score DESC
            LIMIT {top_k}
        """
        
        async with get_db_connection_obj() as conn:
            try:
                rows = await conn.fetch(sql, *args)
            except Exception as e:
                # Fallback if tsquery syntax is invalid (e.g. weird symbols)
                logger.warning(f"Hybrid search failed ({e}), falling back to pure vector.")
                fallback_sql = f"""
                    SELECT source_path, content, metadata, 1 - (embedding <=> $1) as final_score
                    FROM search_documents WHERE 1 - (embedding <=> $1) > 0.2
                    {filter_clause.replace('$3', '$2')}
                    ORDER BY embedding <=> $1 LIMIT {top_k}
                """
                fallback_args = [query_vector_str]
                if source_type: fallback_args.append(source_type)
                rows = await conn.fetch(fallback_sql, *fallback_args)

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
                'score': row['final_score']
            })
            
        return results

    async def clear_index(self, source_type: str = None):
        async with get_db_connection_obj() as conn:
            if source_type:
                await conn.execute("DELETE FROM search_documents WHERE source_type = $1", source_type)
            else:
                await conn.execute("TRUNCATE search_documents")

search_engine = SemanticSearchEngine()