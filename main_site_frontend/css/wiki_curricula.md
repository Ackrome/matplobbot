# Curriculum workspace styles

`curricula.css` styles the administrator document workspace: metadata grid,
source actions, editable assessment table, group/semester rows and status notes.
It is loaded by `curricula.html` after shared Tailwind/product styles.

Example: `.curricula-card` wraps each import/review/binding step;
`.curricula-scroll` contains the deliberately wide assessment table so narrow
screens scroll only the table, not the page. At 640 px the metadata grid stacks
and semester fields use two columns.

Dependencies are ordinary CSS and the shared `.dark` theme class. Side effects
are visual only; interactive rules target `.curricula-main`. Keep visible focus
rings, input contrast and horizontal scroll containment. Check 320 px and desktop
widths in both languages/themes whenever row fields or labels change.

OCR progress uses `.curricula-processing` and a separate error treatment. The
`.curricula-preview` native dialog contains one lazily created scan fragment;
its backdrop blurs the workspace and its `.curricula-preview-image` region
scrolls horizontally instead of widening the page. The image keeps a minimum
readable width on mobile; keyboard users can focus the scroll region. Do not
remove the viewport-height bounds, visible focus ring or dark-theme contrast.
