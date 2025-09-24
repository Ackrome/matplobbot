import logging
import os
import aiohttp
import base64
import hashlib
import asyncio

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Caches for GitHub API calls to reduce rate-limiting and speed up responses
github_content_cache = TTLCache(maxsize=200, ttl=300)  # Cache for file contents (5 min)
github_dir_cache = TTLCache(maxsize=50, ttl=180)      # Cache for directory listings (3 min)

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


async def upload_image_to_github(image_bytes: asyncio.StreamReader, session: aiohttp.ClientSession, max_retries: int = 3, retry_delay: int = 2) -> str | None:
    """Uploads an image to a GitHub repository and returns the raw content URL, with retries."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set. Image upload to GitHub is disabled.")
        return None

    image_bytes.seek(0)
    image_data = image_bytes.read()

    if not image_data:
        logger.warning("Attempted to upload an empty image.")
        return None

    image_hash = hashlib.sha1(image_data).hexdigest()
    filename = f"{image_hash}.png"

    repo_owner = "Ackrome"
    repo_name = "matplobbot"
    repo_path = f"image/latex_render/{filename}"
    branch = "test"

    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{repo_path}"
    raw_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{branch}/{repo_path}"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    for attempt in range(max_retries):
        try:
            # 1. Check if the file already exists
            async with session.get(api_url, headers=headers) as get_response:
                if get_response.status == 200:
                    logger.info(f"Image {filename} already exists on GitHub. Returning existing URL.")
                    # Optionally, you could get the download_url from get_response.json()
                    return raw_url
                elif get_response.status != 404:
                    # An unexpected error occurred while checking for the file
                    error_text = await get_response.text()
                    logger.error(f"Failed to check for existing file {filename} with status {get_response.status}: {error_text}")
                    # Fall through to retry logic

            # 2. If we are here, the file does not exist (or the check failed), so we try to create it.
            base64_content = base64.b64encode(image_data).decode('utf-8')
            payload = {
                "message": f"feat: Add LaTeX render for {filename}",
                "content": base64_content,
                "branch": branch
            }

            async with session.put(api_url, headers=headers, json=payload) as put_response:
                if put_response.status == 201: # 201 Created
                    response_data = await put_response.json()
                    logger.info(f"Successfully uploaded image to GitHub: {response_data.get('content', {}).get('html_url')}")
                    return response_data.get('content', {}).get('download_url', raw_url)
                
                # Handle race condition where file was created between GET and PUT
                elif put_response.status == 409:
                    logger.warning(f"Race condition for {filename} (409 Conflict). File was created concurrently. Returning existing URL.")
                    return raw_url

                # The 422 error should now be rare, but we handle it as a fallback.
                # It might happen in a race condition where another process creates the file between our GET and PUT.
                elif put_response.status == 422:
                    error_data = await put_response.json()
                    if 'sha' in error_data.get('message', ''):
                        logger.warning(f"Race condition for {filename}? File created between check and upload. Returning existing URL.")
                        return raw_url
                    else:
                        logger.error(f"GitHub image upload API failed for {filename} with status 422: {error_data}. No retry.")
                        return None
                else: # Handle other server errors (5xx) or rate-limiting (403)
                    error_text = await put_response.text()
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} for {filename} failed with status {put_response.status}: {error_text}. Retrying in {retry_delay}s...")

        except aiohttp.ClientError as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} for {filename} failed with network error: {e}. Retrying in {retry_delay}s...")
        except Exception as e:
            logger.error(f"An unexpected non-network error occurred during upload for {filename}: {e}", exc_info=True)
            return None

        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)

    logger.error(f"Failed to upload image {filename} after {max_retries} attempts.")
    return None