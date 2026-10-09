# ux_router.py

Приём ограниченных измерений UX.

## Основные элементы

`JourneyEvent` разрешает четыре имени и duration_ms от 0 до 3600000, запрещает дополнительные поля. `record_journey` применяет авторизацию и лимит 30 запросов в минуту.

## Использование

POST `/api/ux/events` с Bearer JWT и JSON `{"journey":"studio_first","duration_ms":1800}` возвращает 202.

## Зависимости

FastAPI, Pydantic, rate_limit, product_metrics, WebAccount.

## Побочные эффекты и сопровождение

Не принимает документ, URL, запрос поиска или идентификатор другого пользователя. Метрика записывается best effort; 202 означает приём запроса, не гарантированную запись. Проверки: tests/test_ux_workflows.py.
