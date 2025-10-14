import logging
import os
import aiohttp
import base64
import hashlib
import asyncio
import datetime

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Caches for GitHub API calls to reduce rate-limiting and speed up responses
github_content_cache = TTLCache(maxsize=200, ttl=300)  # Cache for file contents (5 min)
github_dir_cache = TTLCache(maxsize=50, ttl=180)      # Cache for directory listings (3 min)
github_repo_files_cache = TTLCache(maxsize=20, ttl=600) # Cache for full repo file lists (10 min)

# --- Constants ---
MD_SEARCH_BRANCH = "main"


async def get_github_repo_contents(repo_path: str, path: str = "") -> list[dict] | None:
    """Fetches directory contents from the GitHub repository."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set. /lec_all command is disabled.")
        return None

    cache_key = f"{repo_path}:{path}"
    # Check cache first
    cached_contents = github_dir_cache.get(cache_key)
    if cached_contents is not None:
        logger.info(f"Cache hit for dir content: {cache_key}")
        return cached_contents

    # The URL for the contents API
    url = f"https://api.github.com/repos/{repo_path}/contents/{path}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {github_token}"
    }
    params = {"ref": MD_SEARCH_BRANCH}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Sort items: folders first, then files, all alphabetically
                    if isinstance(data, list):
                        data.sort(key=lambda x: (x['type'] != 'dir', x['name'].lower()))
                    # Store in cache on success
                    github_dir_cache[cache_key] = data
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"GitHub API contents fetch failed for path '{path}' with status {response.status}: {error_text}")
                    return None
    except Exception as e:
        logger.error(f"Error during GitHub API contents request for path '{path}': {e}", exc_info=True)
        return None

async def get_all_repo_files_cached(repo_path: str, session: aiohttp.ClientSession) -> list[str] | None:
    """
    Fetches a list of all file paths in a repository using the Git Trees API.
    Results are cached to minimize API calls.
    """
    # Check cache first
    if repo_path in github_repo_files_cache:
        logger.info(f"Cache hit for repo file list: {repo_path}")
        return github_repo_files_cache[repo_path]

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set. Cannot fetch repo file list.")
        return None

    url = f"https://api.github.com/repos/{repo_path}/git/trees/{MD_SEARCH_BRANCH}?recursive=1"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {github_token}"
    }

    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("truncated"):
                    logger.warning(f"File list for repo {repo_path} is truncated. Wikilink resolution may be incomplete.")
                
                # We are only interested in files ('blob')
                file_paths = [item['path'] for item in data.get('tree', []) if item['type'] == 'blob']
                
                # Store in cache on success
                github_repo_files_cache[repo_path] = file_paths
                logger.info(f"Fetched and cached {len(file_paths)} file paths for repo {repo_path}")
                return file_paths
            else:
                error_text = await response.text()
                # Log the detailed error from GitHub API for better diagnostics
                logger.error(f"GitHub API trees fetch failed for repo '{repo_path}' with status {response.status}. Response: {error_text}")
                return None
    except Exception as e:
        logger.error(f"Error during GitHub API trees request for repo '{repo_path}': {e}", exc_info=True)
        return None


async def get_repo_contributors(repo_path: str, session: aiohttp.ClientSession) -> list | None:
    """
    Получает список контрибьюторов для указанного репозитория.
    Возвращает список словарей {'login': username, 'html_url': profile_url} или None в случае ошибки.
    """
    github_token = os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo_path}/contributors"
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if github_token:
        headers['Authorization'] = f'token {github_token}'
        
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                # Извлекаем только нужные поля
                return [{'login': user['login'], 'html_url': user['html_url']} for user in data]
            else:
                logger.error(f"Failed to fetch contributors for {repo_path}. Status: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Exception while fetching contributors for {repo_path}: {e}")
        return None

async def get_file_last_modified_date(repo_path: str, file_path: str, session: aiohttp.ClientSession) -> str | None:
    """
    Получает дату последнего коммита для указанного файла.
    Возвращает отформатированную строку с датой или None в случае ошибки.
    """
    github_token = os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo_path}/commits?path={file_path}&page=1&per_page=1"
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if github_token:
        headers['Authorization'] = f'token {github_token}'

    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data:
                    commit_date_str = data[0]['commit']['committer']['date']
                    # Преобразуем из ISO формата в читаемый вид
                    commit_date = datetime.datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))
                    return commit_date.strftime("%d %B %Y")
                return None # Если для файла нет коммитов (маловероятно)
            else:
                logger.error(f"Failed to fetch last commit date for {file_path}. Status: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Exception while fetching last commit date for {file_path}: {e}")
        return None