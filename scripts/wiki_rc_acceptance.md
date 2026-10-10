# rc_acceptance.py

PostgreSQL readiness uses a real TCP query to the configured database, so the
image's temporary Unix-only initialization server cannot trigger migration early.

Запускает обязательный RC-прогон настоящих PostgreSQL15, Redis7, API и Celery worker плюс scheduler-probe. Пример: python scripts/rc_acceptance.py --manifest release-manifest.json --output rc-acceptance.json. --local-image service=tag разрешён только для разработки: отчёт working-tree невозможно принять в релизный manifest. Зависимости: Docker Compose, PyYAML, release_backup, release_manifest. Изолированная internal Docker-сеть, без published ports и production env_file; данные синтетические. Миграции, API restart, компиляции трёх форматов, календарь/ICS, account ownership/export/delete, сессии, Redis Lua и outbox выполняются реально. RUZ заменён предварительно заполненным кэшем, внешний Telegram — локальным HTTP503/200 fixture. finally сохраняет отчёт/логи ошибки и удаляет только ресурсы случайного mpb-rc-* проекта. Расширяя sandbox worker, сохранять его ограничения в build_compose.

Обязательный image gate включает одиннадцать worker sandbox tests и все шесть render
paths. Дополнительный restart после logout/logout-all доказывает DB persistence
отзыва; проверяются реальные HTTP password login/429, открытый/новый WebSocket,
Lua client/account/pair budgets, PostgreSQL SKIP LOCKED/CAS/cancellation. Отчёт
содержит Docker image IDs и результат восстановления всех public tables; токены и
секреты в него не попадают. Успешный запуск удаляет только собственный прежний error log.

`worker_security.apparmor_security_option` checks the Docker daemon and installed
policy before containers start. The generated worker configuration adds its single
named profile on AppArmor hosts and omits the option on daemons without AppArmor.
The report records the selection. The actual sandbox test suite establishes runtime
loadability, which checking the policy file alone cannot prove. When redirecting
the outer diagnostic command, use a different stdout filename from the report's
`.log` sibling, which the harness owns for failure diagnostics.
