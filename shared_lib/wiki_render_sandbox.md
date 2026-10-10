# Render sandbox

`render_sandbox.py` is the mandatory boundary around every server compiler subprocess.
`sandbox_command(command, workdir=..., resources=...)` creates a bubblewrap invocation
with private namespaces, no network, a minimal filesystem, cleared environment,
read-only installed runtimes and explicit trusted resource files. Only the fresh job
directory is writable and visible from the worker. `run_render_process` executes it
through Studio's cancellation-aware process transport. It fails closed on Windows,
root execution, missing tools, or denied kernel/container namespace operations.

Example: `run_render_process(["latexmk", "-norc", "-no-shell-escape", "main.tex"],
workdir=job_directory, capture_output=True, timeout=50)`.

Dependencies: Linux user namespaces, bubblewrap, util-linux prlimit, and the worker
runtime packages. CPU time, process count, descriptors and individual file sizes are
bounded; Compose additionally caps worker memory, PIDs and the writable temporary
filesystem. Cancellation and timeout kill the sandbox process group; successful
exit also terminates the private PID namespace, including detached descendants.
Before the worker reads any output, the job directory is checked with `lstat` and
symlinks/FIFOs/devices are rejected. No secret
environment, application checkout, host temporary files, sockets, or host processes
are mounted. Trusted resource paths are supplied by server code, never API inputs.

Maintain the explicit runtime allowlist when upgrading TeX/Chromium; do not replace it
with a read-only bind of `/`, which would expose credentials. A deployment must pass
the real container isolation/compile tests as the image's non-root `appuser`;
do not add an unsandboxed fallback or deploy the worker with a root user override.
