# product_ui.js

Диалоги и измерения пользовательских сценариев.

## Основные элементы

`MpbUI.dialog`, `prompt`, `confirm` создают native dialog с возвратом фокуса. `start`/`finish` измеряют четыре разрешённых сценария; `t` читает namespace ux.

## Использование

`await MpbUI.confirm(title, message)`; `MpbUI.start("studio_first")` / `finish("studio_first")`.

## Зависимости

frontend_i18n.js, runtime_config.js, native dialog, Performance API и авторизованный `/api/ux/events`.

## Побочные эффекты и сопровождение

Диалоги добавляются в DOM и удаляются при закрытии. Метрики передают только имя сценария и ограниченную длительность; без JWT не отправляются. Ответ сервера не блокирует пользовательское действие.
