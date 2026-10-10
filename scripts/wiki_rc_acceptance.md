# rc_acceptance.py

Запускает обязательный RC-прогон настоящих PostgreSQL15, Redis7, API и Celery worker плюс scheduler-probe. Пример: python scripts/rc_acceptance.py --manifest release-manifest.json --output rc-acceptance.json. --local-image service=tag разрешён только для разработки: отчёт working-tree невозможно принять в релизный manifest. Зависимости: Docker Compose, PyYAML, release_backup, release_manifest. Изолированная internal Docker-сеть, без published ports и production env_file; данные синтетические. Миграции, API restart, компиляции трёх форматов, календарь/ICS, account ownership/export/delete, сессии, Redis Lua и outbox выполняются реально. RUZ заменён предварительно заполненным кэшем, внешний Telegram — локальным HTTP503/200 fixture. finally сохраняет отчёт/логи ошибки и удаляет только ресурсы случайного mpb-rc-* проекта. Расширяя sandbox worker, сохранять его ограничения в build_compose.

Обязательный image gate включает десять worker sandbox tests и все шесть render
paths. Дополнительный restart после logout/logout-all доказывает DB persistence
отзыва; проверяются реальные HTTP password login/429, открытый/новый WebSocket,
Lua client/account/pair budgets, PostgreSQL SKIP LOCKED/CAS/cancellation. Отчёт
содержит Docker image IDs и результат восстановления всех public tables; токены и
секреты в него не попадают. Успешный запуск удаляет только собственный прежний error log.
