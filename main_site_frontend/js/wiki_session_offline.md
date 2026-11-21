# Saved public semester

`MpbSessionOffline.save(plan, dates)` saves one explicitly selected public
semester in this browser. It projects the group, term, forms and observed
events into a bounded record. It carries the capture time and RUZ check time.
Only a verified plan can be saved. Missing dates remain missing.

`read()` validates the current saved record. `url(saved)` opens that record
directly through the cached schedule shell. `remove()` clears the record.
`available()` checks that a service worker controls the document and its cache
contains the schedule shell and the versioned snapshot helper. Call it before
offering confirmation that a copy is available offline.
Saving another semester replaces the old copy after confirmation in the UI.
Storage errors leave the previous copy intact.

This helper has no API or account dependencies. It uses browser localStorage
and URLSearchParams. Payloads are limited to 500 plan rows, 1000 date events and
250000 serialized characters. It never stores credentials, private settings,
calendar URLs or an arbitrary API response. The service worker does not cache
Session API requests. Clear browser storage or use the Remove action to forget
the saved public data.
