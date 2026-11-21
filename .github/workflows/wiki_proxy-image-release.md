# Proxy Image Release workflow

The manual GitHub Actions workflow builds the selected `main` commit's proxy
image and tests it in an isolated Docker container. It uploads `proxy-release.json`
with the exact source commit, GHCR digest and checked image ID. Each run pushes
a separate registry tag, and consumers use the digest from the report.

Dispatch **Proxy Image Release** on `main`. The job requires Docker, GitHub
packages write access and the existing repository token. It publishes an image
only after a real SOCKS request through the local listener succeeds. It does
not contact the deployment host. Use `scripts/proxy_release.py` for deliberate
production rollout and recovery.
