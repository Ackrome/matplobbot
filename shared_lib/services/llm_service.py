import aiohttp
import logging
import json
import os

logger = logging.getLogger(__name__)

# URL for the internal docker network. 
# "mpb-ollama" is the service name in docker-compose.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://mpb-ollama:11434")
MODEL_NAME = "llama3.2:1b"  # Change this if you pulled a different model

class LLMService:
    def __init__(self):
        self.base_url = f"{OLLAMA_HOST}/api/generate"

    async def generate_answer(self, query: str, context_chunks: list[str]) -> str:
        """
        Generates an answer using the Local LLM based on the provided context.
        """
        if not context_chunks:
            return "I couldn't find any relevant information in your notes to answer this."

        # Construct a prompt that forces RAG behavior
        context_block = "\n\n".join([f"--- CHUNK {i+1} ---\n{chunk}" for i, chunk in enumerate(context_chunks)])
        
        system_prompt = (
            "You are Matplobbot, a helpful teaching assistant. "
            "Answer the user's question using ONLY the context provided below. "
            "If the answer is not in the context, say 'I don't have enough information in the notes'. "
            "Keep the answer concise and use Markdown formatting."
        )

        full_prompt = f"{system_prompt}\n\nCONTEXT:\n{context_block}\n\nUSER QUESTION:\n{query}\n\nANSWER:"

        payload = {
            "model": MODEL_NAME,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.3, # Low temperature for factual accuracy
                "num_ctx": 4096     # Context window size
            }
        }

        try:
            timeout = aiohttp.ClientTimeout(total=60) # Give the 1B model time to think
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
            return "I cannot connect to my brain (Ollama service is unreachable)."

llm_service = LLMService()