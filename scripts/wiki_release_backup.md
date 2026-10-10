# release_backup.py

Restore readiness executes `SELECT 1` against the configured database over TCP
loopback. PostgreSQL's initial setup server accepts Unix sockets before the target
database is created; `pg_isready` alone can therefore start restore too early.
The TCP query waits for completed initialization and has a two-second connection
timeout inside the bounded readiness loop.

Создаёт PostgreSQL custom-format backup и проверяет восстановление в новом изолированном контейнере. CLI backup --output /secure/backup.dump и restore-drill /secure/backup.dump --output restore.json. Snapshot удерживает экспортированный read-only snapshot для pg_dump и witness(); сравниваются все public-таблицы, число и MD5 отсортированных хэшей JSON-строк, Alembic head и SHA-256 dump. Зависимости: Python stdlib, Docker, PostgreSQL15. Пароли не печатаются; dump/метаданные имеют0600. Restore не принимает production-target, не публикует порты, удаляет только созданный mpb-restore-* контейнер с его томом. Backup содержит персональные данные: хранить вне Git, ограничивать права, шифровать внешнее хранение. При изменении версии PostgreSQL проверить совместимость dump/restore.
