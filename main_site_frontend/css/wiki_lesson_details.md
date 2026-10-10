# lesson_details.css

Стили модального окна `MpbLessonDetails` из `js/lesson_details.js`.
Все внутренние правила ограничены `.lesson-details-dialog`; используются
существующие `--schedule-*` цвета и класс `.dark`.

## Основные компоненты

`ld-header` закрепляет полное название и закрытие, `ld-tabs` оформляет вкладки,
`ld-body`/`dl` — поля занятия, `ld-occurrence` — список связанных записей,
`ld-footer` — основные действия, `ld-copy` — запасной способ копирования.
`ld-curriculum` — компактная отдельная секция учебного плана над кэшем занятий;
`ld-assessment-badges` группирует формы аттестации, `ld-assessment-sources` содержит
ссылки на документ/страницу, `ld-curriculum-provenance` — сведения об источнике.
Подтверждённые сведения используют `--ld-tint`; неизвестное состояние — нейтральный
фон. Другие семестры раскрываются без расширения модального окна.
На компьютере ширина ограничена 670 px, высота — текущим viewport. На телефоне
до 600 px окно занимает весь экран с safe-area, поля становятся одноколоночными.
Backdrop повторяет размытие 10 px у окна календаря.

## Использование и зависимости

Подключается в `schedule.html` после базовых стилей; DOM создаёт lesson_details.js.
Например, `<dialog class="lesson-details-dialog">` с `showModal()` получает фон,
обводку и ограничение высоты. Скрытые вкладки используют атрибут `hidden`.
Стиль `.schedule-feed-card-title.lesson-details-button` сохраняет оформление
заголовка мобильной карточки после превращения его в доступную кнопку.

## Побочные эффекты и сопровождение

CSS не меняет геометрию таблицы. Блокировка/восстановление прокрутки принадлежит JS;
стабильный scrollbar-gutter страницы задан в calendar_sync.css. Правило
`[data-lesson-card]` обозначает кликабельную карточку курсором.
При изменениях проверять длинный заголовок, почту, адрес, список дисциплины,
фокус и прокрутку на 320/390/820/1440/1920 px, RU/EN и светлой/тёмной теме.
Не задавать dialog постоянный display, который покажет закрытое окно.
## Separate teacher ratings

`.ld-teachers` contains one identity and MyPrepod card per lecturer. The compact
`.ld-teacher-rating` uses the dialog's existing light/dark variables, wraps long
names and metadata, and separates percentage, sample counts, provenance and stale
states. Teacher schedule and retry controls retain visible keyboard focus and
44-pixel mobile targets. Do not use stars or color thresholds that imply teaching
quality; the source percentage measures loyalty. Async updates affect only the
individual rating card and preserve dialog scroll.
