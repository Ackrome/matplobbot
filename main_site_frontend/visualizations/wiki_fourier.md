# `fourier.html`

## Purpose

Standalone QR destination showing a closed contour reconstructed by Fourier epicycles.

## Public surface

The harmonics and speed sliders, pause/resume button, and trace reset button control the canvas lesson.

## Usage

Open `/visualizations/fourier` or `/visualizations/fourier.html`. The page works without an account or backend connection.

## Dependencies

`visualizations.css` and `js/fourier.js`; the renderer uses the browser Canvas 2D API.

## Side effects

Runs a requestAnimationFrame loop while the lesson is playing and keeps a bounded in-memory trace.

## Maintenance

Keep the sample contour and coefficient ordering deterministic so screenshots and explanations remain reproducible.
