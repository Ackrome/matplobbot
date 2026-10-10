# Onboarding destination regression

Loads the complete BaseManager/filters from their current source and uses the
actual aiogram Router and MemoryStorage FSM. External manager imports and outbound
Telegram methods are replaced so the suite cannot send messages or fetch optional
library data. Unlike direct-handler tests, registration order participates.

`OnboardingDestinationTests` checks all six supported private deep links through
language selection and finish/skip, human identity preservation, direct routing
for returning users, destination clearing on restart and private-data exclusion
from groups. Run `.venv/Scripts/python.exe -m unittest tests.test_onboarding_destinations -v`.
Feature-detour regressions execute the actual schedule search and LaTeX completion
methods against the same FSM, then finish onboarding. A controlled Redis adapter
models the separate destination key and atomic `GETDEL`; concurrent finish/skip
consumes a destination once, other users remain isolated, fresh starts replace or
clear it, and no user settings are rewritten. Redis 7 is required by Compose;
these local tests establish routing/state behavior, not Redis availability.
Dependencies: aiogram and Python unittest/AST. Side effects are in-memory state
and mocks only. Preserve full handler registration in future refactors.
