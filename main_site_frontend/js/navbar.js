const NAV_API_BASE = "https://api.ivantishchenko.ru/api";
const UI_LANG_KEY = "mpb_ui_lang";

const I18N = {
    en: {
        "nav.home": "Home",
        "nav.projects": "Projects",
        "nav.schedule": "Schedule",
        "nav.studio": "Studio",
        "nav.admin": "Admin",
        "nav.signIn": "Sign In",
        "nav.profile": "Profile",
        "nav.logout": "Log out",
        "nav.logoutAccount": "Log out of account",
        "nav.menu": "Toggle menu",
        "lang.en": "EN",
        "lang.ru": "RU",
        "palette.title": "Command Palette",
        "palette.placeholder": "Type a command...",
        "palette.empty": "No commands found",
        "palette.openHelp": "Open shortcut help",
        "palette.toggleLang": "Toggle UI language",
        "palette.refresh": "Refresh current page",
        "help.title": "Keyboard Shortcuts",
        "help.palette": "Open command palette",
        "help.focusSearch": "Focus search field",
        "help.refresh": "Refresh widgets/page",
        "help.nextPage": "Next table page",
        "help.prevPage": "Previous table page",
        "help.close": "Close dialogs",
        "help.open": "Open shortcuts help",
        "help.hint": "Shortcuts work when a text input is not focused.",
        "index.meta.title": "Ivan Tishchenko | Portfolio",
        "index.hero.badge": "Open for projects",
        "index.hero.title.top": "Building digital",
        "index.hero.title.accent": "tools",
        "index.hero.text": "A personal builder hub with projects, automation, and useful services for everyday work.",
        "index.hero.primaryCta": "View projects",
        "index.projects.title": "Featured projects",
        "index.projects.text": "A collection of tools built to solve real tasks.",
        "index.project.type.bot": "Telegram Bot",
        "index.project.description.matplobbot": "A smart assistant for students with schedule automation, alerts, and performance stats right in the messenger.",
        "index.project.link.more": "Learn more",
        "index.footer.rights": "© 2026 Ivan Tishchenko. All rights reserved.",
        "schedule.meta.title": "Schedule | ITISHCHENKO",
        "schedule.heading": "Schedule",
        "schedule.offline.available": "Available offline",
        "schedule.search.placeholder": "Find a group or lecturer...",
        "schedule.today": "Today",
        "schedule.filters.mobile": "Filters and modules",
        "schedule.filters.desktop": "Filters and modules",
        "schedule.filters.shortNames": "Short names",
        "schedule.filters.fullLecturer": "Full lecturer name",
        "schedule.filters.all": "All",
        "schedule.filters.clear": "Reset",
        "schedule.filters.selected": "Selected",
        "schedule.filters.available": "Available",
        "schedule.offline.warning": "University service is unavailable. Loaded a cached copy.",
        "schedule.state.default": "Choose a schedule",
        "schedule.context.reset": "Reset",
        "schedule.action.today": "Today",
        "schedule.action.tomorrow": "Tomorrow",
        "schedule.action.thisWeek": "This week",
        "schedule.action.nextWeek": "Next week",
        "schedule.view.auto": "Auto",
        "schedule.view.table": "Table",
        "schedule.view.cards": "Cards",
        "schedule.context.none": "No group selected",
        "schedule.context.loadedRange": "Loaded {start} — {end}",
        "schedule.history.empty": "History is empty",
        "schedule.history.saved": "Saved offline",
        "schedule.search.error": "Search failed or the server is unavailable.",
        "schedule.search.empty": "Nothing found",
        "schedule.search.cacheBadge": "CACHE",
        "schedule.error.load": "Failed to load schedule.",
        "schedule.table.time": "Time",
        "schedule.state.emptyWeek": "No classes this week.",
        "schedule.state.emptyPeriod": "No classes for this period.",
        "schedule.copy.done": "Copied!",
        "schedule.copy.room": "Copy room",
        "schedule.copy.teacher": "Copy lecturer",
        "schedule.calendar.eyebrow": "Sync",
        "schedule.calendar.title": "Calendar subscription",
        "schedule.calendar.description": "Connect your personal ICS feed to Apple Calendar, Google Calendar, or any other calendar app.",
        "schedule.calendar.loading": "Loading your personal subscription link...",
        "schedule.calendar.error": "Failed to load the calendar subscription.",
        "schedule.calendar.unavailable": "Calendar subscription is available for Telegram-linked accounts with bot schedule subscriptions.",
        "schedule.calendar.resetDone": "The subscription link was updated. The previous link is now disabled.",
        "schedule.calendar.urlLabel": "Subscription URL",
        "schedule.calendar.copy": "Copy link",
        "schedule.calendar.apple": "Open on iOS / Mac",
        "schedule.calendar.reset": "Reset link",
        "schedule.calendar.summary": "Personal calendar feed for your active schedule subscriptions and filters.",
        "schedule.calendar.settingsTitle": "What this sync includes",
        "schedule.calendar.expand": "Expand",
        "schedule.calendar.collapse": "Collapse",
        "schedule.calendar.statusReady": "Ready",
        "schedule.calendar.statusSetup": "Setup",
        "schedule.calendar.setting.source.label": "Source",
        "schedule.calendar.setting.source.value": "Your active Telegram schedule subscriptions",
        "schedule.calendar.setting.scope.label": "Scope",
        "schedule.calendar.setting.scope.value": "Lessons, lecturers, rooms, and active personal schedule filters",
        "schedule.calendar.setting.window.label": "Time window",
        "schedule.calendar.setting.window.value": "Recent 14 days plus the next 90 days of schedule",
        "schedule.calendar.setting.access.label": "Access",
        "schedule.calendar.setting.access.value": "Private secret link. Reset it any time to revoke the previous URL.",
        "schedule.calendar.instructions": "Use the iOS / Mac button for Apple Calendar. For Google Calendar, copy the HTTPS URL and add it from URL in the web version.",
        "schedule.action.retry": "Retry",
        "schedule.action.clearFilters": "Clear filters",
        "schedule.action.changeGroup": "Change group",
        "schedule.day.today": "Today"
    },
    ru: {
        "nav.home": "Главная",
        "nav.projects": "Проекты",
        "nav.schedule": "Расписание",
        "nav.studio": "Студия",
        "nav.admin": "Админ",
        "nav.signIn": "Войти",
        "nav.profile": "Профиль",
        "nav.logout": "Выйти",
        "nav.logoutAccount": "Выйти из аккаунта",
        "nav.menu": "Открыть меню",
        "lang.en": "EN",
        "lang.ru": "RU",
        "palette.title": "Палитра команд",
        "palette.placeholder": "Введите команду...",
        "palette.empty": "Команды не найдены",
        "palette.openHelp": "Открыть справку по клавишам",
        "palette.toggleLang": "Переключить язык интерфейса",
        "palette.refresh": "Обновить текущую страницу",
        "help.title": "Горячие клавиши",
        "help.palette": "Открыть палитру команд",
        "help.focusSearch": "Фокус на поле поиска",
        "help.refresh": "Обновить виджеты/страницу",
        "help.nextPage": "Следующая страница таблицы",
        "help.prevPage": "Предыдущая страница таблицы",
        "help.close": "Закрыть диалоги",
        "help.open": "Открыть справку по клавишам",
        "help.hint": "Сочетания работают, если курсор не в поле ввода.",
        "index.meta.title": "Иван Тищенко | Портфолио",
        "index.hero.badge": "Открыт для проектов",
        "index.hero.title.top": "Создаю цифровые",
        "index.hero.title.accent": "инструменты",
        "index.hero.text": "Персональный хаб разработчика. Проекты, автоматизация и полезные сервисы для ежедневной работы.",
        "index.hero.primaryCta": "Смотреть проекты",
        "index.projects.title": "Избранные проекты",
        "index.projects.text": "Коллекция инструментов, которые я разработал для решения реальных задач.",
        "index.project.type.bot": "Telegram Bot",
        "index.project.description.matplobbot": "Умный помощник для студентов: автоматизация расписания, уведомления и статистика успеваемости прямо в мессенджере.",
        "index.project.link.more": "Подробнее",
        "index.footer.rights": "© 2026 Ivan Tishchenko. Все права защищены.",
        "schedule.meta.title": "Расписание | ITISHCHENKO",
        "schedule.heading": "Расписание",
        "schedule.offline.available": "Доступно оффлайн",
        "schedule.search.placeholder": "Найти группу или ФИО...",
        "schedule.today": "Сегодня",
        "schedule.filters.mobile": "Фильтры и модули",
        "schedule.filters.desktop": "Фильтры и модули",
        "schedule.filters.shortNames": "Короткие названия",
        "schedule.filters.all": "Всё",
        "schedule.filters.clear": "Сброс",
        "schedule.filters.selected": "Активные",
        "schedule.filters.available": "Доступные",
        "schedule.offline.warning": "ВУЗ недоступен. Загружена копия.",
        "schedule.state.default": "Выберите расписание",
        "schedule.context.reset": "Сброс",
        "schedule.action.today": "Сегодня",
        "schedule.action.tomorrow": "Завтра",
        "schedule.action.thisWeek": "Эта неделя",
        "schedule.action.nextWeek": "Следующая неделя",
        "schedule.view.auto": "Авто",
        "schedule.view.table": "Таблица",
        "schedule.view.cards": "Карточки",
        "schedule.context.none": "Группа не выбрана",
        "schedule.context.loadedRange": "Загружено {start} — {end}",
        "schedule.history.empty": "История пуста",
        "schedule.history.saved": "Сохранено локально",
        "schedule.search.error": "Ошибка поиска или сервер недоступен.",
        "schedule.search.empty": "Ничего не найдено",
        "schedule.search.cacheBadge": "КЭШ",
        "schedule.error.load": "Ошибка загрузки.",
        "schedule.table.time": "Время",
        "schedule.state.emptyWeek": "Нет занятий на этой неделе.",
        "schedule.state.emptyPeriod": "Нет занятий за выбранный период.",
        "schedule.copy.done": "Скопировано!",
        "schedule.copy.room": "Копировать аудиторию",
        "schedule.copy.teacher": "Копировать преподавателя",
        "schedule.action.retry": "Повторить",
        "schedule.action.clearFilters": "Сбросить фильтры",
        "schedule.action.changeGroup": "Сменить группу",
        "schedule.day.today": "Сегодня"
    }
};

Object.assign(I18N.ru, {
    "schedule.filters.fullLecturer": "Полное имя преподавателя",
    "schedule.calendar.eyebrow": "Синхронизация",
    "schedule.calendar.title": "Подписка на календарь",
    "schedule.calendar.description": "Подключите персональную ICS-ленту к Apple Calendar, Google Calendar или любому другому приложению календаря.",
    "schedule.calendar.loading": "Загружаем вашу персональную ссылку...",
    "schedule.calendar.error": "Не удалось загрузить подписку на календарь.",
    "schedule.calendar.unavailable": "Подписка на календарь доступна для аккаунтов, связанных с Telegram и подписками бота на расписание.",
    "schedule.calendar.resetDone": "Ссылка обновлена. Предыдущая ссылка больше не работает.",
    "schedule.calendar.urlLabel": "Ссылка подписки",
    "schedule.calendar.copy": "Скопировать ссылку",
    "schedule.calendar.apple": "Открыть на iOS / Mac",
    "schedule.calendar.reset": "Сбросить ссылку",
    "schedule.calendar.instructions": "Для Apple Calendar используйте кнопку iOS / Mac. Для Google Calendar скопируйте HTTPS-ссылку и добавьте ее по URL в веб-версии."
});

Object.assign(I18N.ru, {
    "schedule.calendar.summary": "Персональная календарная лента для ваших активных подписок и фильтров расписания.",
    "schedule.calendar.settingsTitle": "Что входит в синхронизацию",
    "schedule.calendar.expand": "Развернуть",
    "schedule.calendar.collapse": "Свернуть",
    "schedule.calendar.statusReady": "Готово",
    "schedule.calendar.statusSetup": "Настройка",
    "schedule.calendar.setting.source.label": "Источник",
    "schedule.calendar.setting.source.value": "Ваши активные Telegram-подписки на расписание",
    "schedule.calendar.setting.scope.label": "Состав",
    "schedule.calendar.setting.scope.value": "Занятия, преподаватели, аудитории и активные персональные фильтры расписания",
    "schedule.calendar.setting.window.label": "Период",
    "schedule.calendar.setting.window.value": "Последние 14 дней и следующие 90 дней расписания",
    "schedule.calendar.setting.access.label": "Доступ",
    "schedule.calendar.setting.access.value": "Приватная секретная ссылка. Ее можно сбросить в любой момент, чтобы отозвать прежний URL."
});

Object.assign(I18N.en, {
    "schedule.calendar.summaryReady": "Private iCal feeds for your website sync profiles.",
    "schedule.calendar.summaryPaused": "Your calendar links are paused until you enable sync again.",
    "schedule.calendar.summarySetup": "Build private feeds for all classes, exams only, or the current schedule page.",
    "schedule.calendar.statusPaused": "Paused",
    "schedule.calendar.pausedNotice": "Sync is paused. External calendar apps will stop updating until you enable the feed again.",
    "schedule.calendar.profile.custom": "Preset",
    "schedule.calendar.profile.builtin": "Built-in",
    "schedule.calendar.hide": "Hide link",
    "schedule.calendar.reveal": "Reveal link",
    "schedule.calendar.preview": "Test feed",
    "schedule.calendar.download": "Download .ics",
    "schedule.calendar.disable": "Disable sync",
    "schedule.calendar.enable": "Enable sync",
    "schedule.calendar.instructionsTitle": "How to subscribe",
    "schedule.calendar.platform.apple": "Use the Apple button below or paste the webcal link into Apple Calendar on iPhone, iPad, or Mac.",
    "schedule.calendar.platform.google": "Open Google Calendar on the web, choose Other calendars, then Add by URL and paste the HTTPS feed link.",
    "schedule.calendar.platform.outlook": "In Outlook, use Add calendar or Subscribe from web, then paste the HTTPS feed link and confirm the subscription.",
    "schedule.calendar.platform.apple.label": "Apple",
    "schedule.calendar.platform.google.label": "Google",
    "schedule.calendar.platform.outlook.label": "Outlook",
    "schedule.calendar.meta.scope": "Scope",
    "schedule.calendar.meta.modules": "Modules",
    "schedule.calendar.meta.modulesAll": "No module restriction",
    "schedule.calendar.meta.events": "Events in feed",
    "schedule.calendar.meta.next": "Next event",
    "schedule.calendar.meta.none": "No upcoming event in range",
    "schedule.calendar.meta.health": "Feed health",
    "schedule.calendar.meta.sources": "{used}/{total} cached source(s)",
    "schedule.calendar.meta.updated": "Source updated",
    "schedule.calendar.meta.accessed": "Last external access",
    "schedule.calendar.meta.generated": "Preview generated",
    "schedule.calendar.meta.never": "Not yet",
    "schedule.calendar.setting.scope.currentValue": "{subs} subscription(s), {entities} unique source(s)",
    "schedule.calendar.health.cached": "Cached sources ready",
    "schedule.calendar.health.partial": "Partially cached",
    "schedule.calendar.health.empty": "No cached lessons yet",
    "schedule.calendar.currentView.title": "Current page preset",
    "schedule.calendar.currentView.description": "Save the current website schedule page as a separate iCal feed. This sync config is stored on the website and does not reuse Telegram quick filters.",
    "schedule.calendar.currentView.save": "Save current view",
    "schedule.calendar.currentView.empty": "Open a schedule first to save the current page as a separate feed.",
    "schedule.calendar.currentView.noModules": "No module filter on this page",
    "schedule.calendar.currentView.allModules": "All modules selected",
    "schedule.calendar.currentView.someModules": "{count} module(s) selected",
    "schedule.calendar.mode.all": "All classes",
    "schedule.calendar.mode.exams": "Exams only",
    "schedule.calendar.delete": "Delete preset",
    "schedule.calendar.confirmReset": "Reset the private calendar link? The previous URL will stop working immediately.",
    "schedule.calendar.confirmEnable": "Enable sync again for all of your website calendar feeds?",
    "schedule.calendar.confirmDisable": "Disable sync for all of your website calendar feeds? Existing external subscriptions will stop updating.",
    "schedule.calendar.confirmDelete": "Delete this saved website calendar preset?"
});

Object.assign(I18N.ru, {
    "schedule.calendar.summaryReady": "Р§Р°СЃС‚РЅС‹Рµ iCal-Р»РµРЅС‚С‹ РґР»СЏ РІР°С€РёС… РІРµР±-РїСЂРѕС„РёР»РµР№ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёРё.",
    "schedule.calendar.summaryPaused": "РЎСЃС‹Р»РєРё РєР°Р»РµРЅРґР°СЂСЏ РЅР° РїР°СѓР·Рµ, РїРѕРєР° РІС‹ СЃРЅРѕРІР° РЅРµ РІРєР»СЋС‡РёС‚Рµ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ.",
    "schedule.calendar.summarySetup": "РЎРѕР·РґР°Р№С‚Рµ С‡Р°СЃС‚РЅС‹Рµ Р»РµРЅС‚С‹ РґР»СЏ РІСЃРµС… Р·Р°РЅСЏС‚РёР№, СЌРєР·Р°РјРµРЅРѕРІ РёР»Рё С‚РµРєСѓС‰РµР№ СЃС‚СЂР°РЅРёС†С‹ СЂР°СЃРїРёСЃР°РЅРёСЏ.",
    "schedule.calendar.statusPaused": "РќР° РїР°СѓР·Рµ",
    "schedule.calendar.pausedNotice": "РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ РЅР° РїР°СѓР·Рµ. Р’РЅРµС€РЅРёРµ РєР°Р»РµРЅРґР°СЂРё РїРµСЂРµСЃС‚Р°РЅСѓС‚ РѕР±РЅРѕРІР»СЏС‚СЊСЃСЏ, РїРѕРєР° РІС‹ РЅРµ РІРєР»СЋС‡РёС‚Рµ РµРµ СЃРЅРѕРІР°.",
    "schedule.calendar.profile.custom": "РџСЂРµСЃРµС‚",
    "schedule.calendar.profile.builtin": "Р‘Р°Р·РѕРІС‹Р№",
    "schedule.calendar.hide": "РЎРєСЂС‹С‚СЊ СЃСЃС‹Р»РєСѓ",
    "schedule.calendar.reveal": "РџРѕРєР°Р·Р°С‚СЊ СЃСЃС‹Р»РєСѓ",
    "schedule.calendar.preview": "РџСЂРѕРІРµСЂРёС‚СЊ Р»РµРЅС‚Сѓ",
    "schedule.calendar.download": "СЃРєР°С‡Р°С‚СЊ .ics",
    "schedule.calendar.disable": "Р’С‹РєР»СЋС‡РёС‚СЊ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ",
    "schedule.calendar.enable": "Р’РєР»СЋС‡РёС‚СЊ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ",
    "schedule.calendar.instructionsTitle": "РљР°Рє РїРѕРґРїРёСЃР°С‚СЊСЃСЏ",
    "schedule.calendar.platform.apple": "РСЃРїРѕР»СЊР·СѓР№С‚Рµ РєРЅРѕРїРєСѓ Apple РЅРёР¶Рµ РёР»Рё РІСЃС‚Р°РІСЊС‚Рµ СЃСЃС‹Р»РєСѓ webcal РІ Apple Calendar РЅР° iPhone, iPad РёР»Рё Mac.",
    "schedule.calendar.platform.google": "РћС‚РєСЂРѕР№С‚Рµ Google Calendar РІ РІРµР±Рµ, РІС‹Р±РµСЂРёС‚Рµ Other calendars, Р·Р°С‚РµРј Add by URL Рё РІСЃС‚Р°РІСЊС‚Рµ HTTPS-СЃСЃС‹Р»РєСѓ.",
    "schedule.calendar.platform.outlook": "Р’ Outlook РёСЃРїРѕР»СЊР·СѓР№С‚Рµ Add calendar РёР»Рё Subscribe from web, Р·Р°С‚РµРј РІСЃС‚Р°РІСЊС‚Рµ HTTPS-СЃСЃС‹Р»РєСѓ Рё РїРѕРґС‚РІРµСЂРґРёС‚Рµ РїРѕРґРїРёСЃРєСѓ.",
    "schedule.calendar.platform.apple.label": "Apple",
    "schedule.calendar.platform.google.label": "Google",
    "schedule.calendar.platform.outlook.label": "Outlook",
    "schedule.calendar.meta.scope": "РћС…РІР°С‚",
    "schedule.calendar.meta.modules": "РњРѕРґСѓР»Рё",
    "schedule.calendar.meta.modulesAll": "Р‘РµР· РѕРіСЂР°РЅРёС‡РµРЅРёР№ РїРѕ РјРѕРґСѓР»СЏРј",
    "schedule.calendar.meta.events": "РЎРѕР±С‹С‚РёР№ РІ Р»РµРЅС‚Рµ",
    "schedule.calendar.meta.next": "Р‘Р»РёР¶Р°Р№С€РµРµ СЃРѕР±С‹С‚РёРµ",
    "schedule.calendar.meta.none": "Р‘Р»РёР¶Р°Р№С€РёС… СЃРѕР±С‹С‚РёР№ РІ РґРёР°РїР°Р·РѕРЅРµ РЅРµС‚",
    "schedule.calendar.meta.health": "РЎРѕСЃС‚РѕСЏРЅРёРµ Р»РµРЅС‚С‹",
    "schedule.calendar.meta.sources": "{used}/{total} РёСЃС‚РѕС‡РЅРёРєРѕРІ РІ РєСЌС€Рµ",
    "schedule.calendar.meta.updated": "РСЃС‚РѕС‡РЅРёРє РѕР±РЅРѕРІР»РµРЅ",
    "schedule.calendar.meta.accessed": "РџРѕСЃР»РµРґРЅРµРµ РІРЅРµС€РЅРµРµ РѕР±СЂР°С‰РµРЅРёРµ",
    "schedule.calendar.meta.generated": "РџСЂРµРІСЊСЋ СЃРѕР·РґР°РЅРѕ",
    "schedule.calendar.meta.never": "Р•С‰Рµ РЅРµС‚",
    "schedule.calendar.setting.scope.currentValue": "{subs} Р°РєС‚РёРІРЅС‹С… РїРѕРґРїРёСЃРѕРє, {entities} СѓРЅРёРєР°Р»СЊРЅС‹С… РёСЃС‚РѕС‡РЅРёРєР°",
    "schedule.calendar.health.cached": "РљСЌС€РёСЂРѕРІР°РЅРЅС‹Рµ РёСЃС‚РѕС‡РЅРёРєРё РіРѕС‚РѕРІС‹",
    "schedule.calendar.health.partial": "Р§Р°СЃС‚СЊ РёСЃС‚РѕС‡РЅРёРєРѕРІ РІ РєСЌС€Рµ",
    "schedule.calendar.health.empty": "Р’ РєСЌС€Рµ РїРѕРєР° РЅРµС‚ Р·Р°РЅСЏС‚РёР№",
    "schedule.calendar.currentView.title": "РџСЂРµСЃРµС‚ С‚РµРєСѓС‰РµР№ СЃС‚СЂР°РЅРёС†С‹",
    "schedule.calendar.currentView.description": "РЎРѕС…СЂР°РЅРёС‚Рµ С‚РµРєСѓС‰СѓСЋ РІРµР±-СЃС‚СЂР°РЅРёС†Сѓ СЂР°СЃРїРёСЃР°РЅРёСЏ РєР°Рє РѕС‚РґРµР»СЊРЅСѓСЋ iCal-Р»РµРЅС‚Сѓ. Р­С‚Р° РЅР°СЃС‚СЂРѕР№РєР° С…СЂР°РЅРёС‚СЃСЏ РЅР° СЃР°Р№С‚Рµ РѕС‚РґРµР»СЊРЅРѕ РѕС‚ Telegram-С„РёР»СЊС‚СЂРѕРІ.",
    "schedule.calendar.currentView.save": "РЎРѕС…СЂР°РЅРёС‚СЊ С‚РµРєСѓС‰РёР№ РІРёРґ",
    "schedule.calendar.currentView.empty": "РЎРЅР°С‡Р°Р»Р° РѕС‚РєСЂРѕР№С‚Рµ СЂР°СЃРїРёСЃР°РЅРёРµ, С‡С‚РѕР±С‹ СЃРѕС…СЂР°РЅРёС‚СЊ С‚РµРєСѓС‰СѓСЋ СЃС‚СЂР°РЅРёС†Сѓ РєР°Рє РѕС‚РґРµР»СЊРЅСѓСЋ Р»РµРЅС‚Сѓ.",
    "schedule.calendar.currentView.noModules": "РќР° СЌС‚РѕР№ СЃС‚СЂР°РЅРёС†Рµ РЅРµС‚ С„РёР»СЊС‚СЂР° РїРѕ РјРѕРґСѓР»СЏРј",
    "schedule.calendar.currentView.allModules": "Р’С‹Р±СЂР°РЅС‹ РІСЃРµ РјРѕРґСѓР»Рё",
    "schedule.calendar.currentView.someModules": "Р’С‹Р±СЂР°РЅРѕ РјРѕРґСѓР»РµР№: {count}",
    "schedule.calendar.mode.all": "Р’СЃРµ Р·Р°РЅСЏС‚РёСЏ",
    "schedule.calendar.mode.exams": "РўРѕР»СЊРєРѕ СЌРєР·Р°РјРµРЅС‹",
    "schedule.calendar.delete": "РЈРґР°Р»РёС‚СЊ РїСЂРµСЃРµС‚",
    "schedule.calendar.confirmReset": "РЎР±СЂРѕСЃРёС‚СЊ С‡Р°СЃС‚РЅСѓСЋ СЃСЃС‹Р»РєСѓ РєР°Р»РµРЅРґР°СЂСЏ? РџСЂРµР¶РЅРёР№ URL СЃСЂР°Р·Сѓ РїРµСЂРµСЃС‚Р°РЅРµС‚ СЂР°Р±РѕС‚Р°С‚СЊ.",
    "schedule.calendar.confirmEnable": "Р’РєР»СЋС‡РёС‚СЊ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ СЃРЅРѕРІР° РґР»СЏ РІСЃРµС… РІРµР±-Р»РµРЅС‚ РєР°Р»РµРЅРґР°СЂСЏ?",
    "schedule.calendar.confirmDisable": "Р’С‹РєР»СЋС‡РёС‚СЊ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ РґР»СЏ РІСЃРµС… РІРµР±-Р»РµРЅС‚ РєР°Р»РµРЅРґР°СЂСЏ? Р’РЅРµС€РЅРёРµ РїРѕРґРїРёСЃРєРё РїРµСЂРµСЃС‚Р°РЅСѓС‚ РѕР±РЅРѕРІР»СЏС‚СЊСЃСЏ.",
    "schedule.calendar.confirmDelete": "РЈРґР°Р»РёС‚СЊ СЌС‚РѕС‚ СЃРѕС…СЂР°РЅРµРЅРЅС‹Р№ РІРµР±-РїСЂРµСЃРµС‚ РєР°Р»РµРЅРґР°СЂСЏ?"
});

const NAV_ITEMS = [
    { href: "/", key: "nav.home" },
    { href: "/#projects", key: "nav.projects" },
    { href: "/schedule", key: "nav.schedule" },
    { href: "/studio", key: "nav.studio" },
    { href: "/stats", key: "nav.admin", adminOnly: true }
];

const navState = {
    lang: "en",
    user: null,
    paletteOpen: false,
    helpOpen: false,
    commandQuery: "",
    selectedCommandIndex: 0,
    activeSection: ""
};
const pageTranslators = new Set();

function getStoredLanguage() {
    const saved = localStorage.getItem(UI_LANG_KEY);
    if (saved === "ru" || saved === "en") return saved;
    const htmlLang = (document.documentElement.lang || "").toLowerCase();
    return htmlLang.startsWith("ru") ? "ru" : "en";
}

function translate(key, fallback = "", params = {}) {
    const source = I18N[navState.lang] || I18N.en;
    const template = source[key] || I18N.en[key] || fallback || key;
    return template.replace(/\{(\w+)\}/g, (_, param) => String(params[param] ?? ""));
}

function setLanguage(lang, { broadcast = true } = {}) {
    if (lang !== "ru" && lang !== "en") return;
    navState.lang = lang;
    localStorage.setItem(UI_LANG_KEY, lang);
    document.documentElement.lang = lang;
    renderNavbar();
    applyTranslations();
    runPageTranslators();
    if (broadcast) {
        window.dispatchEvent(new CustomEvent("mpb-language-change", { detail: { lang } }));
    }
}

function runPageTranslators() {
    pageTranslators.forEach((translator) => {
        try {
            translator(navState.lang, translate);
        } catch (error) {
            console.warn("Page translator failed", error);
        }
    });
}

function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach((element) => {
        const key = element.getAttribute("data-i18n");
        if (!key) return;
        element.textContent = translate(key, element.textContent || "");
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
        const key = element.getAttribute("data-i18n-placeholder");
        if (!key) return;
        element.setAttribute("placeholder", translate(key, element.getAttribute("placeholder") || ""));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((element) => {
        const key = element.getAttribute("data-i18n-title");
        if (!key) return;
        element.setAttribute("title", translate(key, element.getAttribute("title") || ""));
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
        const key = element.getAttribute("data-i18n-aria-label");
        if (!key) return;
        element.setAttribute("aria-label", translate(key, element.getAttribute("aria-label") || ""));
    });
}

function normalizePath(path) {
    if (!path) return "/";
    return path.endsWith("/") && path !== "/" ? path.slice(0, -1) : path;
}

function isActiveNavItem(item) {
    const pathname = normalizePath(window.location.pathname);
    if (item.href === "/") {
        return pathname === "/" && window.location.hash !== "#projects" && navState.activeSection !== "projects";
    }
    if (item.href === "/#projects") {
        return pathname === "/" && (window.location.hash === "#projects" || navState.activeSection === "projects");
    }
    return pathname === normalizePath(item.href);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function shouldShowNavItem(item) {
    if (!item.adminOnly) return true;
    return navState.user?.role === "admin";
}

function getProfileLink() {
    if (!navState.user) return "/login";
    return navState.user.role === "admin" ? "/stats" : "/schedule";
}

function getAvatarHtml(sizeClass = "w-6 h-6", textClass = "text-xs") {
    const username = (navState.user?.username || "?").trim();
    const initial = username.length > 0 ? username[0].toUpperCase() : "?";
    if (navState.user?.avatar_url) {
        return `<img src="${escapeHtml(navState.user.avatar_url)}" class="${sizeClass} rounded-full object-cover shrink-0 border border-slate-200" alt="${escapeHtml(username)}">`;
    }
    return `<div class="${sizeClass} rounded-full bg-blue-600 text-white flex items-center justify-center ${textClass} font-bold shrink-0">${escapeHtml(initial)}</div>`;
}

function renderDesktopAuth() {
    if (!navState.user) {
        return `
            <a href="/login" class="group relative px-5 py-2.5 bg-slate-900 text-white rounded-full font-medium overflow-hidden shadow-lg shadow-slate-900/20 hover:shadow-slate-900/40 transition-all">
                <span class="relative z-10 flex items-center gap-2">${translate("nav.signIn")}</span>
                <span class="absolute inset-0 bg-gradient-to-r from-blue-600 to-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></span>
            </a>
        `;
    }

    return `
        <a href="${getProfileLink()}" class="flex items-center gap-2 px-4 py-2 rounded-full border border-slate-200 hover:border-blue-400 hover:bg-blue-50 transition-colors max-w-[220px]">
            ${getAvatarHtml("w-6 h-6", "text-xs")}
            <span class="text-sm font-bold text-slate-700 truncate">${escapeHtml(navState.user.username || "")}</span>
        </a>
        <button type="button" data-logout-btn class="text-sm font-medium text-slate-400 hover:text-red-500 transition-colors">${translate("nav.logout")}</button>
    `;
}

function renderMobileAuth() {
    if (!navState.user) {
        return `
            <a href="/login" class="block mt-4 px-3 py-3 rounded-lg text-base font-medium text-center bg-blue-600 text-white hover:bg-blue-700 transition-colors">
                ${translate("nav.signIn")}
            </a>
        `;
    }

    return `
        <div class="mt-4 pt-4 border-t border-slate-100">
            <a href="${getProfileLink()}" class="flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-slate-50 transition-colors">
                ${getAvatarHtml("w-8 h-8", "text-sm")}
                <div class="overflow-hidden">
                    <div class="text-sm font-bold text-slate-900 truncate">${escapeHtml(navState.user.username || "")}</div>
                    <div class="text-xs text-slate-500">${translate("nav.profile")}</div>
                </div>
            </a>
            <button type="button" data-logout-btn class="w-full text-left mt-2 px-3 py-3 rounded-lg text-red-500 font-medium hover:bg-red-50 transition-colors">
                ${translate("nav.logoutAccount")}
            </button>
        </div>
    `;
}

function renderLanguageToggle(isMobile = false) {
    const base = isMobile
        ? "mt-3 w-full flex items-center gap-2 rounded-xl bg-slate-100 p-1"
        : "hidden lg:flex items-center gap-1 rounded-full bg-slate-100 p-1";
    return `
        <div class="${base}">
            <button type="button" data-lang="en" aria-pressed="${navState.lang === "en"}" class="js-lang-switch px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${navState.lang === "en" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}">${translate("lang.en")}</button>
            <button type="button" data-lang="ru" aria-pressed="${navState.lang === "ru"}" class="js-lang-switch px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${navState.lang === "ru" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}">${translate("lang.ru")}</button>
        </div>
    `;
}

function renderNavbar() {
    const desktopRoot = document.getElementById("desktop-nav-links");
    const mobileRoot = document.getElementById("mobile-nav-links");

    const links = NAV_ITEMS.filter(shouldShowNavItem);

    if (desktopRoot) {
        const linksHtml = links
            .map((item) => {
                const active = isActiveNavItem(item);
                const classes = active
                    ? "text-blue-700 bg-blue-50 border border-blue-200"
                    : "text-slate-600 hover:text-blue-600 hover:bg-blue-50 border border-transparent";
                return `<a href="${item.href}" class="px-3 py-2 rounded-xl text-sm font-semibold transition-colors ${classes}">${translate(item.key)}</a>`;
            })
            .join("");

        desktopRoot.innerHTML = `
            ${linksHtml}
            <div id="desktop-auth-container" class="flex items-center gap-3">${renderDesktopAuth()}</div>
            ${renderLanguageToggle(false)}
        `;
    }

    if (mobileRoot) {
        const mobileLinksHtml = links
            .map((item) => {
                const active = isActiveNavItem(item);
                const classes = active
                    ? "text-blue-700 bg-blue-50 border border-blue-200"
                    : "text-slate-700 hover:text-blue-600 hover:bg-blue-50 border border-transparent";
                return `<a href="${item.href}" class="block px-3 py-3 rounded-lg text-base font-medium transition-colors ${classes}">${translate(item.key)}</a>`;
            })
            .join("");

        mobileRoot.innerHTML = `
            ${mobileLinksHtml}
            ${renderLanguageToggle(true)}
            <div id="mobile-auth-container">${renderMobileAuth()}</div>
        `;
    }
}

window.performLogout = function performLogout() {
    localStorage.removeItem("jwt_token");
    window.location.href = "/login";
};

async function checkAuthAndRenderNavbar() {
    const token = localStorage.getItem("jwt_token");
    if (!token) {
        navState.user = null;
        renderNavbar();
        window.dispatchEvent(new CustomEvent("mpb-auth-ready", { detail: { user: null } }));
        return;
    }

    try {
        const response = await fetch(`${NAV_API_BASE}/auth/me`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        if (response.ok) {
            navState.user = await response.json();
        } else {
            navState.user = null;
            localStorage.removeItem("jwt_token");
            if (normalizePath(window.location.pathname) === "/stats") {
                window.location.href = "/login";
            }
        }
    } catch (error) {
        console.error("Auth check failed", error);
        navState.user = null;
    }

    renderNavbar();
    window.dispatchEvent(new CustomEvent("mpb-auth-ready", { detail: { user: navState.user } }));
}

function setupMobileMenu() {
    const button = document.getElementById("mobile-menu-button");
    const menu = document.getElementById("mobile-menu");
    if (!button || !menu) return;

    button.setAttribute("aria-label", translate("nav.menu"));
    button.setAttribute("aria-controls", "mobile-menu");
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", () => {
        menu.classList.toggle("hidden");
        button.setAttribute("aria-expanded", String(!menu.classList.contains("hidden")));
    });

    menu.addEventListener("click", (event) => {
        const target = event.target;
        if (target instanceof HTMLElement && target.closest("a")) {
            menu.classList.add("hidden");
            button.setAttribute("aria-expanded", "false");
        }
    });
}

function setupHomeSectionSpy() {
    if (normalizePath(window.location.pathname) !== "/") return;
    const projectsSection = document.getElementById("projects");
    if (!(projectsSection instanceof HTMLElement)) return;

    const observer = new IntersectionObserver(
        (entries) => {
            const nextSection = entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.35)
                ? "projects"
                : "";
            if (navState.activeSection !== nextSection && window.location.hash !== "#projects") {
                navState.activeSection = nextSection;
                renderNavbar();
            }
        },
        {
            threshold: [0.2, 0.35, 0.6],
            rootMargin: "-120px 0px -35% 0px",
        }
    );

    observer.observe(projectsSection);
}

function setupNavbarScrollBehavior() {
    const navbar = document.getElementById("navbar");
    if (!navbar) return;

    let lastScrollY = window.scrollY;
    let ticking = false;
    const scrollThreshold = 100;

    function updateNavbar() {
        const currentScrollY = window.scrollY;
        if (currentScrollY > scrollThreshold) {
            if (currentScrollY > lastScrollY && currentScrollY > 200) {
                navbar.classList.add("nav-hidden");
                navbar.classList.remove("nav-visible");
            } else {
                navbar.classList.remove("nav-hidden");
                navbar.classList.add("nav-visible");
            }
        } else {
            navbar.classList.remove("nav-hidden");
            navbar.classList.add("nav-visible");
        }

        navbar.classList.toggle("shadow-md", currentScrollY > 20);
        lastScrollY = currentScrollY;
        ticking = false;
    }

    window.addEventListener(
        "scroll",
        () => {
            if (!ticking) {
                window.requestAnimationFrame(updateNavbar);
                ticking = true;
            }
        },
        { passive: true }
    );
}

function getCommandPaletteCommands() {
    const commands = [
        { id: "go-home", label: translate("nav.home"), run: () => (window.location.href = "/") },
        { id: "go-projects", label: translate("nav.projects"), run: () => (window.location.href = "/#projects") },
        { id: "go-schedule", label: translate("nav.schedule"), run: () => (window.location.href = "/schedule") },
        { id: "go-studio", label: translate("nav.studio"), run: () => (window.location.href = "/studio") },
        {
            id: "refresh",
            label: translate("palette.refresh"),
            run: () => window.dispatchEvent(new CustomEvent("mpb-shortcut-refresh"))
        },
        {
            id: "toggle-language",
            label: translate("palette.toggleLang"),
            run: () => setLanguage(navState.lang === "ru" ? "en" : "ru")
        },
        {
            id: "open-help",
            label: translate("palette.openHelp"),
            run: () => toggleShortcutHelp(true)
        }
    ];

    if (navState.user?.role === "admin") {
        commands.splice(4, 0, {
            id: "go-admin",
            label: translate("nav.admin"),
            run: () => (window.location.href = "/stats")
        });
    }

    return commands;
}

function ensureOverlays() {
    if (document.getElementById("mpbCommandPalette")) return;

    const overlays = document.createElement("div");
    overlays.innerHTML = `
        <div id="mpbCommandPalette" class="hidden fixed inset-0 z-[120] bg-slate-900/50 backdrop-blur-sm px-4">
            <div class="mx-auto mt-20 w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-2xl">
                <div class="border-b border-slate-100 p-4">
                    <p class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500" data-i18n="palette.title"></p>
                    <input id="mpbCommandInput" type="text" class="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500" data-i18n-placeholder="palette.placeholder" placeholder="">
                </div>
                <div id="mpbCommandList" class="max-h-[22rem] overflow-y-auto p-2"></div>
            </div>
        </div>
        <div id="mpbShortcutHelp" class="hidden fixed inset-0 z-[120] bg-slate-900/50 backdrop-blur-sm px-4">
            <div class="mx-auto mt-24 w-full max-w-xl rounded-2xl border border-slate-200 bg-white shadow-2xl">
                <div class="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                    <h2 class="text-lg font-bold text-slate-900" data-i18n="help.title"></h2>
                    <button type="button" data-close-help class="rounded-lg px-3 py-1 text-sm text-slate-500 hover:bg-slate-100">Esc</button>
                </div>
                <div class="space-y-3 px-5 py-4 text-sm text-slate-700">
                    <div class="flex items-center justify-between"><span data-i18n="help.palette"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">Ctrl/Cmd + K</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.focusSearch"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">/</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.refresh"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">R</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.nextPage"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">N</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.prevPage"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">P</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.open"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">?</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.close"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">Esc</kbd></div>
                    <p class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500" data-i18n="help.hint"></p>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(overlays);
    applyTranslations();
}

function getVisibleCommands() {
    const query = navState.commandQuery.trim().toLowerCase();
    const commands = getCommandPaletteCommands();
    if (!query) return commands;
    return commands.filter((command) => command.label.toLowerCase().includes(query));
}

function renderCommandList() {
    const list = document.getElementById("mpbCommandList");
    if (!list) return;

    const commands = getVisibleCommands();
    navState.selectedCommandIndex = Math.min(navState.selectedCommandIndex, Math.max(commands.length - 1, 0));

    if (commands.length === 0) {
        list.innerHTML = `<div class="rounded-xl px-3 py-3 text-sm text-slate-500">${translate("palette.empty")}</div>`;
        return;
    }

    list.innerHTML = commands
        .map((command, index) => {
            const selected = index === navState.selectedCommandIndex;
            return `
                <button type="button" data-command-id="${command.id}" class="w-full rounded-xl px-3 py-2 text-left text-sm transition-colors ${selected ? "bg-blue-50 text-blue-700" : "text-slate-700 hover:bg-slate-100"}">
                    ${escapeHtml(command.label)}
                </button>
            `;
        })
        .join("");
}

function openCommandPalette() {
    ensureOverlays();
    const palette = document.getElementById("mpbCommandPalette");
    const input = document.getElementById("mpbCommandInput");
    if (!palette || !input) return;

    navState.paletteOpen = true;
    navState.commandQuery = "";
    navState.selectedCommandIndex = 0;
    palette.classList.remove("hidden");
    input.value = "";
    renderCommandList();
    window.setTimeout(() => input.focus(), 20);
}

function closeCommandPalette() {
    const palette = document.getElementById("mpbCommandPalette");
    if (!palette) return;
    navState.paletteOpen = false;
    palette.classList.add("hidden");
}

function runSelectedCommand() {
    const commands = getVisibleCommands();
    if (commands.length === 0) return;
    const selected = commands[navState.selectedCommandIndex] || commands[0];
    if (!selected) return;
    closeCommandPalette();
    selected.run();
}

function toggleShortcutHelp(forceOpen) {
    ensureOverlays();
    const modal = document.getElementById("mpbShortcutHelp");
    if (!modal) return;

    const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : !navState.helpOpen;
    navState.helpOpen = shouldOpen;
    modal.classList.toggle("hidden", !shouldOpen);
}

function focusPrimarySearch() {
    const target = document.querySelector(
        '[data-search-input], #groupSearch, #leaderboardSearch, input[type="search"]'
    );
    if (!(target instanceof HTMLElement)) return;
    target.focus();
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
        target.select?.();
    }
}

function registerGlobalHandlers() {
    document.body.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;

        const langButton = target.closest(".js-lang-switch");
        if (langButton instanceof HTMLElement) {
            const lang = langButton.getAttribute("data-lang");
            if (lang) setLanguage(lang);
            return;
        }

        if (target.closest("[data-logout-btn]")) {
            window.performLogout();
            return;
        }

        const commandButton = target.closest("[data-command-id]");
        if (commandButton instanceof HTMLElement) {
            const commandId = commandButton.getAttribute("data-command-id");
            const command = getVisibleCommands().find((entry) => entry.id === commandId);
            if (command) {
                closeCommandPalette();
                command.run();
            }
            return;
        }

        if (target.closest("[data-close-help]")) {
            toggleShortcutHelp(false);
        }
    });

    document.addEventListener("keydown", (event) => {
        const isMetaK = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
        if (isMetaK) {
            event.preventDefault();
            if (navState.paletteOpen) {
                closeCommandPalette();
            } else {
                openCommandPalette();
            }
            return;
        }

        const activeTag = document.activeElement?.tagName || "";
        const isTypingContext =
            activeTag === "INPUT" ||
            activeTag === "TEXTAREA" ||
            document.activeElement?.getAttribute("contenteditable") === "true";

        if (navState.paletteOpen) {
            if (event.key === "Escape") {
                closeCommandPalette();
                return;
            }
            if (event.key === "ArrowDown") {
                event.preventDefault();
                const commands = getVisibleCommands();
                if (commands.length > 0) {
                    navState.selectedCommandIndex = Math.min(navState.selectedCommandIndex + 1, commands.length - 1);
                    renderCommandList();
                }
                return;
            }
            if (event.key === "ArrowUp") {
                event.preventDefault();
                navState.selectedCommandIndex = Math.max(navState.selectedCommandIndex - 1, 0);
                renderCommandList();
                return;
            }
            if (event.key === "Enter") {
                event.preventDefault();
                runSelectedCommand();
                return;
            }
        }

        if (event.key === "Escape") {
            const mobileMenu = document.getElementById("mobile-menu");
            const mobileMenuButton = document.getElementById("mobile-menu-button");
            if (mobileMenu && !mobileMenu.classList.contains("hidden")) {
                mobileMenu.classList.add("hidden");
                mobileMenuButton?.setAttribute("aria-expanded", "false");
            }
            toggleShortcutHelp(false);
            closeCommandPalette();
            return;
        }

        if (isTypingContext) return;

        if (event.key === "?" || (event.key === "/" && event.shiftKey)) {
            event.preventDefault();
            toggleShortcutHelp(true);
            return;
        }

        if (event.key === "/") {
            event.preventDefault();
            focusPrimarySearch();
            return;
        }

        if (event.key.toLowerCase() === "r") {
            window.dispatchEvent(new CustomEvent("mpb-shortcut-refresh"));
            return;
        }

        if (event.key.toLowerCase() === "n") {
            window.dispatchEvent(new CustomEvent("mpb-shortcut-pagination", { detail: { direction: "next" } }));
            return;
        }

        if (event.key.toLowerCase() === "p") {
            window.dispatchEvent(new CustomEvent("mpb-shortcut-pagination", { detail: { direction: "prev" } }));
            return;
        }

        if (event.altKey && event.key.toLowerCase() === "l") {
            event.preventDefault();
            setLanguage(navState.lang === "ru" ? "en" : "ru");
        }
    });

    document.addEventListener("input", (event) => {
        const input = document.getElementById("mpbCommandInput");
        if (!input) return;
        if (event.target === input) {
            navState.commandQuery = input.value;
            navState.selectedCommandIndex = 0;
            renderCommandList();
        }
    });
}

function exposePublicI18nApi() {
    window.mpbI18n = {
        getLanguage: () => navState.lang,
        setLanguage: (lang) => setLanguage(lang),
        t: (key, fallback = "", params = {}) => translate(key, fallback, params),
        applyTranslations,
        registerTranslator: (fn) => {
            if (typeof fn !== "function") return () => {};
            pageTranslators.add(fn);
            try {
                fn(navState.lang, translate);
            } catch (error) {
                console.warn("Page translator registration failed", error);
            }
            return () => pageTranslators.delete(fn);
        },
        unregisterTranslator: (fn) => pageTranslators.delete(fn),
    };
}

document.addEventListener("DOMContentLoaded", () => {
    navState.lang = getStoredLanguage();
    document.documentElement.lang = navState.lang;
    exposePublicI18nApi();

    setupMobileMenu();
    setupNavbarScrollBehavior();
    setupHomeSectionSpy();
    registerGlobalHandlers();
    checkAuthAndRenderNavbar();
    ensureOverlays();
    applyTranslations();
    runPageTranslators();
    window.addEventListener("hashchange", renderNavbar);
    window.addEventListener("popstate", renderNavbar);
});
