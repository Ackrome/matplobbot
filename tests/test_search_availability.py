import unittest
from unittest.mock import AsyncMock, patch

from bot.services import search_center
from shared_lib.services import semantic_search


class TestSearchAvailability(unittest.IsolatedAsyncioTestCase):
    async def test_database_failure_is_not_an_empty_search(self):
        session = AsyncMock()
        session.execute.side_effect = RuntimeError("database offline")
        context = AsyncMock()
        context.__aenter__.return_value = session
        with patch.object(semantic_search, "get_session", return_value=context):
            with self.assertRaises(semantic_search.SearchUnavailableError):
                await semantic_search.search_engine.search("algebra", source_type="lib")

    async def test_single_source_outage_propagates_explicit_error(self):
        with patch.object(
            search_center.search_engine, "search", AsyncMock(side_effect=RuntimeError("offline"))
        ):
            with self.assertRaises(semantic_search.SearchUnavailableError):
                await search_center.search_library_examples("algebra")
            with self.assertRaises(semantic_search.SearchUnavailableError):
                await search_center.search_repository_markdown("algebra", "owner/notes")

    async def test_partial_results_keep_successful_repository_and_failure_identity(self):
        async def search(query, source_type, top_k):
            if source_type == "repo:owner/broken":
                raise RuntimeError("offline")
            return [{"path": "topic.md", "score": 1, "metadata": {}}]

        with patch.object(search_center.search_engine, "search", side_effect=search):
            results, filters = await search_center.search_global_sources(
                "algebra", {}, ["owner/good", "owner/broken"]
            )
        self.assertEqual(results.status, "partial")
        self.assertEqual(results.failed_sources, ["owner/broken"])
        self.assertEqual(len(results), 2)
        self.assertEqual(filters["repo_paths"], ["owner/good", "owner/broken"])

    async def test_successful_zero_results_differs_from_total_outage(self):
        with patch.object(search_center.search_engine, "search", AsyncMock(return_value=[])):
            empty, _ = await search_center.search_global_sources("algebra", {}, ["owner/notes"])
        with patch.object(
            search_center.search_engine, "search", AsyncMock(side_effect=RuntimeError("offline"))
        ):
            unavailable, _ = await search_center.search_global_sources(
                "algebra", {}, ["owner/notes"]
            )
        self.assertEqual(empty, [])
        self.assertEqual(unavailable, [])
        self.assertEqual(empty.status, "empty")
        self.assertEqual(unavailable.status, "unavailable")

    async def test_partial_zero_results_does_not_claim_complete_empty(self):
        with (
            patch.object(search_center, "search_library_examples", AsyncMock(return_value=[])),
            patch.object(
                search_center,
                "search_repository_markdown",
                AsyncMock(side_effect=RuntimeError("offline")),
            ),
        ):
            results, _ = await search_center.search_global_sources("algebra", {}, ["owner/notes"])
        self.assertFalse(results)
        self.assertEqual(results.status, "partial")
        self.assertEqual(results.successful_sources, 1)
