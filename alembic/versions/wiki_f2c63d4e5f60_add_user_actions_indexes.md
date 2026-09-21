# `f2c63d4e5f60_add_user_actions_indexes.py`

## Purpose

Adds indexes used by user-action history, leaderboard, and activity queries.

## Public API

- Alembic `upgrade()` creates indexes for `user_id`, `action_type`, `timestamp`, and `(user_id, timestamp)`.
- Alembic `downgrade()` removes those indexes in reverse dependency order.

## Usage

Run `python -m alembic upgrade head` during deployment. Roll back with the normal Alembic downgrade command if required.

## Dependencies and side effects

Depends on Alembic's `op` object and changes PostgreSQL schema metadata only; it does not rewrite existing rows.

## Maintenance notes

Keep the revision chain after `f1b52c3d4e5f` intact. If query shapes change, update both this migration and the matching SQLAlchemy model indexes.
