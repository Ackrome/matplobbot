# Studio stylesheet

## Purpose

`studio.css` contains the page-specific layout, preview, dark-theme, and Telegram Web App
styles formerly embedded in `studio.html`. Keeping these rules in a versioned same-origin asset
allows the Studio CSP to reject inline style elements.

## Public surface and usage

The stylesheet is loaded by `/studio` and its same-origin Monaco frame through `/css/studio.css?v=2`. Its selectors depend on
the existing Studio element IDs and on the `dark` and `tg-webapp` classes applied to the root HTML
element.

The workspace uses remaining dynamic viewport height, including toolbars, mobile tabs, and
status notices. Mobile pane positioning and controls work from 320 pixels; touch file actions
remain visible. Fallback textarea and Monaco frame styles share the same editor container.
Focus indicators, selected states, reduced motion, and modal overflow rules support keyboard
and small-screen use without hiding autosave errors.

## Dependencies and side effects

The rules complement the generated Tailwind stylesheet. Monaco and Split.js still apply runtime
style attributes, so the Studio CSP intentionally permits inline style attributes while rejecting
inline scripts and event attributes.

## Maintenance

When changing this file, increment its query-string version in `studio.html`, update the same URL
in `service-worker.js`, bump the service-worker cache version, and run the Studio CSP/browser tests.
