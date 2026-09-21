import datetime
import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

import aiohttp
from cachetools import TTLCache

from .config import GITHUB_TOKEN

logger = logging.getLogger(__name__)

DEFAULT_GITHUB_BRANCH = "main"


@dataclass(frozen=True)
class GitHubRepoReference:
    """Canonical repository reference used by the bot and the indexer."""

    owner_repo: str
    branch: str = DEFAULT_GITHUB_BRANCH

    @property
    def canonical(self) -> str:
        # Encode slashes so callback paths can still split ``owner/repo`` from
        # a branch that itself contains slashes (for example ``release/v2``).
        return f"{self.owner_repo}@{quote(self.branch, safe='')}"


def parse_repo_reference(value: str | None) -> GitHubRepoReference | None:
    """Parse ``owner/repo`` or a GitHub URL and preserve an explicit branch.

    The database stores the canonical ``owner/repo@branch`` form.  A missing
    branch intentionally resolves to ``main`` so existing rows keep their
    historical behaviour.
    """
    raw = (value or "").strip()
    if not raw:
        return None

    raw = re.sub(r"^https?://(?:www\.)?github\.com/", "", raw, flags=re.IGNORECASE)
    raw = raw.split("?", 1)[0].split("#", 1)[0].strip("/")
    parts = [part for part in raw.split("/") if part]
    if len(parts) < 2:
        return None

    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    explicit_branch = None
    if "@" in repo:
        repo, explicit_branch = repo.split("@", 1)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        return None

    branch = DEFAULT_GITHUB_BRANCH
    if explicit_branch is not None:
        branch = "/".join([explicit_branch, *parts[2:]]) if explicit_branch else branch
    elif len(parts) >= 4 and parts[2].lower() in {"tree", "blob"}:
        branch = "/".join(parts[3:]) or branch
    elif len(parts) == 3 and parts[2] not in {"tree", "blob"}:
        # Accept the compact ``owner/repo/branch`` form for branch names
        # supplied without a GitHub URL.
        branch = parts[2]

    branch = unquote(branch).strip().strip("/") or DEFAULT_GITHUB_BRANCH
    if any(char in branch for char in '?#[\\"') or branch in {".", ".."}:
        return None
    return GitHubRepoReference(f"{owner}/{repo}", branch)


def split_repo_reference(value: str) -> tuple[str, str]:
    """Return ``(owner/repo, branch)`` and fall back safely for old rows."""
    reference = parse_repo_reference(value)
    if not reference:
        return value, DEFAULT_GITHUB_BRANCH
    return reference.owner_repo, reference.branch


# Caches for GitHub API calls to reduce rate-limiting and speed up responses
github_content_cache = TTLCache(maxsize=200, ttl=300)  # Cache for file contents (5 min)
github_dir_cache = TTLCache(maxsize=50, ttl=180)  # Cache for directory listings (3 min)
github_repo_files_cache = TTLCache(maxsize=20, ttl=600)  # Cache for full repo file lists (10 min)


async def get_github_repo_contents(repo_path: str, path: str = "") -> list[dict] | None:
    """Fetches directory contents from the GitHub repository."""
    github_token = GITHUB_TOKEN
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set. /lec_all command is disabled.")
        return None

    owner_repo, branch = split_repo_reference(repo_path)
    cache_key = f"{owner_repo}@{branch}:{path}"
    # Check cache first
    cached_contents = github_dir_cache.get(cache_key)
    if cached_contents is not None:
        logger.info(f"Cache hit for dir content: {cache_key}")
        return cached_contents

    # The URL for the contents API
    url = f"https://api.github.com/repos/{owner_repo}/contents/{quote(path, safe='/')}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {github_token}",
    }
    params = {"ref": branch}

    try:
        async with (
            aiohttp.ClientSession(headers=headers) as session,
            session.get(url, params=params) as response,
        ):
            if response.status == 200:
                data = await response.json()
                # Sort items: folders first, then files, all alphabetically
                if isinstance(data, list):
                    data.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
                # Store in cache on success
                github_dir_cache[cache_key] = data
                return data
            elif response.status == 401:
                logger.critical(
                    "GitHub API request failed with 401 Unauthorized. The GITHUB_TOKEN is likely invalid, expired, or missing 'repo' scope."
                )
                return None
            else:
                error_text = await response.text()
                logger.error(
                    f"GitHub API contents fetch failed for path '{path}' with status {response.status}: {error_text}"
                )
                return None
    except Exception as e:
        logger.error(
            f"Error during GitHub API contents request for path '{path}': {e}", exc_info=True
        )
        return None


async def get_all_repo_files_cached(
    repo_path: str, session: aiohttp.ClientSession
) -> list[str] | None:
    """
    Fetches a list of all file paths in a repository using the Git Trees API.
    Results are cached to minimize API calls.
    """
    owner_repo, branch = split_repo_reference(repo_path)
    cache_key = f"{owner_repo}@{branch}"
    # Check cache first
    if cache_key in github_repo_files_cache:
        logger.info(f"Cache hit for repo file list: {cache_key}")
        return github_repo_files_cache[cache_key]

    github_token = GITHUB_TOKEN
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set. Cannot fetch repo file list.")
        return None

    url = (
        f"https://api.github.com/repos/{owner_repo}/git/trees/{quote(branch, safe='')}?recursive=1"
    )
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {github_token}",
    }

    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("truncated"):
                    logger.warning(
                        f"File list for repo {repo_path} is truncated. Wikilink resolution may be incomplete."
                    )

                # We are only interested in files ('blob')
                file_paths = [
                    item["path"] for item in data.get("tree", []) if item["type"] == "blob"
                ]

                # Store in cache on success
                github_repo_files_cache[cache_key] = file_paths
                logger.info(f"Fetched and cached {len(file_paths)} file paths for repo {repo_path}")
                return file_paths
            else:
                error_text = await response.text()
                # Log the detailed error from GitHub API for better diagnostics
                logger.error(
                    f"GitHub API trees fetch failed for repo '{repo_path}' with status {response.status}. Response: {error_text}"
                )
                return None
    except Exception as e:
        logger.error(
            f"Error during GitHub API trees request for repo '{repo_path}': {e}", exc_info=True
        )
        return None


async def get_repo_contributors(repo_path: str, session: aiohttp.ClientSession) -> list | None:
    """
    Получает список контрибьюторов для указанного репозитория.
    Возвращает список словарей {'login': username, 'html_url': profile_url} или None в случае ошибки.
    """
    github_token = GITHUB_TOKEN
    owner_repo, _ = split_repo_reference(repo_path)
    url = f"https://api.github.com/repos/{owner_repo}/contributors"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                # Извлекаем только нужные поля
                return [{"login": user["login"], "html_url": user["html_url"]} for user in data]
            else:
                logger.error(
                    f"Failed to fetch contributors for {repo_path}. Status: {response.status}"
                )
                return None
    except Exception as e:
        logger.error(f"Exception while fetching contributors for {repo_path}: {e}")
        return None


async def get_file_last_modified_date(
    repo_path: str, file_path: str, session: aiohttp.ClientSession
) -> str | None:
    """
    Получает дату последнего коммита для указанного файла.
    Возвращает отформатированную строку с датой или None в случае ошибки.
    """
    github_token = GITHUB_TOKEN
    owner_repo, branch = split_repo_reference(repo_path)
    url = f"https://api.github.com/repos/{owner_repo}/commits"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    try:
        async with session.get(
            url,
            headers=headers,
            params={"path": file_path, "sha": branch, "page": 1, "per_page": 1},
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data:
                    commit_date_str = data[0]["commit"]["committer"]["date"]
                    # Преобразуем из ISO формата в читаемый вид
                    commit_date = datetime.datetime.fromisoformat(
                        commit_date_str.replace("Z", "+00:00")
                    )
                    return commit_date.strftime("%d %B %Y")
                return None  # Если для файла нет коммитов (маловероятно)
            else:
                logger.error(
                    f"Failed to fetch last commit date for {file_path}. Status: {response.status}"
                )
                return None
    except Exception as e:
        logger.error(f"Exception while fetching last commit date for {file_path}: {e}")
        return None
