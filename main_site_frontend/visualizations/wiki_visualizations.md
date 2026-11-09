# `visualizations.css`

## Purpose

Shared visual language for the standalone educational laboratory pages.

## Public surface

Classes prefixed with `lab-` provide the shell, cards, controls, stage, status messages, responsive layout, and focus treatment.

## Usage

Link the stylesheet from a direct visualization page. It consumes Matplobbot's `--ui-*` theme variable names and supplies fallbacks when the shared stylesheet is absent.

## Dependencies

System fonts and CSS only. The `.dark` class is recognized by the existing theme bootstrap.

## Side effects

Styles are scoped to the `lab-` namespace except for the page-level body and theme variables.

## Maintenance

Preserve the mobile breakpoint, visible focus ring, and `prefers-reduced-motion` block when adding new widgets.
