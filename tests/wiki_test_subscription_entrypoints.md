# test_subscription_entrypoints.py

Проверки переходов из аккаунта в Telegram и независимой работы общего календаря
без глобальных переменных страницы расписания.

`SubscriptionEntrypointTests` выполняет реальные методы BaseManager/SettingsManager
с AsyncMock для Telegram, FSM и БД. Метод `handler` извлекает AST метода, чтобы
не импортировать необязательные ML-библиотеки всего бота. Проверяются прямые
маршруты добавления/управления, личный чат, ID владельца, пустые и отключённые
подписки, действующие callback-кнопки `sub_open`/`subs_page` и прежний web_settings.

`CalendarHostTests` исполняет calendar_sync.js в Node VM с адаптером аккаунта.
Проверяет загрузку без schedule globals, 401, смену JWT и ответы не по порядку.

```powershell
./.venv/Scripts/python.exe -m unittest tests.test_subscription_entrypoints -v
```

Зависимости: стандартная библиотека Python; Node для фронтенд-проверки (без него
тест явно пропускается). Сеть и настоящий Telegram не используются, файлы и БД
не меняются. AST-тесты проверяют логику методов, но не заменяют проверку регистрации
роутеров и реальный бот; DOM/скриншоты проверять Playwright отдельно.
