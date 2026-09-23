# `settings_keyboard.py`

## Purpose

Builds the bot’s private settings keyboard independently from `SettingsManager` routing and callback handling.

## Public API

`SettingsKeyboardFactory.build(user_id)` returns a complete `InlineKeyboardBuilder`. The lower-level `build_display`, `build_latex`, `build_data_management`, and `build_admin` methods support the compatibility facade in `SettingsManager`.

## Usage

Create the factory with the supported language map and admin user IDs, then await `build`. Existing handlers should keep using `SettingsManager.get_settings_keyboard` until its facade is intentionally retired.

## Dependencies and side effects

The factory reads user settings and linked repositories, translates labels through the shared translator, and creates Aiogram button objects. It does not send or edit Telegram messages.

## Maintenance

Keep callback data values synchronized with the handlers registered by `SettingsManager`. Add new keyboard sections here instead of growing the manager again.
