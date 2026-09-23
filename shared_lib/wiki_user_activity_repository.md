# `user_activity_repository.py`

## Purpose

Contains the user-profile and action-history queries extracted from the large `shared_lib.database` module. The old public functions remain available through facade wrappers in `database.py`.

## Public functions

- `get_user_profile_data_from_db` returns user metadata and paginated actions.
- `get_user_message_history` returns paginated incoming and outgoing chat messages.
- `get_users_for_action` lists users associated with one action value.
- `get_all_user_actions` returns the complete action history used by exports.

## Usage

Existing code should continue importing these functions from `shared_lib.database` for compatibility. New repository-focused code may import them directly from this module.

## Dependencies and side effects

Functions use an injected SQLAlchemy `AsyncSession` and only read `User` and `UserAction` rows. They do not commit or mutate database state.

## Maintenance

Keep the facade signatures in `database.py` compatible. Add query-specific tests before changing pagination, sorting, action-type mapping, timestamp formatting, or avatar URL sanitization.
