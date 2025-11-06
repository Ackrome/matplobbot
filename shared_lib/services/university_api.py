import aiohttp
from datetime import datetime
from typing import List, Dict, Any
import asyncio
import random
import logging
import ssl
import certifi

class RuzAPIError(Exception):
    """Custom exception for RUZ API errors."""
    pass

class RuzAPIClient:
    """Asynchronous API client for ruz.fa.ru."""
    def __init__(self, session: aiohttp.ClientSession, max_retries: int = 4, initial_delay: float = 1.0, backoff_factor: float = 2.0):
        self.HOST = "https://ruz.fa.ru"
        self.session = session
        self.logger = logging.getLogger(__name__)
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor

    async def _request(self, sub_url: str) -> Dict[str, Any] | List[Dict[str, Any]]:
        """Performs an asynchronous request to the RUZ API."""
        full_url = self.HOST + sub_url
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                async with self.session.get(full_url, ssl=ssl_context) as response:
                    # Success case
                    if response.status == 200:
                        json_response = await response.json()
                        return json_response if isinstance(json_response, list) else []

                    # Client-side errors (4xx) - don't retry
                    if 400 <= response.status < 500:
                        error_text = await response.text()
                        raise RuzAPIError(f"Client Error: Status {response.status} for URL {full_url}. Response: {error_text}")

                    # Server-side errors (5xx) - retry
                    if response.status >= 500:
                        error_text = await response.text()
                        last_exception = RuzAPIError(f"Server Error: Status {response.status} for URL {full_url}. Response: {error_text}")
                        self.logger.warning(f"RUZ API request failed (attempt {attempt + 1}/{self.max_retries}): {last_exception}")
                    else: # Other unexpected status codes
                        last_exception = RuzAPIError(f"Unexpected status {response.status} for URL {full_url}")

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                self.logger.warning(f"RUZ API request failed (attempt {attempt + 1}/{self.max_retries}) with connection error: {e}")

            # If we are not on the last attempt, calculate delay and sleep
            if attempt < self.max_retries - 1:
                delay = self.initial_delay * (self.backoff_factor ** attempt)
                jitter = delay * random.uniform(-0.1, 0.1) # Add +/- 10% jitter
                await asyncio.sleep(delay + jitter)

        # If all retries fail, raise the last captured exception
        self.logger.error(f"RUZ API request failed after {self.max_retries} attempts for URL: {full_url}")
        raise RuzAPIError(f"Failed after {self.max_retries} retries.") from last_exception


    async def search(self, term: str, search_type: str) -> List[Dict[str, Any]]:
        """Generic search function."""
        return await self._request(f"/api/search?term={term}&type={search_type}")

    async def get_schedule(self, entity_type: str, entity_id: str, start: str, finish: str) -> List[Dict[str, Any]]:
        """Generic function to get a schedule."""
        return await self._request(f"/api/schedule/{entity_type}/{entity_id}?start={start}&finish={finish}&lng=1")

def create_ruz_api_client(session: aiohttp.ClientSession) -> RuzAPIClient:
    """
    Creates and returns a RuzAPIClient instance.
    This function is intended to be called once during application startup.
    """
    return RuzAPIClient(session)