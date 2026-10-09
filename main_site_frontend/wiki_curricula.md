# Curriculum administration page

`curricula.html` is the administrator workspace at `/curricula`, linked from
`/stats`. The static shell contains no protected information. `curricula.js`
loads documents only through API endpoints guarded by `require_admin`.

The page provides document registration, official URL refresh, manual PDF
upload, assessment review/publication and explicit group/semester binding.
For example, register a programme's official plan, check its candidate rows
against the saved PDF, publish, then enter a RUZ group ID and semester dates.

Dependencies: shared navbar, runtime API configuration, theme bootstrap,
RU/EN locale loader, `css/curricula.css`, `js/curricula.js`. Mutations persist
through the API; no curriculum contents or credentials are saved in browser
storage. The normal existing JWT is used for authorization.

Maintain coherent script/style/locale versions in this file and the service
worker. The deployment nginx configuration permits PDF uploads up to 20 MiB
only on the curriculum document endpoint; the API applies its own bound.

Do not add guessed group-to-programme mappings or publish parser output without
document review. Scanned documents require manual entry; the supported parser
does not perform OCR.
