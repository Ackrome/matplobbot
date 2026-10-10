# release_manifest.py

Связывает полный commit, четыре OCI digest, ревизию схемы и SHA-256 файлов развёртывания. CLI create/verify/compose/attest/decode. Пример: python scripts/release_manifest.py verify release-manifest-accepted.json --images --require-rc. Использует стандартную библиотеку, Git и Docker CLI; verify ничего не меняет, другие команды записывают JSON. Не включает секреты. Меняя набор runtime-конфигов, расширяйте RELEASE_FILES и тесты; manifest должен создаваться из чистого commit.
