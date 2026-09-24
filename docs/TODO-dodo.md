# Matplobbot: проверенный технический backlog (`TODO-dodo`)

Дата повторной проверки: 2026-09-24
Проверенная базовая ревизия: `e769006` (`main`)
Статус: актуализирован по текущему коду

## 1. Как читать этот документ

Этот файл содержит только задачи, которые подтверждаются текущим состоянием репозитория, а
также отдельный журнал удалённых или исправленных утверждений. Наличие уязвимого шаблона в
коде считается подтверждением дефекта; утверждения о частоте инцидентов, нагрузке или уже
наблюдавшихся сбоях не считаются доказанными без production-метрик и логов.

Приоритеты:

- **P0** — доступ к чужим данным или иной немедленный security-инцидент.
- **P1** — высокая вероятность потери ключевой функции, уведомления или корректности deploy.
- **P2** — локальный функциональный дефект или существенная проблема надёжности.
- **P3** — улучшение UX, переносимости или сопровождаемости без доказанного текущего сбоя.

## 2. Актуальная сводка

| Категория | P0 | P1 | P2 | P3 | Всего |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bugs & Runtime Failures | 0 | 0 | 0 | 0 | 0 |
| Security & Data Isolation | 0 | 0 | 0 | 0 | 0 |
| Product & Business Logic | 0 | 0 | 0 | 0 | 0 |
| UI/UX & Frontend | 0 | 0 | 0 | 5 | 5 |
| Technical Debt & Architecture | 0 | 0 | 0 | 2 | 2 |
| Database & Performance | 0 | 0 | 0 | 1 | 1 |
| DevOps & Infrastructure | 0 | 0 | 0 | 2 | 2 |
| **Итого активных** | **0** | **0** | **0** | **10** | **10** |

В первоначальном варианте было описано 33, а не 39 уникальных задач. Шесть пунктов исключены
из активного backlog после проверки, два пункта Sprint 1, шесть пунктов Sprint 2 и десять пунктов
Sprint 3 выполнены. CSP-hardening был выделен из SEC-02 в отдельный SEC-04 и также закрыт в
Sprint 3. Причины и результаты приведены в разделе 7.

## 3. P0 — активных задач нет

SEC-01 закрыт в Sprint 1 и перенесён в журнал выполненных пунктов.

## 4. P1 — активных задач нет (Sprint 2 выполнен)

Ниже сохранены исходные формулировки и критерии приёмки закрытых задач Sprint 2. Реализация и
проверки завершены 2026-09-24; сводка результата добавлена в раздел 7.

### BUG-01: ZIP-экспорт Studio ломается на Unicode-имени проекта

- **Файл:**
  [`fastapi_stats_app/routers/studio_router.py`](../fastapi_stats_app/routers/studio_router.py)
- **Подтверждение:** `str.isalnum()` сохраняет кириллицу в `filename=...`, тогда как заголовки
  Starlette кодируются в Latin-1. Для имени вроде «Курсовая работа» возможен
  `UnicodeEncodeError`.
- **Исправление:** формировать ASCII fallback в `filename` и UTF-8 значение в `filename*` по
  RFC 5987/6266.
- **Критерии приёмки:** интеграционный тест скачивает ZIP проекта с кириллицей, кавычками и
  пробелами; заголовок валиден и содержит безопасное имя.

### BUG-02: production Nginx не проксирует WebSocket статистики

- **Файлы:**
  [`main_site_frontend/default.conf`](../main_site_frontend/default.conf),
  [`main_site_frontend/js/stats.js`](../main_site_frontend/js/stats.js)
- **Подтверждение:** Nginx содержит только `location /api/` и SPA fallback; запрос `/ws/...`
  получает HTML вместо upgrade. Клиент строит URL только из `window.location.host`, игнорируя
  настраиваемую базу API.
- **Исправление:** добавить `/ws/` proxy с заголовками Upgrade/Connection и формировать WS URL
  из того же runtime API base, что используется REST-клиентом. Зафиксировать один контракт
  маршрутизации для same-origin и отдельного API-домена.
- **Критерии приёмки:** smoke-тест проходит `101 Switching Protocols` через frontend Nginx и
  через production-домен; reconnect не создаёт параллельные сокеты.

### BUG-04: уведомление об изменении расписания теряется после ошибки Telegram

- **Файл:** [`scheduler_app/jobs.py`](../scheduler_app/jobs.py)
- **Подтверждение:** кэш и `last_schedule_hash` обновляются до рассылки. Сырой HTTP-клиент
  возвращает `None` для любого non-200, не обрабатывает `429 retry_after`, а результат отправки
  в `check_for_schedule_updates()` не проверяется. Следующий запуск уже не увидит изменение.
- **Исправление:** ввести устойчивый outbox/статус доставки по уникальной паре
  `(изменение, user_id, entity)`; для 429 соблюдать `retry_after`, для транспортных сбоев делать
  ограниченные повторы с backoff. Хэш источника и статус доставки не должны быть одним
  маркером.
- **Критерии приёмки:** тесты на 429, timeout и частично успешную рассылку доказывают повтор
  только недоставленных сообщений без дублей успешно доставленных.

### BUG-05: ежедневная рассылка не использует кэш при сбое RUZ

- **Файл:** [`scheduler_app/jobs.py`](../scheduler_app/jobs.py)
- **Подтверждение:** `send_daily_schedules()` обращается к RUZ напрямую; ошибка переводит всю
  сущность в failed и не вызывает `get_cached_schedule()`.
- **Исправление:** использовать последний валидный DB-кэш, если live-запрос не удался, и явно
  помечать сообщение временем последней проверки. Не отправлять кэш, если он отсутствует или
  не соответствует запрошенной сущности.
- **Критерии приёмки:** тесты покрывают live success, stale fallback и отсутствие обоих
  источников; сбой одной сущности не отменяет остальные рассылки.

### BUG-07: naive timestamp записывается в timezone-aware поле кэша расписания

- **Файлы:**
  [`shared_lib/database.py`](../shared_lib/database.py),
  [`shared_lib/services/schedule_freshness.py`](../shared_lib/services/schedule_freshness.py)
- **Подтверждение:** несколько upsert-путей записывают `datetime.datetime.now()` в
  `CachedSchedule.updated_at`, а freshness-код трактует любой naive timestamp как UTC. Это
  зависит от timezone процесса/драйвера и может дать сдвиг либо ошибку сравнения.
- **Исправление:** записывать `datetime.datetime.now(datetime.UTC)` во всех путях обновления
  кэша. Перед миграцией старых данных проверить тип колонки, timezone сессии PostgreSQL и
  фактические значения: `TIMESTAMP WITH TIME ZONE` уже хранит абсолютный момент, а слепая
  повторная конвертация может создать новый сдвиг. Исправлять исторические строки только если
  затронутый диапазон можно доказуемо идентифицировать.
- **Критерии приёмки:** тесты с UTC и `Europe/Moscow` дают одинаковый возраст кэша; из БД
  возвращается aware datetime.

### BUG-08: optional production-переменные дописываются в локальный `.env` Jenkins

- **Файл:** [`Jenkinsfile.groovy`](../Jenkinsfile.groovy)
- **Подтверждение:** SSH heredoc, пишущий `$DEPLOY_PATH/.env`, заканчивается до блоков с
  `PROD_OUTLINE_ACCESS_KEY` и Telegram retry settings. Последующие `>> .env` выполняются в
  workspace Jenkins, а не на app-vm.
- **Исправление:** включить optional-переменные в тот же передаваемый по SSH поток/скрипт и
  атомарно заменить удалённый `.env`; не печатать секреты в лог.
- **Критерии приёмки:** shell-тест или тест шаблона проверяет удалённый путь; post-deploy
  проверка подтверждает наличие заданных ключей без вывода их значений.

## 5. P2 — активных задач нет (Sprint 3 выполнен)

Ниже сохранены исходные формулировки и критерии приёмки закрытых задач Sprint 3. Реализация,
регрессионные тесты и browser QA завершены 2026-09-24; сводка результата добавлена в раздел 7.

### BUG-03: ожидаемый HTTP 404 профиля превращается в 500

- **Файл:**
  [`fastapi_stats_app/routers/stats_router.py`](../fastapi_stats_app/routers/stats_router.py)
- **Подтверждение:** `HTTPException(404)` выбрасывается внутри `try`, затем перехватывается
  общим `except Exception` и заменяется на 500.
- **Исправление:** вынести проверку результата за DB `try` либо отдельно пробрасывать
  `HTTPException`.
- **Критерии приёмки:** отсутствующий пользователь даёт 404; исключение БД даёт 500.

### SEC-03: shared Redis-клиент игнорирует `REDIS_URL`

- **Файлы:**
  [`shared_lib/redis_client.py`](../shared_lib/redis_client.py),
  [`shared_lib/celery_app.py`](../shared_lib/celery_app.py)
- **Подтверждение:** Celery использует `REDIS_URL`, а `RedisClient` собирается только из
  `REDIS_HOST`/`REDIS_PORT`. Пароль, TLS, номер БД и дополнительные URL-параметры расходятся
  между сервисами.
- **Исправление:** предпочитать `ConnectionPool.from_url(REDIS_URL, decode_responses=True)`,
  сохранив `REDIS_HOST`/`REDIS_PORT` как совместимый fallback.
- **Критерии приёмки:** тесты URL с паролем, нестандартной DB и `rediss://`; Celery и shared
  client используют эквивалентную конфигурацию.

### SEC-04: CSP для Studio требует отдельного совместимого профиля

- **Файлы:**
  [`main_site_frontend/studio.html`](../main_site_frontend/studio.html),
  [`main_site_frontend/default.conf`](../main_site_frontend/default.conf)
- **Контекст:** основной XSS-вектор SEC-02 закрыт санитизацией. Однако Studio всё ещё содержит
  inline script/style и обработчики событий, загружает Marked/KaTeX/Mermaid/Monaco с CDN, а
  Monaco требует отдельной проверки `worker-src` и `unsafe-eval`. Немедленное включение
  формально строгой CSP сломает редактор; политика с безусловными `unsafe-inline` и широкими
  источниками не является надёжным вторым уровнем защиты.
- **Исправление:** убрать inline JavaScript и обработчики в существующие versioned assets,
  определить минимальные `script-src`, `style-src`, `worker-src`, `connect-src`, `img-src` и
  `frame-src`, затем сначала собрать нарушения через `Content-Security-Policy-Report-Only` и
  после браузерной проверки включить enforcing header. CDN-зависимости закрепить и снабдить
  SRI либо раздавать локально.
- **Критерии приёмки:** Studio, Monaco, KaTeX, Mermaid, Telegram Web App и compile preview
  работают без CSP violations; inline script и event-handler payload блокируются даже при
  искусственном обходе DOMPurify; production-ответ `/studio` содержит enforcing CSP.

### PROD-01: FSM-состояния Aiogram хранятся только в процессе

- **Файл:** [`bot/main.py`](../bot/main.py)
- **Подтверждение:** `Dispatcher()` создаётся без storage, поэтому незавершённые диалоги
  сбрасываются при deploy/restart.
- **Исправление:** использовать `RedisStorage` с общей Redis-конфигурацией, namespace и TTL;
  корректно закрывать storage при остановке.
- **Критерии приёмки:** состояние, созданное до перезапуска экземпляра приложения, читается
  после него; `/cancel` и TTL удаляют старые состояния.

### ARCH-01: WeasyPrint выполняется синхронно внутри async endpoint

- **Файл:**
  [`fastapi_stats_app/routers/stats_router.py`](../fastapi_stats_app/routers/stats_router.py)
- **Подтверждение:** `export_user_actions()` напрямую вызывает синхронный
  `_build_weekly_pdf_bytes()`.
- **Исправление:** `await asyncio.to_thread(_build_weekly_pdf_bytes, weekly_html)` либо Celery.
  Важно: вариант `to_thread(HTML(...).write_pdf)` неверен — он вызывает `write_pdf()` до
  передачи управления в thread.
- **Критерии приёмки:** во время тестового медленного рендера event loop продолжает обслуживать
  параллельный health/request; rate limit сохраняется.

### BUG-06: сообщения предложения сокращения затираются между администраторами

- **Файлы:**
  [`scheduler_app/jobs.py`](../scheduler_app/jobs.py),
  [`bot/handlers/admin.py`](../bot/handlers/admin.py),
  [`bot/handlers/suggestions.py`](../bot/handlers/suggestions.py)
- **Подтверждение:** каждый проход admin-цикла перезаписывает один Redis key списком из одного
  сообщения. Обработчик затем итерирует `messages`, но фактически редактирует только сообщение,
  на котором кликнули, несмотря на комментарий «ALL admins».
- **Исправление:** атомарно сохранять все `(chat_id, message_id)` (Redis list/set или транзакция),
  после решения обновлять каждое сообщение и только затем удалять состояние.
- **Критерии приёмки:** тест с двумя администраторами подтверждает обновление обеих кнопок и
  идемпотентность второго клика.

### BUG-09: HTML-конвертер Studio пропускает неподдерживаемые Telegram-теги

- **Файл:**
  [`bot/services/document_renderer.py`](../bot/services/document_renderer.py)
- **Подтверждение:** конвертация построена на точных `str.replace`; теги с атрибутами и
  неизвестные элементы остаются в тексте для `parse_mode=HTML`.
- **Исправление:** разобрать HTML стандартным parser/BeautifulSoup, разрешить только Telegram
  HTML-теги и допустимые атрибуты, неизвестные элементы превратить в безопасный текст.
- **Критерии приёмки:** тесты с атрибутами, вложенными списками, таблицами, ссылками и
  неизвестными тегами; результат принимается Telegram parser либо безопасно отправляется как
  plain text.

### UX-06: одиночный `.ics` использует TZID без `VTIMEZONE`

- **Файл:**
  [`main_site_frontend/js/schedule_render.js`](../main_site_frontend/js/schedule_render.js)
- **Подтверждение:** событие содержит `DTSTART;TZID=Europe/Moscow`, но календарь не содержит
  `VTIMEZONE`.
- **Исправление:** предпочтительно конвертировать время в UTC и выдавать `DTSTART:...Z` /
  `DTEND:...Z`; если сохраняется TZID, добавить корректный `VTIMEZONE`. Не копировать вручную
  неполное описание timezone.
- **Критерии приёмки:** импорт в Outlook, Apple Calendar и Google Calendar сохраняет время
  занятия; валидатор iCalendar не сообщает об ошибках.

### ARCH-03: Celery tasks зависят от абсолютного `/app/bot`

- **Файл:** [`shared_lib/tasks.py`](../shared_lib/tasks.py)
- **Подтверждение:** пути Pandoc, Puppeteer и шаблонов строятся от `BASE_DIR = "/app/bot"`, что
  мешает локальному запуску и изолированным тестам.
- **Исправление:** ввести `APP_TEMPLATES_DIR` с безопасным container default либо определять
  корень от `Path(__file__)`; валидировать обязательные файлы при старте worker.
- **Критерии приёмки:** path-resolution тест работает в checkout и в worker image.

### OPS-02: у Celery worker нет healthcheck

- **Файлы:**
  [`docker-compose.yml`](../docker-compose.yml),
  [`docker-compose.prod.yml`](../docker-compose.prod.yml)
- **Подтверждение:** `mpb-worker` не имеет healthcheck в обоих Compose-файлах.
- **Исправление:** добавить ограниченный по времени `celery inspect ping` или эквивалентный
  probe, а также внешний alert по длине очереди. Сам статус `unhealthy` в Compose не
  перезапускает контейнер, поэтому healthcheck не заменяет мониторинг и task time limits.
- **Критерии приёмки:** parity-тест проверяет probe в обоих Compose; зависший/остановленный
  worker становится unhealthy, нормальный отвечает в пределах timeout.

## 6. P3 — UX, переносимость и измеряемый технический долг

### UX-02: нетекстовый ответ в поиске расписания получает сообщение об ошибке времени

- **Файл:** [`bot/handlers/schedule.py`](../bot/handlers/schedule.py)
- **Подтверждение:** когда `message.text` отсутствует, `handle_search_query()` отвечает строкой
  `schedule_invalid_time_format`, хотя обработчик ожидает название группы или преподавателя.
- **Исправление:** добавить отдельную локализованную подсказку о допустимом текстовом запросе;
  не переиспользовать валидацию времени.
- **Критерии приёмки:** голосовое сообщение, стикер и фото получают понятную подсказку, состояние
  поиска сохраняется для следующего текстового ответа.

### UX-03: основная Reply-клавиатура перегружена

- **Файл:** [`bot/keyboards.py`](../bot/keyboards.py)
- **Подтверждение:** к Web App-кнопкам добавляются все доступные slash-команды по две в ряд,
  используется `one_time_keyboard=True`.
- **Статус:** релевантная UX-гипотеза, но не runtime bug. Перед переделкой проверить реальные
  сценарии и частоту использования команд.
- **Рекомендация:** оставить 2–3 верхнеуровневых действия, остальное перенести в inline-меню;
  отдельно решить, должна ли клавиатура скрываться после выбора.

### UX-04: avatar proxy выбирает минимальный размер Telegram-фото

- **Файл:**
  [`fastapi_stats_app/routers/stats_router.py`](../fastapi_stats_app/routers/stats_router.py)
- **Подтверждение:** используется `photos[0][0]`; Telegram возвращает размеры по возрастанию.
- **Исправление:** выбирать `photos[0][-1]`, сохранив существующий bounded cache и fallback.
- **Критерии приёмки:** тест проверяет выбор последнего `file_id`.

### UX-05: ZIP blob URL не освобождается после скачивания

- **Файл:** [`main_site_frontend/js/studio.js`](../main_site_frontend/js/studio.js)
- **Подтверждение:** `downloadZIP()` создаёт object URL и не вызывает `URL.revokeObjectURL()`.
- **Исправление:** сохранить URL в переменную и отозвать после клика (с небольшой задержкой для
  браузерной совместимости).
- **Уточнение:** это ограниченная утечка на одно скачивание, а не доказанная причина OOM.

### UX-07: production username бота захардкожен во frontend

- **Файлы:**
  [`main_site_frontend/login.html`](../main_site_frontend/login.html),
  [`main_site_frontend/js/calendar_sync.js`](../main_site_frontend/js/calendar_sync.js)
- **Подтверждение:** Telegram Login Widget и fallback deeplink содержат `matplobbot`.
- **Исправление:** внедрять public runtime config при сборке/старте. Для Login Widget конфиг
  должен быть известен до загрузки widget script либо сам script нужно создавать динамически.
- **Критерии приёмки:** staging указывает только на staging-бота, production — на production.

### ARCH-02: `shared_lib/database.py` остаётся чрезмерно крупным модулем

- **Файл:** [`shared_lib/database.py`](../shared_lib/database.py)
- **Исправление исходной формулировки:** файл содержит около 1850 строк, но заявленных в старом
  тексте классов `ScheduleManager`, `SettingsManager`, `UserManager` в нём нет;
  `bot/handlers/base.py` содержит около 510, а не 900+ строк. Циклы импортов не доказаны.
- **Рекомендация:** постепенно выделять тематические repository/service-модули за совместимым
  фасадом и только вместе с unit-тестами. Не делать одномоментный DI-rewrite без измеримой цели.

### PERF-03: конфигурация DB pool требует hardening, а не первичного добавления

- **Файл:** [`shared_lib/database.py`](../shared_lib/database.py)
- **Исправление исходной формулировки:** `pool_size=20` и `max_overflow=10` уже заданы; заявленная
  ошибка starvation логами не подтверждена.
- **Рекомендация:** добавить настраиваемые через env `pool_pre_ping`, `pool_recycle` и timeout,
  затем подобрать размеры по метрикам PostgreSQL/SQLAlchemy. Не увеличивать пул вслепую для
  каждого replica.

### ARCH-04: mypy gate покрывает только небольшую часть проекта и работает permissive

- **Файлы:**
  [`pyproject.toml`](../pyproject.toml),
  [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml)
- **Исправление исходной формулировки:** проверенные модули уже используют современные generic
  types; смешение `typing.Dict`/`Optional` не воспроизводится. Реальный долг — малый список
  файлов в CI и разрешённые untyped/incomplete definitions.
- **Рекомендация:** расширять mypy coverage пакет за пакетом и ужесточать настройки без
  массового `Any`/`ignore`.

### OPS-01: `network_mode: host` ограничивает переносимость Caddy

- **Файлы:**
  [`docker-compose.yml`](../docker-compose.yml),
  [`docker-compose.prod.yml`](../docker-compose.prod.yml),
  [`Caddyfile`](../Caddyfile)
- **Уточнение:** production-топология намеренно проксирует host-bound порты; это не доказанный
  production-сбой. Ограничение актуально для Docker Desktop и локального запуска Caddy.
- **Рекомендация:** либо вынести Caddy в production profile, либо отдельно спроектировать
  bridge-сеть и публикацию 80/443. Не менять production topology только ради симметрии dev.

### OPS-03: базовый worker image воспроизводим лишь частично

- **Файл:** [`Dockerfile.base-worker`](../Dockerfile.base-worker)
- **Исправление исходной формулировки:** Mermaid CLI уже зафиксирован версией. Плавающими
  остаются `node:22-slim` без digest и версии apt-пакетов.
- **Рекомендация:** закрепить base image по digest и выполнять контролируемые обновления; для
  Debian использовать snapshot/lock strategy, если бит-в-бит воспроизводимость действительно
  нужна. Ручное pinning десятков apt-пакетов без snapshot может сделать security updates хуже.

## 7. Исключённые или уже выполненные пункты

| Исходный ID | Решение | Причина |
| --- | --- | --- |
| SEC-01 | Выполнен в Sprint 1 | Добавлена зависимость `require_ws_admin`: `/ws/stats/total_actions` проверяет роль до `accept()` и отклоняет обычного пользователя кодом `1008`. Интеграционные тесты проверяют отказ без payload и успешное подключение администратора. |
| SEC-02 | Выполнен в Sprint 1; CSP выделен в SEC-04 | Markdown проходит через закреплённый DOMPurify с allow-list до вставки в DOM, ошибки выводятся через `textContent`, Mermaid работает в strict mode. Статические и браузерные XSS-проверки покрывают script, event-handler, `javascript:` и SVG payload; разрешённый Markdown сохраняется. |
| BUG-01/02/04/05/07/08 | Выполнены в Sprint 2 | ZIP-экспорт использует RFC 6266 `filename`/`filename*`; frontend Nginx и runtime-конфигурация поддерживают WebSocket с проверкой `101`; уведомления об изменениях проходят через атомарный PostgreSQL outbox и ограниченные Telegram retry; ежедневная рассылка использует помеченный временем DB-cache fallback; все записи времени кэша стали UTC-aware; Jenkins атомарно формирует полный удалённый `.env` и проверяет имена ключей без вывода секретов. Добавлена миграция `f5b6c7d8e9f0` и регрессионные тесты. |
| BUG-03/06/09 | Выполнены в Sprint 3 | Отсутствующий stats-профиль возвращает 404, а DB-сбой — 500; ссылки на сообщения предложения атомарно накапливаются в Redis set, решение защищено коротким lock и обновляет сообщения всех администраторов; HTML Studio разбирается стандартным parser и сводится к безопасному Telegram allow-list с обработкой списков, таблиц, ссылок и неизвестных тегов. |
| SEC-03/04 | Выполнены в Sprint 3 | Shared Redis и Celery используют один `REDIS_URL` с поддержкой password/TLS/DB и host/port fallback. Studio удалил inline script/style/event attributes, закрепил CDN-версии с SRI, получил отдельный enforcing CSP в Nginx и успешно прошёл browser QA для Monaco, KaTeX, Mermaid и Telegram WebApp; искусственные inline script/handler не исполняются. |
| PROD-01/ARCH-01/ARCH-03 | Выполнены в Sprint 3 | Aiogram FSM хранится в namespaced RedisStorage с TTL и корректным закрытием; WeasyPrint PDF вынесен через `asyncio.to_thread` без потери rate limit; worker resources разрешаются из checkout или `/app/bot`, могут переопределяться через `APP_BOT_DIR`/`APP_TEMPLATES_DIR` и валидируются при старте процесса. |
| UX-06/OPS-02 | Выполнены в Sprint 3 | Одиночный iCalendar event экспортирует московское время как UTC `DTSTART/DTEND ...Z`; worker получил одинаковый bounded `celery inspect ping` healthcheck в обоих Compose, а scheduler health публикует глубину очереди и возвращает 503 при пороге `CELERY_QUEUE_ALERT_THRESHOLD` для внешнего мониторинга. |
| PROD-02 | Исключён как текущий дефект | Установленная версия APScheduler уже использует `coalesce=True` и `max_instances=1` по умолчанию. Распределённый lock понадобится при запуске нескольких scheduler replicas — такого topology сейчас нет. |
| UX-01 | Исключён | Защищённый `GET /` относится к API-приложению и намеренно ведёт в admin stats. Публичный корень сайта обслуживается отдельным Nginx. Это не ошибка входа нового посетителя на сайт. |
| PERF-01 | Выполнен / исходное утверждение неверно | У `UserAction` есть индексы по `user_id`, `action_type`, `timestamp` и составной `(user_id, timestamp)`; существует Alembic migration `f2c63d4e5f60`. Новый `(timestamp, action_type)` можно добавлять только после `EXPLAIN ANALYZE`, а не по предположению о Seq Scan. |
| PROD-03 | Выполнен | API уже возвращает `freshness`, `source_checked_at`, `cache_age_seconds`, `is_offline`; frontend показывает отдельные состояния live/fresh/refreshing/stale fallback. |
| PERF-02 | Исключён | `check_for_schedule_updates()` получает подписки одним запросом и не вызывает `get_user_settings()` для каждого подписчика. Описанный N+1 в указанном пути не воспроизводится. |
| ARCH-05 | Исключён | `bot/services/text_utils.py` занимается разбиением Markdown и не содержит заявленной логики форматирования расписания. API уже нормализует `discipline_short`, `discipline_full` и `module`; отличие серверного и UI-представления само по себе не является дублированием business logic. |
| Сводка «39 задач» | Исправлена | В документе фактически было 33 уникальных ID. После исключения шести, выполнения двух задач Sprint 1, шести задач Sprint 2 и девяти исходных задач Sprint 3 осталось 10 исходных P3-задач. Отдельный CSP follow-up SEC-04 также выполнен в Sprint 3. |

## 8. Рекомендуемый порядок выполнения

### Этап 1 — security hotfix

1. [x] SEC-01: admin guard для stats WebSocket.
2. [x] SEC-02: DOMPurify, безопасный вывод ошибок и регрессионные XSS-тесты.

Sprint 1 выполнен 2026-09-24. Совместимый enforcing CSP не маскируется ослабленной политикой и
учтён отдельно как SEC-04.

### Этап 2 — доставка и production correctness

1. [x] BUG-08: корректная удалённая генерация `.env` в Jenkins.
2. [x] BUG-04: outbox/retry для уведомлений об изменениях.
3. [x] BUG-05: cached fallback ежедневной рассылки.
4. [x] BUG-07: единый UTC-aware timestamp contract.
5. [x] BUG-02: WebSocket proxy и runtime URL.
6. [x] BUG-01: Unicode-safe ZIP filename.

Sprint 2 выполнен 2026-09-24. Production smoke для WebSocket начнёт проверять оба маршрута после
следующего Jenkins deploy; код и локальные/интеграционные проверки завершены.

### Этап 3 — локальные дефекты P2

1. [x] BUG-03, SEC-03, SEC-04 и PROD-01.
2. [x] ARCH-01, BUG-06 и BUG-09.
3. [x] UX-06, ARCH-03 и OPS-02.

Sprint 3 выполнен 2026-09-24. Все P2-пункты закрыты кодом и регрессионными тестами; Studio
дополнительно проверен в реальном Chromium на desktop/mobile, включая CSP-блокировку inline
script/event-handler payload. Production CSP и worker healthcheck вступят в силу после deploy.

### Этап 4 — только после метрик или UX-проверки

UX-02/03/04/05/07, ARCH-02/04, PERF-03 и OPS-01/03. Для этих пунктов сначала нужны
пользовательские сценарии, production-метрики или отдельное архитектурное решение; они не
должны блокировать исправление security и доставки уведомлений.
