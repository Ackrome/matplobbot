# calendar_sync.css

Styles for the schedule subscription dialog rendered by `js/calendar_sync.js`.

## Main components

`#calendarSubscriptionSection` is a centered, scrollable 590 px dialog. At 600 px
and below it becomes a full-screen sheet with safe-area padding. The separate
backdrop does not participate in the schedule layout. `.calendar-source`,
`.calendar-apps`, `.calendar-primary`, and `.calendar-disclosure` provide the
source summary, app choice, primary action, and secondary settings.

## Usage

Load after `product_ui.css` in schedule.html:
`<link rel="stylesheet" href="/css/calendar_sync.css?v=20261009-7">`.
The script toggles `hidden` and `is-open` on the dialog and backdrop.

## Dependencies and side effects

Uses schedule theme variables and the root `.dark` class. Adds stable scrollbar
space above 600 px to avoid width changes during modal scroll locking. The mobile
sheet uses the whole viewport without reserving a scrollbar gutter.
Focus trapping, background inertness, and scroll restoration belong to
`MpbScheduleUX.calendarFocus` in schedule_workspace.js.

## Maintenance

Keep the first screen focused on subscription source, app selection and its
primary action. Secondary controls must wrap by available dialog width. Verify
desktop/mobile, long RU/EN names, dark theme, expanded settings, loading and
errors. Bump the stylesheet URL and service-worker cache after changes.
