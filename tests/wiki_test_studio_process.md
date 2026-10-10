# test_studio_process.py

Регрессии отмены worker.

## Основные элементы

TestStudioProcess проверяет отмену до запуска, остановку работающего процесса, таймаут, stdin/stdout через повторные communicate, таймаут без Studio ID/Redis и ограничение возвращаемых диагностик до 2 MiB на поток.

Регрессия разбора TeX-лога проверяет переходы к файлу и строке для формата `-file-line-error`, включая вложенный исходник и безопасное сокращение абсолютного пути.

## Использование

`.venv/Scripts/python.exe -X utf8 -m unittest tests.test_studio_process -v`.

## Зависимости

unittest/mock, production studio_process и Python sys.executable.

## Побочные эффекты и сопровождение

Redis подменён, короткие локальные subprocess реальные. Не запускает TeX и не обращается к рабочей очереди. При изменении POSIX очистки дополнительно проверить дочерние процессы на Linux.
