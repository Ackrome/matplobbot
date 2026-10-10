# Studio project asset policy

`allowed_project_path(path)` accepts relative, non-hidden TeX/Markdown/Mermaid text,
data, raster images, PDF and PostScript assets. Compiler configuration, executable
scripts, HTML/SVG and traversal paths are excluded. API uploads and renames use the
same policy as worker snapshots, including legacy database records.

`raster_content_type(bytes)` verifies actual PNG/JPEG/GIF/WebP content with Pillow
and a bounded pixel count. It returns an inline MIME only for a valid raster. Other
downloads use attachment/octet-stream plus restrictive CSP and nosniff.

Usage: reject an upload unless `allowed_project_path(filename)`; call
`raster_content_type(content)` before choosing inline image delivery. Constants
bound one asset (5 MiB), one build (20 MiB), and files per build (100).

Dependencies: Pillow and Python standard library. There are no filesystem/network
side effects. Do not add formats based solely on extensions: review compiler
auto-loading and browser active-content behavior before extending the allowlist.
