import aiohttp
import logging
import json
import os

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://mpb-ollama:11434")
MODEL_NAME = "llama3.2:1b"

class LLMService:
    def __init__(self):
        self.base_url = f"{OLLAMA_HOST}/api/generate"

    async def generate_answer(self, query: str, context_chunks: list[str]) -> str:
        if not context_chunks:
            return "I couldn't find any relevant information in your notes to answer this."

        # --- OPTIMIZATION 1: Hard Character Limit ---
        # 1B models have small context windows (4096 tokens). 
        # We limit context to ~10,000 chars (~2500 tokens) to leave room for the answer.
        MAX_CHARS = 10000 
        combined_context = ""
        for i, chunk in enumerate(context_chunks):
            # Truncate individual chunks if they are huge
            clean_chunk = chunk[:4000] 
            entry = f"\n\n--- SOURCE {i+1} ---\n{clean_chunk}"
            
            if len(combined_context) + len(entry) < MAX_CHARS:
                combined_context += entry
            else:
                break
        
        system_prompt = (
            "You are Matplobbot. Answer the question using ONLY the provided context. "
            "If the answer is not in the context, say 'I don't know based on these notes'. "
            "Be concise."
        )

        full_prompt = f"{system_prompt}\n\nCONTEXT:{combined_context}\n\nUSER QUESTION:\n{query}\n\nANSWER:"

        payload = {
            "model": MODEL_NAME,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_ctx": 4096 # The model's limit
            }
        }

        try:
            # --- OPTIMIZATION 2: 5 Minute Timeout ---
            # CPU inference is slow. We give it 300 seconds.
            timeout = aiohttp.ClientTimeout(total=300) 
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.base_url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("response", "Error: Empty response from LLM.")
                    else:
                        error_text = await response.text()
                        logger.error(f"Ollama API Error: {response.status} - {error_text}")
                        return f"My brain is overloaded (Error {response.status}). Try a simpler question."
        except Exception as e:
            logger.error(f"LLM Connection Error: {e}")
            return "I cannot connect to my brain (Timeout). The server is busy processing."

llm_service = LLMService()