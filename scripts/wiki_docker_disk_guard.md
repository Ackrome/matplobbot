# `docker_disk_guard.py`

## Назначение

`docker_disk_guard.py` проверяет свободное место файловой системы и каталога Docker. Каталог Docker включает containerd content store на текущем Docker runtime, поэтому проверка видит хранилище, которое расходуется во время pull и BuildKit-сборок.

При достижении warning-порога скрипт освобождает старый BuildKit-кэш, остановленные контейнеры и образы. Профиль `runner` удаляет неиспользуемые образы старше заданного срока. Профиль `production` удаляет только dangling-образы, чтобы сохранить образы текущего и предыдущего релиза для rollback. Docker volumes не очищаются.

Профиль `runner` также удаляет неактивные `docker-container` Buildx builders старше `--image-age`. Текущий builder и недавно активные builders пропускаются. Это освобождает связанные state volumes, которые обычный `docker builder prune` не удаляет.

## Использование

```bash
python3 scripts/docker_disk_guard.py monitor --profile runner \
  --warn-gib 20 --critical-gib 8

python3 scripts/docker_disk_guard.py monitor --profile production \
  --warn-gib 30 --critical-gib 15
```

Команда печатает одну JSON-строку для GitHub Actions и systemd journal. `check` выполняет только проверку и возвращает код `2` при critical-состоянии. `monitor` и `cleanup` сначала проверяют место, затем выполняют bounded cleanup только при warning или critical. После очистки проверка повторяется.

Каждый запуск берёт неблокирующий `flock` на lock-файл, поэтому два timer-запуска не выполняют очистку одновременно. Путь lock-файла можно изменить через `--lock-file`.

## Зависимости и побочные эффекты

Используются Python standard library, `docker` CLI и доступ к Docker socket. Скрипт не обращается к сети, не читает секреты и не удаляет volumes. Профиль production не удаляет образы с repository tag. Для runner удаление старых неиспользуемых образов должно выполняться только на выделенном self-hosted runner.

## Сопровождение

Пороги задаются аргументами команды и должны оставлять место под временные слои при pull. Не добавляйте `docker system prune --volumes` и не удаляйте containerd snapshots напрямую. При изменении списка cleanup-команд обновляйте проверки workflow и systemd unit.
