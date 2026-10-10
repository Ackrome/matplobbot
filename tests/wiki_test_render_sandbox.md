# Renderer isolation regressions

`test_render_sandbox.py` verifies filename policy and fail-closed behavior everywhere.
With `RENDER_SANDBOX_INTEGRATION=1`, it must run in the actual Linux worker image:
`python -m unittest tests.test_render_sandbox -v`. The explicit opt-in fails on a
missing/denied sandbox instead of silently skipping the runtime checks.

Tests compile a normal PDF, verify that local latexmk configuration does not run,
probe synthetic filesystem/environment canaries, reject network connections and
writes to runtime mounts, and prove cleanup of a background child on timeout and
successful exit (including a detached session and a delayed symlink writer).
Root execution and unsafe output filesystem entries are rejected. The full task
probe compiles quick LaTeX, a project, a formula, Markdown, Mermaid, and Markdown
with a Mermaid image verified in its resulting PDF. All inputs
are generated in temporary directories; no production services, secrets or accounts
are used. Dependencies are the built worker runtime, Pillow and unittest. Keep the
runtime suite in the release container gate whenever namespace/profile settings change.
