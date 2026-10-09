# studio_process.py

Кооперативная отмена компилятора.

## Основные элементы

`run_studio_process` сохраняет контракт subprocess.run и добавляет проверку Redis-маркера конкретной Studio-сборки. `StudioBuildCancelled` превращается задачами в status=cancelled.

## Использование

Worker вызывает `run_studio_process(command, studio_job_id=id, capture_output=True, timeout=50)`. Для старых вызовов без ID используется subprocess.run.

## Зависимости

redis sync client, общий get_redis_url, subprocess, POSIX process groups; вызывать из worker, не event loop API.

## Побочные эффекты и сопровождение

Проверка до запуска и во время communicate, закрытие Redis и очистка процесса при ошибке/таймауте. На POSIX убивается только новая группа компилятора с дочерними процессами. Celery worker не завершается. Windows fallback завершает непосредственный процесс; production worker — Linux. Проверки запускают локальный Python-процесс вместо TeX.
