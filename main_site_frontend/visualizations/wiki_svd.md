# `svd.html`

## Purpose

Standalone QR destination for the SVD sphere-to-ellipsoid lesson.

## Public surface

The page exposes the `phase` and `sigma3` range controls and mounts the Three.js scene in `#svd-stage`.

## Usage

Open `/visualizations/svd` or `/visualizations/svd.html`. The page is intentionally independent of the global navbar and API.

## Dependencies

`visualizations.css`, `js/svd.js`, and pinned Three.js r128 plus OrbitControls loaded from unpkg with SRI.

## Side effects

Creates a WebGL canvas and an animation loop. It does not read account data or call the backend.

## Maintenance

Keep the Three.js versions and integrity hashes together. Update the fallback message if the renderer requirements change.
