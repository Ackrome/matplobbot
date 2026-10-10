# release_deploy.py

Развёртывает принятый RC manifest, сохраняет последний успешный релиз и откатывает код/конфигурацию/образы. CLI deploy <manifest>, finalize, rollback [--compatible-schema HEAD]. Использует release_manifest/release_backup, Git и Docker Compose. Перед миграцией работающей базы делает consistent backup и останавливает старый scheduler; затем запускает миграции, сервисы, admin bootstrap. finalize вызывается после smoke и сохраняет защищённые snapshot .env/Caddyfile.local и runtime image IDs. rollback без автоматического downgrade или удаления томов; при другой схеме отказывает до явной проверки совместимости. .release-state содержит секреты и игнорируется Git. Не удалять сохранённые образы и backup до окончания окна отката; проверять smoke после rollback.

`preserve-config` запускается Jenkins до замены `.env` и сохраняет старые ключи
шифрования/подписи, включая первый переход на manifest. При незавершённом deploy
rollback выбирает последний успешный current; после успешного релиза — previous.
Повторный finalize после smoke rollback обновляет указатели без downgrade. Полный
порядок восстановления и граница первого legacy-релиза описаны в
`docs/release-runbook.md`.

`prepare <manifest> --candidate <detached-worktree>` проверяет candidate и скачивает
app digests до изменений живого checkout, фиксирует пять здоровых support image IDs,
сохраняет observed-legacy baseline при первом переходе и recovery-tools, создаёт
attempt marker, останавливает все host-bind services и лишь затем переключает Git.
Deploy требует prepare, использует frozen support IDs и `--no-build --pull never`.
Rollback останавливает host binds до checkout, затем повторяет безопасный admin
bootstrap для восстановленного STATS_PASS. Первоначальный support bootstrap выполняется
отдельно; current/previous не следует заменять вручную для обхода проверки схемы.

До marker/stop `probe_worker()` выполняет положительную LaTeX-компиляцию из принятого
worker digest на ядре целевого хоста с production seccomp/ограничениями, network none,
без production env и volumes; проверяет PDF signature и ограничен 120 секундами.
При отказе удаляется только собственный случайный контейнер; старый сайт остаётся жив.
