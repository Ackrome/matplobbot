# `kernel-trick.js`

## Purpose

Renders the fixed concentric-disk/annulus kernel-trick demonstration for `kernel-trick.html`.

## Public surface

The page-scoped module binds the 2D/3D toggle and plane-height range control. It exposes no global API.

## Usage

Load it after Three.js r128 and OrbitControls. The feature map is fixed as `φ(x, y) = (x, y, x² + y²)`.

## Dependencies

Three.js r128, OrbitControls, the browser DOM and shared `visualizations.css` styles.

## Side effects

Creates a WebGL scene and animation loop. It updates point positions, a circular boundary, the separating plane and live status text. It performs no network calls beyond the page's pinned CDN scripts and stores no state.

## Maintenance

Keep the deterministic red disk/blue annulus gap, plane-height range and explanatory caveat synchronized. This is a separability demonstration for a fixed feature map, not a quadratic-program SVM trainer or a proof of maximum margin.
