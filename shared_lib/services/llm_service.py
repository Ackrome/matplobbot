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

        # Limit context to avoid overflow (Roughly 12000 characters ~= 3000 tokens)
        # This leaves ~1000 tokens for the system prompt and the answer.
        MAX_CHARS = 12000
        combined_context = ""
        for i, chunk in enumerate(context_chunks):
            chunk_text = f"\n\n--- CHUNK {i+1} ---\n{chunk}"
            if len(combined_context) + len(chunk_text) < MAX_CHARS:
                combined_context += chunk_text
            else:
                break
        
        system_prompt = (
            "You are Matplobbot, a helpful teaching assistant. "
            "Answer the user's question using ONLY the context provided below. "
            "If the answer is not in the context, say 'I don't have enough information in the notes'. "
            "Keep the answer concise and use Markdown formatting."
        )

        full_prompt = f"{system_prompt}\n\nCONTEXT:{combined_context}\n\nUSER QUESTION:\n{query}\n\nANSWER:"

        payload = {
            "model": MODEL_NAME,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_ctx": 4096
            }
        }

        try:
            # --- FIX: Increased timeout to 5 minutes for CPU inference ---
            timeout = aiohttp.ClientTimeout(total=300) 
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.base_url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("response", "Error: Empty response from LLM.")
                    else:
                        error_text = await response.text()
                        logger.error(f"Ollama API Error: {response.status} - {error_text}")
                        return "I'm having trouble thinking right now (LLM Error)."
        except Exception as e:
            logger.error(f"LLM Connection Error: {e}")
            return f"I cannot connect to my brain (Timeout or Connection Error). Details: {e}"

llm_service = LLMService()