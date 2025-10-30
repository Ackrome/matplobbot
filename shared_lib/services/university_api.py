import aiohttp
from datetime import datetime
from typing import List, Dict, Any
import ssl
import certifi

class RuzAPIError(Exception):
    """Custom exception for RUZ API errors."""
    pass

class RuzAPIClient:
    """Asynchronous API client for ruz.fa.ru."""
    def __init__(self, session: aiohttp.ClientSession):
        self.HOST = "https://ruz.fa.ru"
        self.session = session

    async def _request(self, sub_url: str) -> Dict[str, Any]:
        """Performs an asynchronous request to the RUZ API."""
        full_url = self.HOST + sub_url
        # Create an SSL context that uses the certifi bundle for verification.
        # This is more reliable than the system's default trust store, especially in Docker.
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        async with self.session.get(full_url, ssl=ssl_context) as response:
            if response.status == 200:
                return await response.json()
            error_text = await response.text()
            raise RuzAPIError(
                f"RUZ API Error: Status {response.status} for URL {full_url}. Response: {error_text}"
            )

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