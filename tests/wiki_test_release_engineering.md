# test_release_engineering.py

Проверки подмены release manifest, immutable digest, migration head, изоляции RC, отказа от повреждённого backup и небезопасного rollback. TestReleaseEngineering не обращается к production или Docker: внешние действия заменены на границе subprocess. Пример: python -m unittest tests.test_release_engineering. Зависимости: unittest, PyYAML и scripts/release_*.py. Дополнять негативные сценарии при изменении manifest формата; реальный runtime подтверждает обязательный rc_acceptance, а не эти unit tests.

Schema tests parse a UTF-8 BOM fixture without executing its deliberate exception
and also parse the current repository's entire migration chain. This catches
source-format assumptions that a synthetic-only fixture can miss.

Worker security regressions cover a single AppArmor selection in generated RC
Compose, omitted selection on no-AppArmor daemons, observed profile preservation,
and a retained-policy probe failure before rollback stops any service or changes
source. These boundary tests complement actual merged Compose and live sandbox
checks on the runner; they do not substitute for kernel compatibility evidence.

The restore regression simulates delayed target database initialization and
requires a successful TCP query before any dump is loaded. The RC database
healthcheck follows the same rule, avoiding the temporary Unix-only setup server.
