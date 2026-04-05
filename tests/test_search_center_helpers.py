from bot.services.search_center import (
    GLOBAL_SOURCE_GITHUB,
    GLOBAL_SOURCE_LIBRARY,
    SEARCH_KIND_GITHUB,
    SEARCH_KIND_LIBRARY,
    format_github_search_results,
    merge_global_results,
    normalize_global_filters,
    toggle_global_repo,
    toggle_global_source,
)
from shared_lib.database import delete_search_preset_entries, upsert_search_preset_entries


def test_upsert_search_preset_entries_replaces_existing_and_sorts_newest_first():
    existing = [
        {"id": "older", "name": "Older", "updated_at": "2026-01-01T00:00:00+00:00"},
        {"id": "same", "name": "Same", "updated_at": "2026-01-02T00:00:00+00:00"},
    ]
    preset = {"id": "same", "name": "Updated", "updated_at": "2026-01-03T00:00:00+00:00"}

    updated = upsert_search_preset_entries(existing, preset)

    assert [item["id"] for item in updated] == ["same", "older"]
    assert updated[0]["name"] == "Updated"


def test_delete_search_preset_entries_removes_matching_id():
    existing = [{"id": "one"}, {"id": "two"}]

    updated = delete_search_preset_entries(existing, "one")

    assert updated == [{"id": "two"}]


def test_normalize_global_filters_discards_unknown_repos():
    normalized = normalize_global_filters(
        {
            "sources": [GLOBAL_SOURCE_LIBRARY, GLOBAL_SOURCE_GITHUB],
            "repo_paths": ["team/notes", "team/missing"],
        },
        ["team/notes", "team/math"],
    )

    assert normalized == {
        "sources": [GLOBAL_SOURCE_LIBRARY, GLOBAL_SOURCE_GITHUB],
        "repo_paths": ["team/notes"],
    }


def test_toggle_global_source_keeps_at_least_one_source_enabled():
    updated, changed = toggle_global_source(
        {"sources": [GLOBAL_SOURCE_LIBRARY], "repo_paths": []},
        GLOBAL_SOURCE_LIBRARY,
        [],
    )

    assert changed is False
    assert updated["sources"] == [GLOBAL_SOURCE_LIBRARY]


def test_toggle_global_repo_updates_selected_repo_paths():
    updated = toggle_global_repo(
        {
            "sources": [GLOBAL_SOURCE_LIBRARY, GLOBAL_SOURCE_GITHUB],
            "repo_paths": ["team/notes"],
        },
        "team/math",
        ["team/notes", "team/math"],
    )

    assert updated["repo_paths"] == ["team/notes", "team/math"]


def test_format_github_search_results_deduplicates_chunks_per_file():
    raw_results = [
        {
            "path": "docs/topic.md#chunk_0",
            "metadata": {"file_path": "docs/topic.md"},
            "score": 0.9,
        },
        {
            "path": "docs/topic.md#chunk_1",
            "metadata": {"file_path": "docs/topic.md"},
            "score": 0.7,
        },
        {
            "path": "docs/other.md#chunk_0",
            "metadata": {"file_path": "docs/other.md"},
            "score": 0.8,
        },
    ]

    results = format_github_search_results(raw_results, "team/notes")

    assert results == [
        {
            "kind": SEARCH_KIND_GITHUB,
            "path": "docs/topic.md",
            "repo_path": "team/notes",
            "score": 0.9,
        },
        {
            "kind": SEARCH_KIND_GITHUB,
            "path": "docs/other.md",
            "repo_path": "team/notes",
            "score": 0.8,
        },
    ]


def test_merge_global_results_orders_by_score():
    merged = merge_global_results(
        [{"kind": SEARCH_KIND_LIBRARY, "path": "lib.topic", "score": 0.7}],
        [{"kind": SEARCH_KIND_GITHUB, "path": "docs/topic.md", "score": 0.9}],
        limit=10,
    )

    assert [item["kind"] for item in merged] == [SEARCH_KIND_GITHUB, SEARCH_KIND_LIBRARY]
