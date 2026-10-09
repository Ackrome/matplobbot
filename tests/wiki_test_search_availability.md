# Search availability tests

`test_search_availability.py` validates the distinction between successful zero matches, partial source responses and total index unavailability. `TestSearchAvailability` exercises the actual FTS error conversion and global search aggregation with isolated async database/source fakes.

Run `.venv/Scripts/python.exe -m unittest tests.test_search_availability -v`. The tests preserve successful source results when another repository fails, require failure identities to be retained and ensure a partial empty result never becomes a complete empty search. They use unittest and production search services; no network, live index or production data is accessed. When adding source types, extend aggregation cases and localized bot-rendering checks rather than turning exceptions back into empty lists.
