# archive_download.js

ZIP без зависимости от CDN.

## Основные элементы

`MpbArchive.zip(files)` создаёт ZIP STORE с UTF-8 именами и CRC32. `safePath` нормализует путь; `download` инициирует сохранение Blob.

## Использование

`MpbArchive.download(MpbArchive.zip([{name:"main.tex",text:"source"}]), "project.zip")`; бинарный файл передаётся в `bytes: Uint8Array`.

## Зависимости

TextEncoder, DataView, Blob, URL.createObjectURL.

## Побочные эффекты и сопровождение

Архив строится в памяти: максимум 128 MiB исходных данных и 60000 записей. Дубли путей отклоняются. Относительные имена файлов внутри проекта должны сохраняться, иначе перестанут работать include и картинки. Регрессия test_ux_workflows читает архив стандартным Python zipfile и проверяет CRC.
