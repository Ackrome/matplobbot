# `fourier.js`

## Purpose

Computes a deterministic discrete Fourier representation of the sample contour and animates its epicycles on Canvas 2D.

## Public surface

The page controls are the public interface; the module is intentionally self-contained.

## Usage

Load it after `fourier.html`. Change the harmonic count, speed, or playback state to explore the reconstruction.

## Dependencies

Browser Canvas 2D, `requestAnimationFrame`, `ResizeObserver`-free resize handling, and `matchMedia` for reduced motion.

## Side effects

Runs a bounded animation trace in memory while playback is active. No network or storage access occurs.

## Maintenance

Keep the sample count and coefficient ordering stable when comparing screenshots or adding tests. Preserve the paused initial state for reduced-motion users.
