import asyncio
import logging
from typing import Any

from shared_lib.services.semantic_search import search_engine

logger = logging.getLogger(__name__)

SEARCH_KIND_LIBRARY = "library"
SEARCH_KIND_GITHUB = "github"
SEARCH_KIND_SCHEDULE = "schedule"
SEARCH_KIND_GLOBAL = "global"

GLOBAL_SOURCE_LIBRARY = "library"
GLOBAL_SOURCE_GITHUB = "github"
GLOBAL_SOURCES = {GLOBAL_SOURCE_LIBRARY, GLOBAL_SOURCE_GITHUB}


def build_default_global_filters(repo_paths: list[str]) -> dict[str, list[str]]:
    unique_repos = list(dict.fromkeys(repo_paths))
    sources = [GLOBAL_SOURCE_LIBRARY]
    if unique_repos:
        sources.append(GLOBAL_SOURCE_GITHUB)
    return {"sources": sources, "repo_paths": unique_repos}


def normalize_global_filters(filters: dict[str, Any] | None, repo_paths: list[str]) -> dict[str, list[str]]:
    available_repos = list(dict.fromkeys(repo_paths))
    default_filters = build_default_global_filters(available_repos)
    if not filters:
        return default_filters

    requested_sources = [
        source
        for source in dict.fromkeys(filters.get("sources") or [])
        if source in GLOBAL_SOURCES
    ]
    sources = requested_sources or default_filters["sources"]

    if GLOBAL_SOURCE_GITHUB not in sources or not available_repos:
        selected_repos: list[str] = []
    else:
        requested_repos = filters.get("repo_paths") or available_repos
        selected_repos = [repo for repo in dict.fromkeys(requested_repos) if repo in available_repos]

    return {"sources": sources, "repo_paths": selected_repos}


def toggle_global_source(
    filters: dict[str, Any], source: str, repo_paths: list[str]
) -> tuple[dict[str, list[str]], bool]:
    normalized = normalize_global_filters(filters, repo_paths)
    sources = list(normalized["sources"])

    if source in sources:
        if len(sources) == 1:
            return normalized, False
        sources.remove(source)
    else:
        sources.append(source)

    updated = {"sources": sources, "repo_paths": normalized["repo_paths"]}
    if source == GLOBAL_SOURCE_GITHUB and source in sources and not updated["repo_paths"]:
        updated["repo_paths"] = list(dict.fromkeys(repo_paths))
    if GLOBAL_SOURCE_GITHUB not in sources:
        updated["repo_paths"] = []

    return normalize_global_filters(updated, repo_paths), True


def toggle_global_repo(filters: dict[str, Any], repo_path: str, repo_paths: list[str]) -> dict[str, list[str]]:
    normalized = normalize_global_filters(filters, repo_paths)
    selected_repos = list(normalized["repo_paths"])
    if repo_path in selected_repos:
        selected_repos.remove(repo_path)
    else:
        selected_repos.append(repo_path)

    return normalize_global_filters(
        {"sources": normalized["sources"], "repo_paths": selected_repos},
        repo_paths,
    )


def format_github_search_results(raw_results: list[dict], repo_path: str) -> list[dict[str, Any]]:
    formatted_results: list[dict[str, Any]] = []
    seen_files: set[str] = set()

    for result in raw_results:
        metadata = result.get("metadata") or {}
        file_path = metadata.get("file_path") or result.get("path")
        if not file_path or file_path in seen_files:
            continue

        seen_files.add(file_path)
        formatted_results.append(
            {
                "kind": SEARCH_KIND_GITHUB,
                "path": file_path,
                "repo_path": repo_path,
                "score": float(result.get("score") or 0),
            }
        )

    return formatted_results


def merge_global_results(
    library_results: list[dict[str, Any]], github_results: list[dict[str, Any]], limit: int = 20
) -> list[dict[str, Any]]:
    combined_results = [*library_results, *github_results]
    combined_results.sort(
        key=lambda item: (float(item.get("score") or 0), item.get("kind") == SEARCH_KIND_LIBRARY),
        reverse=True,
    )
    return combined_results[:limit]


def format_global_result_label(result: dict[str, Any]) -> str:
    if result.get("kind") == SEARCH_KIND_LIBRARY:
        return f"📚 {result['path']}"

    repo_name = result.get("repo_path", "").split("/")[-1]
    return f"📄 [{repo_name}] {result['path']}"


async def search_library_examples(query: str, limit: int = 20) -> list[dict[str, Any]]:
    try:
        raw_results = await search_engine.search(query, source_type="lib", top_k=limit)
    except Exception as exc:
        logger.error("Library semantic search failed: %s", exc, exc_info=True)
        return []

    return [
        {
            "kind": SEARCH_KIND_LIBRARY,
            "path": item["path"],
            "score": float(item.get("score") or 0),
        }
        for item in raw_results
    ]


async def search_repository_markdown(
    query: str, repo_path: str, limit: int = 10
) -> list[dict[str, Any]]:
    try:
        raw_results = await search_engine.search(query, source_type=f"repo:{repo_path}", top_k=limit)
    except Exception as exc:
        logger.error("GitHub semantic search failed for %s: %s", repo_path, exc, exc_info=True)
        return []

    return format_github_search_results(raw_results, repo_path)


async def search_linked_github_markdown(
    query: str, repo_paths: list[str], per_repo_limit: int = 5, limit: int = 20
) -> list[dict[str, Any]]:
    if not repo_paths:
        return []

    results_per_repo = await asyncio.gather(
        *[search_repository_markdown(query, repo_path, limit=per_repo_limit) for repo_path in repo_paths]
    )
    merged_results = [item for repo_results in results_per_repo for item in repo_results]
    merged_results.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return merged_results[:limit]


async def search_global_sources(
    query: str, filters: dict[str, Any], repo_paths: list[str], limit: int = 20
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    normalized_filters = normalize_global_filters(filters, repo_paths)
    search_tasks = []

    if GLOBAL_SOURCE_LIBRARY in normalized_filters["sources"]:
        search_tasks.append(search_library_examples(query, limit=limit))
    else:
        search_tasks.append(asyncio.sleep(0, result=[]))

    if GLOBAL_SOURCE_GITHUB in normalized_filters["sources"] and normalized_filters["repo_paths"]:
        search_tasks.append(
            search_linked_github_markdown(
                query,
                normalized_filters["repo_paths"],
                per_repo_limit=max(3, min(8, limit)),
                limit=limit,
            )
        )
    else:
        search_tasks.append(asyncio.sleep(0, result=[]))

    library_results, github_results = await asyncio.gather(*search_tasks)
    return merge_global_results(library_results, github_results, limit=limit), normalized_filters
