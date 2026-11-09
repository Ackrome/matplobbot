# `paging.js`

## Purpose

Parses canonical 64-bit x86-64 virtual addresses and renders the 48-bit, four-level page-table walk into the SVG in `paging.html`.

## Public surface

The module binds the page controls and exposes no global API.

## Usage

Load it after the page markup. It accepts hexadecimal canonical lower-half or upper-half addresses with optional underscores and uses `BigInt` for bit extraction.

## Dependencies

Browser DOM, SVG, and `BigInt`; no libraries or backend calls.

## Side effects

Replaces the diagram children and updates ARIA live status/error messages.

## Maintenance

Keep the canonical-address bounds, masks, bit shifts, labels, ARIA IDs, and explanatory text synchronized when changing the paging model.
