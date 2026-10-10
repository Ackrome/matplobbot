# test_release_engineering.py

Проверки подмены release manifest, immutable digest, migration head, изоляции RC, отказа от повреждённого backup и небезопасного rollback. TestReleaseEngineering не обращается к production или Docker: внешние действия заменены на границе subprocess. Пример: python -m unittest tests.test_release_engineering. Зависимости: unittest, PyYAML и scripts/release_*.py. Дополнять негативные сценарии при изменении manifest формата; реальный runtime подтверждает обязательный rc_acceptance, а не эти unit tests.
