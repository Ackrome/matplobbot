# studio_process.py

Кооперативная отмена компилятора.

## Основные элементы

`run_studio_process` сохраняет контракт subprocess.run и добавляет проверку Redis-маркера конкретной Studio-сборки. `StudioBuildCancelled` превращается задачами в status=cancelled.

## Использование

Worker вызывает `run_render_process` из `render_sandbox.py`, который передаёт изолированную команду в `run_studio_process`. Для вызовов без Studio ID тоже используются отдельная группа процессов и очистка по таймауту, но Redis не подключается.

## Зависимости

redis sync client, общий get_redis_url, subprocess, POSIX process groups; вызывать из worker, не event loop API.

## Побочные эффекты и сопровождение

Проверка до запуска и во время communicate, закрытие Redis и очистка процесса при ошибке/таймауте. На POSIX убивается только новая группа компилятора с дочерними процессами. Celery worker не завершается. `capture_output` записывает диагностики во временные файлы и возвращает не более 2 MiB каждого потока; в production размер записи ограничивают RLIMIT_FSIZE и tmpfs. Windows transport завершает непосредственный процесс; серверный renderer на Windows запрещён в `render_sandbox.py`. Проверки transport запускают локальный Python-процесс вместо TeX, реальные Linux sandbox-регрессии находятся в `test_render_sandbox.py`.
