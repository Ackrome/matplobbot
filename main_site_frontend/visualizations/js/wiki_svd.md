# `svd.js`

## Purpose

Drives the SVD Three.js scene used by `svd.html`.

## Public surface

The module is page-scoped and initializes from the existing `#phase` and `#sigma3` controls. It has no exported globals.

## Usage

Load it after Three.js and OrbitControls. It creates the renderer, scene, grid, source sphere, transformed mesh, resize observer, and animation loop.

## Dependencies

Three.js r128, OrbitControls, and the shared `lab-*` CSS.

## Side effects

Creates WebGL resources and updates the live status text. It does not persist state.

## Maintenance

Keep geometry updates bounded and retain the WebGL fallback. Any change to the CDN version requires new SRI hashes.
