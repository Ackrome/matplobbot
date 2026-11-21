# studio_workspace.js

`importZIP()` opens the Studio ZIP dialog. A preflight request shows the file
list, type and main file. A legacy archive exposes editable selectors. The
second request sends the same selected file and its confirmation token, then
opens a separate project in the normal editor. Both opening and confirmation
stay keyboard-accessible, and creation uses the existing Studio save queue.

`manageVersions()` opens a project-scoped dialog to save, inspect, restore and
delete named server versions. A save or restore waits for the current source
through the existing Studio `transition()` queue. The inventory shows only
paths and main/binary flags. Restore asks for a new name, creates a separate
project via `studio_versions_router.py`, and opens the resulting copy. An error
saving the active document stops version creation and restore.

Пользовательские сценарии Студии.

## Основные элементы

`MpbStudioUX` добавляет перенос черновика, менеджер проектов, шаблоны, сравнение версий, историю сборок, переход к ошибке и очередь загрузок.

## Использование

В режиме черновика выбрать «Сохранить как проект». В «Моих проектах» доступны поиск, переименование, копирование и подтверждаемое удаление.

## Зависимости

studio.js transport/transition, studio_session.js, MpbUI, MpbArchive, frontend_i18n и авторизованные Studio API.

## Побочные эффекты и сопровождение

Все изменения используют существующую сериализованную очередь сохранений. Загрузки удерживают ID проекта при повторе. История локальная: последние 20 сборок, результаты сервера доступны 24 часа. Хранятся метаданные и отпечаток, не копия исходников. Отмена остаётся cancelling до подтверждения worker; превью шаблона схематическое, не обещание точного PDF.
