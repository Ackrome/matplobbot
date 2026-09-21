# `test_stats_avatar_security.py`

## Purpose

Regression tests ensuring Telegram bot tokens are not persisted in avatar URLs returned by bot logging and database helpers.

## Public tests

`TestAvatarSecurity` covers logger-generated URLs, leaderboard data, user-profile data, and a mocked successful avatar-proxy response using the shared HTTP configuration.

## Usage

Run `python -m unittest tests.test_stats_avatar_security` from the project root.

## Dependencies and side effects

Uses `unittest`, `AsyncMock`, and SQLAlchemy model objects with mocked sessions. No Telegram or database network calls are made.

## Maintenance notes

Keep these tests separate from endpoint integration tests. When the proxy URL or signing scheme changes, add an endpoint test that verifies a successful image response without exposing the bot token.
