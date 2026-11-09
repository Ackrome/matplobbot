# `kernel-trick.html`

## Purpose

Standalone QR destination for the Kernel Trick lesson.

## Public surface

The page exposes 2D/3D view buttons, a separating-plane height slider and a live status region.

## Usage

Open `/visualizations/kernel-trick` or `/visualizations/kernel-trick.html`. The page is intentionally outside the global navbar and API flows.

## Dependencies

`visualizations.css`, `js/kernel-trick.js`, and pinned Three.js r128 plus OrbitControls loaded from unpkg with SRI.

## Side effects

Creates a WebGL canvas and animation loop. No account, backend or persistent state is used.

## Maintenance

Preserve the statement that `φ(x,y)=(x,y,x²+y²)` makes this finite fixed dataset linearly separable in 3D; do not describe the page as an implementation of SVM training unless an optimization solver is added and audited separately.
