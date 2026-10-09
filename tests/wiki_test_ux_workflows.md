# test_ux_workflows.py

Регрессии API измерений и ZIP.

## Основные элементы

TestJourneyAPI проверяет авторизацию, запрет произвольного контента и привязку владельца; TestArchive проверяет ZIP стандартным zipfile.

## Использование

`.venv/Scripts/python.exe -X utf8 -m unittest tests.test_ux_workflows -v`.

## Зависимости

FastAPI TestClient, mocks, Node для исполнения archive_download.js, Python zipfile.

## Побочные эффекты и сопровождение

Нет реальных пользователей, базы или внешних запросов. ZIP проверяется по байтам, CRC и Unicode путям, дубликаты путей отклоняются. При отсутствии Node архивный тест явно пропускается.
