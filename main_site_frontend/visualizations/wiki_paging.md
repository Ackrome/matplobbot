# `paging.html`

## Purpose

Standalone QR destination for a four-level x86-64 virtual-address walk.

## Public surface

The address input, parse/step/reset buttons, and TLB-hit simulation are the user-facing controls.

## Usage

Open `/visualizations/paging` or `/visualizations/paging.html`, enter a 48-bit canonical address, and step through the SVG diagram.

## Dependencies

`visualizations.css` and `js/paging.js`; no external libraries or API calls.

## Side effects

Updates an inline SVG and an ARIA live status region only.

## Maintenance

The demo intentionally models 4 KiB pages, four levels, and 48-bit canonical addresses. Extend the explanation and bit masks together if LA57 or huge pages are added.
