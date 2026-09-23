# Backlog & Audit Report: Matplobbot

## Реализованные решения PROD-2–7

- **PROD-2:** `user_schedule_subscriptions` теперь хранит профиль, timezone,
  режим доставки, lesson mode и выбранные модули. WebCal и Telegram используют
  одну запись; старый JSON остаётся совместимым read-продолжением, новые Web
  профили пишутся в БД. Уведомления дедуплицируются по `(user, entity)`,
  часовой пояс по умолчанию — `Europe/Moscow`, а API отдаёт карусель GMT±N.
- **PROD-4:** рейтинг `/stats` ведёт на `admin-user.html`; данные страницы
  загружаются только защищённым admin API.
- **PROD-6:** GitHub ссылки нормализуются в `owner/repo@branch`; URL `/tree/...`
  и явная ветка имеют приоритет, отсутствие ветки даёт `main`.
- **PROD-7:** поиск документирован и логируется как PostgreSQL text search;
  векторное хранилище не добавлялось.
- **UX-4:** ручные query-string версии статики не менялись.

## Зафиксированные решения пользователя (21 сентября 2026)

Эти решения уточняют дальнейшую реализацию задач и не означают, что каждая из них уже выполнена.

1. **SEC-5 — Caddy:** разделить публичную конфигурацию из репозитория и локальные/private-маршруты через внешний `Caddyfile.local`; изменение на `app-vm` выполнить по SSH после подтверждения Tailscale.
2. **BUG-5 — inline-состояние:** хранить сопоставления callback-хэшей в Redis с TTL и локальным LRU-кэшем для быстрого доступа; Redis является источником восстановления после перезапуска, а явная очистка кэша удаляет оба слоя.
3. **PROD-2 — расписание Web/Telegram:** профиль календаря и Telegram-подписка — один канонический объект. Настройки Web применяются к Telegram-уведомлениям. Один пользователь имеет один Telegram ID, но может иметь несколько подписок; одинаковые сущности дедуплицируются по сущности, а не по строке подписки. Базовый часовой пояс — `Europe/Moscow` (GMT+3); для другого пояса нужна кнопка-карусель `GMT ± N`; старые записи мигрируются на GMT+3. Telegram отправляет уведомления в личные сообщения и выдаёт iCal/WebCal-ссылку, Web UI выдаёт только ссылку.
   - Под «моделью» здесь понимается не ML-модель, а каноническая модель данных/API: одна запись профиля-подписки с сущностью расписания, фильтрами/модулями, режимом занятий, часовым поясом, временем уведомлений, настройками доставки и секретом календарной ссылки.
4. **PROD-4 — статистика:** строка рейтинга на `/stats` должна вести на отдельную admin-only страницу деталей пользователя; остальные рекомендации по безопасности и экспорту приняты.
5. **PROD-6 — GitHub:** ветка из ссылки или названия репозитория имеет приоритет; если ветка не указана, используется `main`.
6. **PROD-7 — поиск:** оставить PostgreSQL FTS и явно называть его текстовым поиском; векторное хранилище не добавлять.
7. **UX-4:** текущую ручную версионизацию статических ресурсов оставить.
8. **UX-5:** принять рекомендации по единому источнику локализации и проверкам frontend-локалей.
9. **DEBT-1:** принять постепенное сведение двух frontend-поверхностей к статическому frontend.
10. **DEBT-3:** принять поэтапный рефакторинг больших объектов с совместимым фасадом.
11. **DEBT-4:** принять миграцию на стандартную JWT-библиотеку с проверками claims и тестами.
12. **OPS-1:** текущую политику запуска контейнеров оставить без изменения.
13. **OPS-2 — `compose.dev`:** отдельный `compose.dev` не нужен; оставить `docker-compose.yml` самостоятельной локальной конфигурацией, а `docker-compose.prod.yml` — самостоятельной production-конфигурацией, используемой `deploy.sh`, и проверять оба сценария.
14. **OPS-3:** принять рекомендации по структурированному логированию и уровням через env, сохранив Docker-ротацию логов.

> Дата ревью: 17 сентября 2026 г.
> Статус: Комплексный аудит (Product, UI/UX, Security, Backend, Database, Frontend, DevOps)

---

## 1. Безопасность и критические уязвимости (Security & Critical)

### ✅ SEC-1 (ИСПРАВЛЕНО): Утечка `BOT_TOKEN` через публичные URL аватарок пользователей
- **Приоритет:** CRITICAL (P0)
- **Файлы:** [bot/logger.py](file:///c:/Projects/matplobbot/bot/logger.py#L41), [shared_lib/schemas.py](file:///c:/Projects/matplobbot/shared_lib/schemas.py), [fastapi_stats_app/routers/stats_router.py](file:///c:/Projects/matplobbot/fastapi_stats_app/routers/stats_router.py)
- **Проблема:** В `_get_avatar_pic_url` формируется ссылка вида:
  `f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"`.
  Этот URL сохраняется в таблицу `users.avatar_pic_url` в базе данных и затем отдаётся через публичные API эндпоинты (`/api/auth/me`, `/api/stats/leaderboard`, `/api/stats/users/{id}`) на клиент, где рендерится в теге `<img src="...">`.
- **Влияние:** Любой авторизованный пользователь или читатель API-ответов со списком лидеров может извлечь полный приватный токен Telegram-бота (`BOT_TOKEN`) и получить неограниченный контроль над ботом.
- **Рекомендация:**
  1. Никогда не сохранять `bot.token` в строках БД.
  2. Для отображения аватарок проксировать загрузку через внутренний эндпоинт бота (`/api/users/{id}/avatar`), либо отдавать сгенерированные SVG-аватарки/инициалы, либо кэшировать бинарный файл локально/в S3 без раскрытия токена.

---

### ✅ SEC-2 (ИСПРАВЛЕНО): Хранимая межсайтовая сценария (Stored XSS) в дашборде статистики
- **Приоритет:** CRITICAL (P0)
- **Файлы:**
  - [main_site_frontend/js/stats.js](file:///c:/Projects/matplobbot/main_site_frontend/js/stats.js)
  - [main_site_frontend/js/admin-user.js](file:///c:/Projects/matplobbot/main_site_frontend/js/admin-user.js)
- **Исправление:** Единый статический frontend экранирует пользовательские поля до вставки в HTML. Удалённые Jinja-дашборд и его legacy JS больше не являются отдельной поверхностью рендеринга.
- **Проблема:** Пользовательские данные (имя Telegram-аккаунта `full_name`, никнейм `username` и текст сообщений, отправленных боту `action_details`) напрямую конкатенируются в HTML-строки и вставляются в DOM через `innerHTML` без вызова функции экранирования `escapeHtml`.
- **Влияние:** Любой пользователь Telegram может отправить сообщение боту с XSS-нагрузкой (например, `<img src=x onerror="...">`) или указать такое имя в профиле. Когда администратор открывает дашборд статистики или историю сообщений, скрипт выполняется в браузере администратора с правами доступа к `localStorage.getItem("jwt_token")`, что приводит к краже административной сессии.
- **Рекомендация:**
  1. Использовать `escapeHtml()` при любой интерполяции строковых данных в шаблоны `innerHTML`.
  2. Либо использовать безопасное присваивание через `element.textContent` / `document.createTextNode()`.

---

### ✅ SEC-3 (ИСПРАВЛЕНО): RCE и чтение произвольных файлов при компиляции проектов в Celery Worker
- **Приоритет:** HIGH (P1)
- **Файлы:** [shared_lib/tasks.py](file:///c:/Projects/matplobbot/shared_lib/tasks.py#L574-L583), [Dockerfile.worker](file:///c:/Projects/matplobbot/Dockerfile.worker)
- **Проблема:**
  1. В `compile_project_task` запуск `latexmk` выполняется без параметра `-no-shell-escape` и без проверки на команды типа `\write18`, `\openout`, `\newwrite` (в отличие от `compile_full_latex_task`).
  2. Даже при выключенном shell escape стандартные команды LaTeX `\input{/etc/passwd}` или `\input{/app/.env}` позволяют злоумышленнику включить содержимое конфиденциальных файлов контейнера в выходной PDF.
  3. Контейнер воркера запускается от пользователя `root`.
- **Влияние:** Утечка секретов окружения (`.env`, приватные ключи, токены) или удаленное выполнение кода на сервере через движок TeX.
- **Рекомендация:**
  1. Добавить обязательный флаг `-no-shell-escape` в вызов `latexmk` в `compile_project_task`.
  2. Добавить валидацию и запрет команд `\write18`, `\openout`, `\input` абсолютных путей.
  3. В `Dockerfile.worker` создать и использовать непривилегированного пользователя (`USER appuser`).
  4. Рассмотреть изолированный запуск компиляции (chroot, firejail или docker-in-docker с read-only fs).

---

### ✅ SEC-4 (ИСПРАВЛЕНО): Дефолтные учетные данные администратора `admin:admin`
- **Приоритет:** HIGH (P1)
- **Файл:** [fastapi_stats_app/config.py](file:///c:/Projects/matplobbot/fastapi_stats_app/config.py#L77-L78)
- **Проблема:** Значения по умолчанию для доступа к дашборду: `STATS_USER = os.getenv("STATS_USER", "admin")` и `STATS_PASS = os.getenv("STATS_PASS", "admin")`.
- **Влияние:** Если в production-окружении забыли явно переопределить переменные, панель администратора с доступом к рассылкам, статистике и управлению учетными записями доступна с базовым логином/паролем.
- **Рекомендация:** Блокировать запуск приложения в production-режиме, если `STATS_PASS` равен `admin` или не задан.

---

### ✅ SEC-5 (ИСПРАВЛЕНО): Утечка внутренней топологии сети и домашних сервисов в `Caddyfile`
- **Приоритет:** MEDIUM (P2)
- **Файл:** [Caddyfile](file:///c:/Projects/matplobbot/Caddyfile#L10-L33)
- **Проблема:** В публичном репозитории в файле `Caddyfile` захардкожены приватные IP-адреса и порты домашней локальной сети:
  - `kg.ivantishchenko.ru -> 192.168.1.30:3000`
  - `ftv.ivantishchenko.ru -> 192.168.1.16:8765`
  - `immich.ivantishchenko.ru -> 192.168.1.33:2283`
  - `auth.ivantishchenko.ru -> 192.168.1.33:9091`
  - `dl.ivantishchenko.ru -> 192.168.1.33:8080`
- **Влияние:** Раскрытие внутренней инфраструктуры владельца и связывание приватных сервисов с открытым кодом проекта.
- **Рекомендация:** Вынести конфигурацию персональных доменов и локальных прокси во внешний, не отслеживаемый репозиторием `Caddyfile.local` (через директиву `import`).

---

### ✅ SEC-6 (ИСПРАВЛЕНО): Отсутствие санитизации имен файлов при загрузке в Studio
- **Приоритет:** MEDIUM (P2)
- **Файл:** [fastapi_stats_app/routers/studio_router.py](file:///c:/Projects/matplobbot/fastapi_stats_app/routers/studio_router.py#L294)
- **Проблема:** В `upload_asset` имя загружаемого файла `file_path=file.filename` используется без нормализации (`secure_filename`).
- **Влияние:** Возможны спецсимволы, проблемы с кодировками или попытки Path Traversal при передаче специфических путей.
- **Рекомендация:** Пропускать `file.filename` через функцию безопасного имени (оставляя только базовое имя с валидным расширением).

---

## 2. Баги и ошибки времени выполнения (Bugs & Runtime Failures)

### ✅ BUG-1 (ИСПРАВЛЕНО): Падение FastAPI при старте без `JWT_SECRET_KEY`
- **Приоритет:** HIGH (P1)
- **Файлы:** [fastapi_stats_app/auth.py](file:///c:/Projects/matplobbot/fastapi_stats_app/auth.py#L25-L32), [README.md](file:///c:/Projects/matplobbot/README.md#L101-L111)
- **Проблема:** В `auth.py` на уровне модуля выполняется `SECRET_KEY = _get_jwt_secret_key()`, который выбрасывает `RuntimeError("JWT_SECRET_KEY environment variable must be set")`. При этом в `README.md` в секции Minimal `.env` переменная `JWT_SECRET_KEY` не указана вовсе.
- **Влияние:** Разработчик, следующий инструкциям из `README.md`, получает аварийный останов контейнера `mpb-fastapi-stats` при первом же запуске.
- **Рекомендация:**
  1. Добавить `JWT_SECRET_KEY` в пример в `README.md` и `.env.example`.
  2. В `auth.py` генерировать случайный временный ключ для разработки с предупреждением в лог, если переменная не задана.

---

### ✅ BUG-2 (ИСПРАВЛЕНО): Разрыв HTML-тегов при разбиении длинных сообщений в Telegram
- **Приоритет:** HIGH (P1)
- **Файл:** [scheduler_app/jobs.py](file:///c:/Projects/matplobbot/scheduler_app/jobs.py#L89-L108)
- **Проблема:** Функция `send_telegram_message` делит текст сообщения на части простым слайсом строки: `text[i : i + TELEGRAM_MESSAGE_LIMIT]`. Если срез происходит посередине тега `<b>`, `<a href="...">` или `<code>`, сообщение становится невалидным HTML.
- **Влияние:** Telegram API отклоняет отправку с ошибкой `400 Bad Request: can't parse entities: tag <b> is not closed`, и пользователи не получают утренние/вечерние уведомления о расписании.
- **Рекомендация:** Использовать умное разбиение по границам параграфов/строк с закрытием незакрытых тегов в текущем чанке и повторным открытием в следующем, либо использовать готовую библиотеку (или существующий хелпер `split_telegram_message` из `broadcast_service.py`).

---

### ✅ BUG-3 (ИСПРАВЛЕНО): Падение отправки формул LaTeX в боте из-за устаревшего Markdown
- **Приоритет:** MEDIUM (P2)
- **Файл:** [bot/handlers/rendering.py](file:///c:/Projects/matplobbot/bot/handlers/rendering.py#L64-L66)
- **Проблема:** Подпись к формуле отправляется с `parse_mode="markdown"`, а формула вставляется напрямую в строку шаблона:
  `caption=translator.gettext(lang, "latex_your_formula", formula=formula)`.
  В LaTeX-формулах почти всегда присутствуют символы `_`, `*`, `[`, `]`.
- **Влияние:** Парсер Telegram Markdown падает с ошибкой `TelegramBadRequest: Can't parse entities: can't find end of italic entity at byte offset ...`, в результате чего отрендеренная картинка не отправляется пользователю.
- **Рекомендация:** Перевести отправку на `parse_mode="HTML"` и экранировать формулу через `html.escape(formula)` внутри тегов `<code>...</code>`.

---

### ✅ BUG-4 (ИСПРАВЛЕНО): Неработающий локальный сайт из-за хардкода production API URL
- **Приоритет:** HIGH (P1)
- **Файлы:**
  - [main_site_frontend/js/runtime_config.js](file:///c:/Projects/matplobbot/main_site_frontend/js/runtime_config.js#L3) (`window.__MPB_API_BASE__ = "https://api.ivantishchenko.ru/api"`)
  - [main_site_frontend/default.conf](file:///c:/Projects/matplobbot/main_site_frontend/default.conf#L11-L21) (отсутствие проксирования `/api/`)
  - [docker-compose.yml](file:///c:/Projects/matplobbot/docker-compose.yml#L148-L157) (не проброшен `default.conf` в nginx)
- **Проблема:**
  1. В `default.conf` настроен только `location /api/cal/`, но запросы на `/api/schedule/`, `/api/auth/` и др. падают в `location /`, возвращая `index.html`.
  2. Чтобы это обойти, в `runtime_config.js` захардкодили внешний адрес `https://api.ivantishchenko.ru/api`.
  3. В `docker-compose.yml` файл `default.conf` даже не примонтирован в контейнер `main-site-frontend`.
- **Влияние:** Локальное окружение не изолировано: локальный веб-сайт шлёт запросы на чужой/удаленный боевой сервер вместо локального контейнера `mpb-fastapi-stats`.
- **Рекомендация:**
  1. Добавить в `default.conf` секцию `location /api/ { proxy_pass http://mpb-fastapi-stats:9583; ... }`.
  2. Изменить `runtime_config.js` по умолчанию на относительный путь `window.__MPB_API_BASE__ = "/api";`.
  3. В `docker-compose.yml` добавить том: `- ./main_site_frontend/default.conf:/etc/nginx/conf.d/default.conf:ro`.

---

### ✅ BUG-5 (ИСПРАВЛЕНО): Потеря состояния инлайн-кнопок при перезапуске бота (`LRUCache`)
- **Приоритет:** MEDIUM (P2)
- **Файлы:** [bot/keyboards.py](file:///c:/Projects/matplobbot/bot/keyboards.py#L54), [bot/handlers/github.py](file:///c:/Projects/matplobbot/bot/handlers/github.py#L507-L510)
- **Проблема:** Хэши путей репозиториев и файлов хранятся в `code_path_cache = LRUCache(maxsize=1024)` в оперативной памяти одного процесса бота.
- **Влияние:** При перезапуске контейнера или вытеснении из кэша все инлайн-кнопки в истории переписки пользователей перестают работать, выдавая алерт "Информация устарела".
- **Решение:** Маппинг хранится в Redis под ключами `callback_path:<hash>` с TTL 14 дней и одновременно в локальном LRU-кэше. При промахе локального кэша обработчик восстанавливает значение из Redis; при недоступности Redis продолжает работу с локальным кэшем. Команда `/clear_cache` очищает оба слоя.

---

### ✅ BUG-6 (ИСПРАВЛЕНО): Отсутствие URL-кодирования поискового запроса в RUZ API
- **Приоритет:** MEDIUM (P2)
- **Файл:** [shared_lib/services/university_api.py](file:///c:/Projects/matplobbot/shared_lib/services/university_api.py#L76)
- **Проблема:** Строка запроса формируется конкатенацией: `f"/api/search?term={term}&type={search_type}"` без `urllib.parse.quote_plus(term)`.
- **Влияние:** При поиске с пробелами, амперсандами, спецсимволами или специфическими символами кириллицы запрос к API вуза может быть искажен.
- **Рекомендация:** Передавать параметры через словарь `params={"term": term, "type": search_type}` в вызове `session.get()`.

---

### ✅ BUG-7 (ИСПРАВЛЕНО): Дублирующаяся регистрация обработчика команды в `admin.py`
- **Приоритет:** LOW (P3)
- **Файл:** [bot/handlers/admin.py](file:///c:/Projects/matplobbot/bot/handlers/admin.py#L101-L102)
- **Проблема:** Строка `self.router.message(Command("set_module"), AdminFilter())(self.set_module_command)` зарегистрирована дважды подряд.
- **Рекомендация:** Удалить строку-дубликат.

---

## 3. Продуктовые пробелы и несоответствия (Product Issues)

### ✅ PROD-1 (ИСПРАВЛЕНО): Скрытая и недокументированная интеграция с почтой (`/mail`)
- **Проблема:** В проекте реализован мощный функционал защищенного почтового клиента (IMAP/POP3 через TLS с шифрованием Fernet, парсинг MIME, отправка в Telegram).
- **Несоответствия:**
  1. Команда `/mail` отсутствует в списке популярных команд в `README.md`.
  2. Команда `/mail` отсутствует в меню `/help` бота (`get_help_inline_keyboard`).
  3. Команда `/mail` отсутствует в `BASE_COMMANDS` в `keyboards.py`.
  4. Сайт не должен получать почтовые пароли; управление почтой остаётся в private-only Telegram UI.
  5. Переменная `MAIL_CREDENTIAL_KEY` не описана в документации по настройке `.env`.
- **Решение:** Либо полноценно представить почту как фичу в документации и UI, либо пометить как экспериментальный/скрытый модуль.

---

### ✅ PROD-2 (ИСПРАВЛЕНО): Единая модель расписания Web/Telegram
- **Проблема:**
  1. В Web-версии появились профили синхронизации календаря (`all`, `exams_only`, выбор конкретных дисциплин и модулей, сокрытие аудиторий).
  2. В боте подписка по-прежнему привязана к жесткому времени `notification_time` и единому состоянию.
  3. Экспорт WebCal/iCal из бота генерирует базовый календарь, в то время как веб-интерфейс позволяет гибко управлять несколькими фидами.
- **Решение:** Унифицировать модель подписок и профилей между Telegram Mini App, ботом и веб-сайтом.

---

### ✅ PROD-3 (ИСПРАВЛЕНО): Заброшенный эндпоинт стриминга логов (`/ws/bot_log`)
- **Проблема:** `README.md` заявляет функцию: *"Stream the bot log into the dashboard for real-time monitoring"*. В дашборде есть соответствующий блок, но в `ws_router.py` отдаётся заглушка: *"File-based bot log streaming is disabled. Use docker compose logs -f..."*.
- **Решение:** Либо реализовать реальный стриминг через Redis Pub/Sub логгер-хэндлер, либо удалить вводящее в заблуждение описание из `README.md` и UI.

---

### ✅ PROD-4 (ИСПРАВЛЕНО): Admin-only переход из рейтинга к деталям пользователя (`/users/{user_id}`)
- **Проблема:** Существует полноценная страница `user_details.html` с историей действий, возможностью отправки сообщений пользователю от админа и экспортом. Однако в актуальной версии сайта (`main_site_frontend/stats.html`) ссылки на эту страницу убраны — таблица лидеров не кликабельна.
- **Решение:** Интегрировать переход в профиль пользователя или модальное окно деталей в основной интерфейс `stats.html`.

---

### ✅ PROD-5 (ИСПРАВЛЕНО): "Мертвая" страница регистрации `register.html`
- **Проблема:** На странице `register.html` выводится надпись "Регистрация закрыта. Парольные аккаунты выдаются вручную. Для обычного входа используйте Telegram", форма ввода удалена, но остались пустые div-ы для сообщений об ошибках, а в навигации всё ещё есть ссылки на авторизацию/регистрацию.
- **Решение:** При отключенной регистрации автоматически перенаправлять на `/login` с понятным баннером или показывать четкую инструкцию по входу через Telegram Widget.

---

### ✅ PROD-6 (ИСПРАВЛЕНО): Ветка GitHub сохраняется в ссылке репозитория
- **Проблема:** В `bot/config.py` захардкожено `MD_SEARCH_BRANCH = "main"`. Если репозиторий студента или преподавателя имеет основную ветку `master` (или кастомную), бот не находит ни одного файла (404).
- **Решение:** Получать ветку по умолчанию через GitHub API (`/repos/{owner}/{repo}`) и сохранять её в `user_github_repos`.

---

### ✅ PROD-7 (ИСПРАВЛЕНО): PostgreSQL FTS явно называется текстовым поиском
- **Проблема:** Модуль называется `semantic_search.py`, но выполняет стандартный полнотекстовый поиск PostgreSQL (`to_tsquery('russian', ...)`). Поиск по формулам LaTeX, англоязычным терминам и названиям библиотек работает плохо из-за русской стемминг-словаря.
- **Решение:** Переименовать сервис в `text_search.py` или подключить честный векторный поиск (через `pgvector` с легкой моделью эмбеддингов).

---

## 4. UI/UX проблемы и фронтенд (UI/UX & Frontend)

### ✅ UX-1 (ИСПРАВЛЕНО): Перегруженная Reply-клавиатура бота на 20+ строк
- **Файл:** [bot/keyboards.py](file:///c:/Projects/matplobbot/bot/keyboards.py#L156-L175)
- **Проблема:** В `get_main_reply_keyboard` каждая кнопка и WebApp размещаются на отдельной строке:
  `keyboard_buttons.extend([[KeyboardButton(text=cmd)] for cmd in current_commands])`.
- **Влияние:** Открывающаяся клавиатура занимает 100% высоты экрана смартфона, закрывая историю сообщений.
- **Рекомендация:**
  1. Группировать кнопки по 2-3 в строке.
  2. Сократить количество кнопок быстрого меню до 4-6 ключевых, перенеся редкие команды в меню `/help` или нативное меню Telegram (`BotCommandScope`).

---

### ✅ UX-2 (ИСПРАВЛЕНО): Риск падения фронтенда по `QuotaExceededError` в LocalStorage
- **Файл:** [main_site_frontend/js/schedule.js](file:///c:/Projects/matplobbot/main_site_frontend/js/schedule.js#L878)
- **Проблема:** В `persistScheduleSnapshot` полные списки пар за семестр для разных групп сохраняются в `localStorage` без очистки старых записей и без `try...catch`.
- **Влияние:** В браузерах Safari (iOS) при превышении квоты 5 МБ происходит `Uncaught DOMException: QuotaExceededError`, ломающий весь JS на странице расписания.
- **Рекомендация:**
  1. Обернуть сохранение в `try...catch`.
  2. Ограничить количество сохраняемых снимков (например, до 3 последних) или перевести кэширование расписаний на `IndexedDB`.

---

### ✅ UX-3 (ИСПРАВЛЕНО): Безусловное отображение `BackButton` в Telegram Mini App
- **Файл:** [main_site_frontend/js/telegram_webapp.js](file:///c:/Projects/matplobbot/main_site_frontend/js/telegram_webapp.js#L115)
- **Проблема:** `webApp.BackButton?.show()` вызывается при старте любого экрана TMA.
- **Влияние:** Пользователь видит кнопку "Назад" даже когда он только что открыл WebApp и истории переходов ещё нет. Нажатие на кнопку в таком случае закрывает приложение или ведёт себя непредсказуемо.
- **Рекомендация:** Скрывать `BackButton` на корневых экранах и показывать только при переходе в глубь расписания/проекта.

---

### ✅ UX-4 (РЕШЕНИЕ ЗАФИКСИРОВАНО): Ручное версионирование статики оставлено
- **Файлы:** [main_site_frontend/service-worker.js](file:///c:/Projects/matplobbot/main_site_frontend/service-worker.js#L21-L37), HTML-файлы
- **Проблема:** Ручное добавление хэшей версий (`?v=20260821-6`, `?v=19`, `?v=1`, `?v=6`). Значения в `login.html`, `schedule.html` и `service-worker.js` отличаются.
- **Влияние:** Service Worker кэширует одни версии, страницы запрашивают другие. Обновления фронтенда не доходят до пользователей без принудительной очистки кэша браузера.
- **Рекомендация:** Внедрить базовый бандлер (Vite) с автоматическим хэшированием файлов в именах (`script.[hash].js`).

---

### ✅ UX-5 (ИСПРАВЛЕНО): Единый источник локализации фронтенда
- **Файлы:** [main_site_frontend/js/frontend_i18n.js](file:///c:/Projects/matplobbot/main_site_frontend/js/frontend_i18n.js), [main_site_frontend/locales/en.json](file:///c:/Projects/matplobbot/main_site_frontend/locales/en.json), [main_site_frontend/locales/ru.json](file:///c:/Projects/matplobbot/main_site_frontend/locales/ru.json)
- **Решение:** Встроенные словари удалены из `navbar.js` и `stats.js`. Оба языка загружаются из общих JSON-файлов через единый `window.mpbI18n`; service worker кэширует loader и локали.
- **Проверка:** Тест контролирует одинаковые ключи и placeholder'ы RU/EN, существование ключей из HTML-атрибутов и порядок подключения loader до `navbar.js`.

---

## 5. База данных и производительность (Database & Performance)

### ✅ DB-1 (ИСПРАВЛЕНО): Отсутствие индексов на таблице действий пользователей (`user_actions`)
- **Файлы:** [shared_lib/models.py](file:///c:/Projects/matplobbot/shared_lib/models.py#L34-L42), [alembic/versions/c7a670795f42_init_full_schema.py](file:///c:/Projects/matplobbot/alembic/versions/c7a670795f42_init_full_schema.py#L74-L82)
- **Проблема:** Таблица `user_actions` содержит только первичный ключ `id`. Индексы на `user_id`, `action_type`, `timestamp` отсутствуют.
- **Влияние:** При росте таблицы до сотен тысяч записей выборка истории пользователя (`WHERE user_id = ... ORDER BY timestamp DESC`) и графиков активности в дашборде приводит к медленному Sequential Scan и деградации производительности БД.
- **Рекомендация:** Добавить составные индексы в Alembic:
  - `CREATE INDEX ix_user_actions_user_timestamp ON user_actions (user_id, timestamp DESC);`
  - `CREATE INDEX ix_user_actions_timestamp ON user_actions (timestamp);`
  - `CREATE INDEX ix_user_actions_action_type ON user_actions (action_type);`

---

### ✅ DB-2 (ИСПРАВЛЕНО): Отсутствие индексов на подписках (`user_schedule_subscriptions`)
- **Файл:** [shared_lib/models.py](file:///c:/Projects/matplobbot/shared_lib/models.py#L74-L96)
- **Проблема:** Планировщик каждую минуту выполняет запрос:
  `WHERE notification_time = :time AND is_active = true`.
  Колонка `notification_time` не проиндексирована, внешний ключ `user_id` также не имеет B-Tree индекса.
- **Влияние:** Ежеминутный Seq Scan по таблице подписок.
- **Рекомендация:** Создать индекс:
  `CREATE INDEX ix_user_subs_notify ON user_schedule_subscriptions (notification_time, is_active);`

---

### ✅ DB-3 (ИСПРАВЛЕНО): Избыточный опрос БД через WebSocket (`periodic_stats_updater`)
- **Файл:** [fastapi_stats_app/routers/ws_router.py](file:///c:/Projects/matplobbot/fastapi_stats_app/routers/ws_router.py#L113-L136)
- **Проблема:** Каждые 2 секунды при наличии подключенных клиентов фоновая задача проверяет `SELECT COUNT(*) FROM user_actions`. Если счетчик изменился, в одном цикле выполняется 9 тяжелых аналитических SQL-запросов (агрегации, группировки по дням/неделям/месяцам, подсчет топ-команд).
- **Влияние:** При активном использовании бота и открытом дашборде создаётся непрерывная паразитная нагрузка на PostgreSQL.
- **Рекомендация:**
  1. Увеличить интервал опроса (например, до 10-15 секунд) или агрегировать счетчики в Redis.
  2. Использовать инкрементальное обновление / кэширование аналитических выборок в Redis.

---

### ✅ DB-4 (ИСПРАВЛЕНО): Неэффективный `jsonb_array_elements` в `/api/schedule/cached_list`
- **Файл:** [fastapi_stats_app/routers/schedule_router.py](file:///c:/Projects/matplobbot/fastapi_stats_app/routers/schedule_router.py#L327-L344)
- **Проблема:** Чтобы узнать читаемое название группы/преподавателя (`label`), эндпоинт распаковывает весь JSON семестрового расписания через `LEFT JOIN LATERAL jsonb_array_elements(...)`.
- **Влияние:** Высокая нагрузка на CPU и память БД при открытии оффлайн-шторки в вебе.
- **Рекомендация:** Добавить в таблицу `cached_schedules` отдельную колонку `entity_name` (VARCHAR), заполняемую при сохранении кэша.

---

### ✅ DB-5 (ИСПРАВЛЕНО): Изолированная модель `MailAccount` вне `models.py`
- **Файл:** [shared_lib/mail_bridge.py](file:///c:/Projects/matplobbot/shared_lib/mail_bridge.py#L44-L60)
- **Проблема:** Класс `MailAccount` объявлен в `mail_bridge.py`, а не в общем файле `shared_lib/models.py`. У колонки `user_id` отсутствует `ForeignKey("users.user_id", ondelete="CASCADE")`.
- **Влияние:** Нарушение целостности: при удалении пользователя его почтовые аккаунты остаются в базе данных навсегда.
- **Рекомендация:** Перенести модель в `models.py` и добавить внешний ключ с каскадным удалением.

---

## 6. Технологический долг и архитектура (Technical Debt & Architecture)

### ✅ DEBT-1 (ИСПРАВЛЕНО): Единый статический интерфейс
- **Решение:** Jinja2-шаблоны дашборда и их дублирующие JS/CSS удалены. `main_site_frontend` является единственным UI, а FastAPI обслуживает REST/WebSocket/OpenAPI и совместимые защищённые редиректы старых URL на `PUBLIC_SITE_URL`.
- **Совместимость:** `/` перенаправляет аутентифицированного пользователя на `/stats`, `/users/{user_id}` остаётся admin-only и перенаправляет на `/admin-user.html?user_id=...`.

---

### ✅ DEBT-2 (ИСПРАВЛЕНО): Мертвый код `calendar_router.py` (v1)
- **Файл:** [fastapi_stats_app/routers/calendar_router.py](file:///c:/Projects/matplobbot/fastapi_stats_app/routers/calendar_router.py)
- **Проблема:** В `fastapi_stats_app/main.py` импортируется `calendar_router_v2 as calendar_router`. Старый файл `calendar_router.py` (135 строк) нигде не используется.
- **Решение:** Удалить неиспользуемый файл `calendar_router.py`.

---

### ✅ DEBT-3 (БЕЗОПАСНЫЙ ЭТАП ВЫПОЛНЕН): Разбиение "God Nodes" с фасадами
- **Проблема:**
  - `ScheduleManager` — 2027 строк кода.
  - `SettingsManager` — 1643 строки кода.
  - `schedule_service.py` — 1435 строк кода.
  - `database.py` — 1756 строк кода.
  Менеджеры требуют взаимной инициализации (`set_base_manager`), что усложняет тестирование и расширение.
- **Решение:** Запросы профиля/истории действий вынесены в `shared_lib/user_activity_repository.py`, фильтры агрегированного расписания — в `bot/services/myschedule_filters.py`, сборка приватной клавиатуры настроек — в `bot/services/settings_keyboard.py`.
- **Совместимость:** Прежние функции `shared_lib.database` и методы менеджеров оставлены как тонкие async-фасады. Это позволяет продолжать поэтапное разбиение без одномоментной миграции всех вызовов.

---

### ✅ DEBT-4 (ИСПРАВЛЕНО): JWT через PyJWT
- **Файл:** [fastapi_stats_app/auth.py](file:///c:/Projects/matplobbot/fastapi_stats_app/auth.py#L48-L109)
- **Решение:** Самописный код удалён, токены создаются и проверяются через `PyJWT==2.15.0` с явным `HS256` и обязательными `sub`, `iat`, `nbf`, `exp`, `iss`, `aud`.
- **Безопасность:** В production требуется секрет не короче 32 байт; issuer/audience настраиваются через окружение. Старые токены без обязательных claims после обновления требуют повторного входа.

---

### ✅ DEBT-5 (ИСПРАВЛЕНО): Захардкоженный хост Redis в клиенте
- **Файл:** [shared_lib/redis_client.py](file:///c:/Projects/matplobbot/shared_lib/redis_client.py#L70)
- **Проблема:** Строка `redis_client = RedisClient(host="redis")` не считывает переменную `REDIS_HOST`.
- **Решение:** Использовать `os.getenv("REDIS_HOST", "redis")` и `int(os.getenv("REDIS_PORT", 6379))`.

---

## 7. Инфраструктура и DevOps (DevOps & CI/CD)

### ✅ OPS-1 (РЕШЕНИЕ ЗАФИКСИРОВАНО): Текущая политика пользователей контейнеров оставлена
- **Файлы:** [Dockerfile.bot](file:///c:/Projects/matplobbot/Dockerfile.bot), [Dockerfile.worker](file:///c:/Projects/matplobbot/Dockerfile.worker), [scheduler_app/Dockerfile](file:///c:/Projects/matplobbot/scheduler_app/Dockerfile), [fastapi_stats_app/Dockerfile](file:///c:/Projects/matplobbot/fastapi_stats_app/Dockerfile)
- **Проблема:** Ни в одном Dockerfile не создаётся пользователь приложения.
- **Решение пользователя:** Не менять текущую политику в рамках этого цикла. Задача закрыта как осознанно принятый инфраструктурный риск; существующий non-root запуск worker не откатывается.

---

### ✅ OPS-2 (ИСПРАВЛЕНО): Конфигурации Compose проверяются как два самостоятельных сценария
- **Проблема:**
  1. В `docker-compose.prod.yml` есть сервис `proxy`, а в `docker-compose.yml` его нет.
  2. В `docker-compose.prod.yml` монтируется `default.conf` в nginx, а в dev `docker-compose.yml` — нет.
  3. В `docker-compose.prod.yml` остался комментарий `# ДОБАВЬ ЭТУ СТРОКУ:`.
- **Исправление:**
  1. Отдельный `compose.dev` не создаётся: локальный и production-файлы остаются самостоятельными, что соответствует реальному запуску `deploy.sh`.
  2. Общие nginx/Caddy mounts выровнены и сделаны read-only; устаревшая директива `version` удалена.
  3. `proxy` явно оставлен production-only, так как ему нужны production-секреты/подписки; это единственное разрешённое различие топологии сервисов.
  4. Добавлен тест паритета общих сервисов, mounts и Docker log limits; оба Compose-файла проходят `docker compose config`.

---

### ✅ OPS-3 (ИСПРАВЛЕНО): Структурированные логи и ограниченная Docker-ротация
- **Файлы:** [bot/logger.py](file:///c:/Projects/matplobbot/bot/logger.py), [fastapi_stats_app/main.py](file:///c:/Projects/matplobbot/fastapi_stats_app/main.py)
- **Проблема:** Логи писались в `StreamHandler` без поддержки структурного логирования (JSON).
- **Исправление:** Общий `shared_lib.logging_config` валидирует `LOG_LEVEL`/`LOG_FORMAT`, выдаёт JSON по умолчанию в production и человекочитаемый текст локально, сохраняет correlation ID и форматирует Uvicorn handlers. Логи остаются в stdout/stderr, а все долгоживущие Compose-сервисы ограничены Docker `json-file` ротацией `10m × 3`.

---

## Итоговая сводка по приоритетам (Priority Summary)

| Приоритет | ID задачи | Краткое описание | Статус |
| :--- | :--- | :--- | :--- |
| **P0 (Critical)** | SEC-1 | Утечка `BOT_TOKEN` в URL аватарок пользователей | ✅ Исправлено |
| **P0 (Critical)** | SEC-2 | Stored XSS в дашборде статистики и деталях пользователя | ✅ Исправлено |
| **P1 (High)** | BUG-1 | Падение FastAPI при старте без `JWT_SECRET_KEY` | ✅ Исправлено |
| **P1 (High)** | BUG-2 | Разрыв HTML-тегов при отправке длинных сообщений бота | ✅ Исправлено |
| **P1 (High)** | BUG-4 | Неработающий локальный сайт (`runtime_config.js` и `default.conf`) | ✅ Исправлено |
| **P1 (High)** | SEC-3 | Небезопасная компиляция LaTeX (RCE / File Read) | ✅ Исправлено |
| **P1 (High)** | SEC-4 | Дефолтные учетные данные `admin:admin` | ✅ Исправлено |
| **P1 (High)** | DB-1 | Отсутствие индексов на таблице `user_actions` | ✅ Исправлено |
| **P2 (Medium)** | SEC-6 | Санитизация имён файлов Studio | ✅ Исправлено |
| **P2 (Medium)** | UX-1 | Перегруженная Reply-клавиатура бота на 20+ строк | ✅ Исправлено |
| **P2 (Medium)** | UX-2 | Падение по `QuotaExceededError` в LocalStorage фронтенда | ✅ Исправлено |
| **P2 (Medium)** | BUG-3 | Падение отправки формул LaTeX в боте из-за устаревшего Markdown | ✅ Исправлено |
| **P2 (Medium)** | BUG-5 | Потеря инлайн-кнопок при перезапуске бота (`code_path_cache`) | ✅ Исправлено |
| **P2 (Medium)** | BUG-6 | URL-параметры поисковых запросов RUZ | ✅ Исправлено |
| **P2 (Medium)** | PROD-1 | Скрытая и недокументированная интеграция `/mail` | ✅ Исправлено |
| **P2 (Medium)** | PROD-3 | Сломанный стриминг логов бота в дашборд | ✅ Исправлено (явно отключён, UI показывает Docker logs) |
| **P2 (Medium)** | DB-2 | Отсутствие индексов на подписках | ✅ Исправлено |
| **P2 (Medium)** | DB-3 | DDoS базы данных через WebSocket опрос каждые 2 секунды | ✅ Исправлено |
| **P2 (Medium)** | DB-4 | Полный `jsonb_array_elements` для списка кэша расписаний | ✅ Исправлено |
| **P2 (Medium)** | UX-3 | Безусловный BackButton в Telegram Mini App | ✅ Исправлено |
| **P2 (Medium)** | UX-5 | Дублирование словарей локализации фронтенда | ✅ Исправлено |
| **P2 (Medium)** | DEBT-1 | Разделение на два разных сайта/дашборда (Jinja2 vs Static) | ✅ Исправлено |
| **P2 (Medium)** | OPS-1 | Политика пользователей контейнеров | ✅ Решение зафиксировано: оставить текущую |
| **P2 (Medium)** | OPS-2 | Паритет локальной и production Compose-конфигураций | ✅ Исправлено |
| **P2 (Medium)** | OPS-3 | Структурированные логи и Docker-ротация | ✅ Исправлено |
| **P3 (Low)** | DEBT-2 | Удаление мертвого `calendar_router.py` (v1) | ✅ Исправлено |
| **P3 (Low)** | DEBT-3 | Рефакторинг God Objects (`ScheduleManager`, `SettingsManager`, `database.py`) | ✅ Безопасный этап выполнен |
| **P3 (Low)** | DEBT-4 | Самописная реализация JWT | ✅ Исправлено |
| **P3 (Low)** | DEBT-5 | Параметризация `REDIS_HOST` в `shared_lib/redis_client.py` | ✅ Исправлено |
| **P3 (Low)** | BUG-7 | Удаление дубликата команды в `admin.py` | ✅ Исправлено |
| **P3 (Low)** | DB-5 | Централизация `MailAccount` и FK владельца | ✅ Исправлено |
| **P3 (Low)** | PROD-5 | Ясная заглушка закрытой регистрации без мёртвых элементов формы | ✅ Исправлено |
