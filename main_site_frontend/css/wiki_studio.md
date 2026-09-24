# Studio stylesheet

## Purpose

`studio.css` contains the page-specific layout, preview, dark-theme, and Telegram Web App
styles formerly embedded in `studio.html`. Keeping these rules in a versioned same-origin asset
allows the Studio CSP to reject inline style elements.

## Public surface and usage

The stylesheet is loaded only by `/studio` through `/css/studio.css?v=1`. Its selectors depend on
the existing Studio element IDs and on the `dark` and `tg-webapp` classes applied to the root HTML
element.

## Dependencies and side effects

The rules complement the generated Tailwind stylesheet. Monaco and Split.js still apply runtime
style attributes, so the Studio CSP intentionally permits inline style attributes while rejecting
inline scripts and event attributes.

## Maintenance

When changing this file, increment its query-string version in `studio.html`, update the same URL
in `service-worker.js`, bump the service-worker cache version, and run the Studio CSP/browser tests.
