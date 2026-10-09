# calendar_sync.js

Общий редактор календарных подписок для `/schedule` и `/account`. Использует
существующий API `/cal/subscription`: загрузка, выбор профиля, создание,
редактирование фильтров/часового пояса, удаление, отключение и смена приватной ссылки.

Обычный режим читает состояние schedule.js. Для другой страницы задать
`window.MpbCalendarHost` **до** загрузки скрипта: `user`, `entity`, `modules`,
`selectedModules`, `onState(state)`, `onProfileSelected(profile)` и
`openSchedule(profile)`. Пример адаптера — account_subscriptions.js.

Основные точки входа: `openCalendarSyncPanel`, `closeCalendarSyncPanel`,
`refreshCalendarSubscription`, `selectCalendarSubscriptionProfile`,
`updateCalendarSubscriptionProfile`, `deleteCalendarSubscriptionProfile`.
Хост получает изменения через onState даже при закрытом dialog. Доступ к
переменным расписания из ветки хоста не допускается. Ответы привязаны к JWT и
порядку запросов; личные ответы не кэшируются HTTP.

`calendarFocus` (совместимый экспорт `MpbScheduleUX.calendarFocus`) теперь
принадлежит этому скрипту. Он делает соседей inert, блокирует скролл, удерживает
Tab с учётом закрытых details, затем восстанавливает overflow, скролл и кнопку
открытия по стабильному ID, даже если список подписок перерисовался.

Зависимости: shared i18n, runtime API base, calendar_sync.css, DOM-узлы
calendarSubscriptionSection/calendarSubscriptionBackdrop непосредственно в body.
CalendarHost необязателен. Выбор платформы и факт раскрытия профиля сохраняются
локально; сама приватная ссылка — нет. Clipboard, навигация в приложение календаря
и мутации выполняются по явным действиям пользователя. Ошибки и закрытие во время
загрузки не должны возвращать окно на экран. Браузерные регрессии нужны для обоих
хостов, мобильных форм, языка, темы, клавиатуры и API-ошибок.
