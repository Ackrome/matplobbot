# Shared feature panels

`feature_panels.css` styles the new schedule planner and admin outcome panels within the existing static design.

## Public surface and usage

Apply `mpb-panel` to a section or details element, `mpb-fields` to flexible controls, `mpb-scroll` around wide tables and `mpb-warning` to incomplete-data notices. Load the versioned stylesheet on Schedule and Stats.

## Dependencies and effects

Plain CSS with no framework dependency. Selectors are scoped to these panels, with `html.dark` overrides. Controls have 44px minimum height, visible keyboard focus and wrapping on narrow screens.

## Maintenance

Preserve contrast, dark-theme readability, label associations in HTML and mobile horizontal overflow behavior. Update manual asset/cache versions after changes and inspect at 390px and desktop widths.
