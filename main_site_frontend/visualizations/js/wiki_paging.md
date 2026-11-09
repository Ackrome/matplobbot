# `paging.js`

## Purpose

Parses a 48-bit virtual address and renders the current page-table walk into the SVG in `paging.html`.

## Public surface

The module binds the page controls and exposes no global API.

## Usage

Load it after the page markup. It accepts hexadecimal addresses with optional underscores and uses `BigInt` for bit extraction.

## Dependencies

Browser DOM, SVG, and `BigInt`; no libraries or backend calls.

## Side effects

Replaces the diagram children and updates ARIA live status/error messages.

## Maintenance

Keep the masks, bit shifts, labels, and explanatory text synchronized when changing the paging model.
