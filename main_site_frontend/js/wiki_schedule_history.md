# Schedule history panel

`MpbScheduleHistory.render(container, {entity, eventKey, onClose, onChange})` renders
the public schedule history for an entity or one accepted source event. It reuses
`ScheduleApi.requestJson` and the shared locale dictionaries. A typical caller
derives the resolved entity ID from the current timetable and passes a rerender
callback. `count(entity, eventKey)` reads the loaded entry count and `reset()` aborts
the current request and discards its state when users close or switch schedules.

The panel displays before/after fields and provides plain links to the original
week or a unique surviving lesson. It renders remote strings as DOM text and
does not persist them in browser storage. Version the script and matching service
worker entry together. Keep linked and empty history distinguishable from an
API/network failure and preserve Russian and English locale key parity.
