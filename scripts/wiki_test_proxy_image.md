# Isolated proxy image smoke test

Run `bash scripts/test_proxy_image.sh matplobbot-proxy:test` to verify a built
image starts its configuration service and accepts SOCKS requests to its own
health endpoint. The new container uses an isolated network namespace with only
loopback, and a temporary cache. The script removes its own container on exit.

It needs Bash, the Docker CLI, an available image and the curl included in that
image. This check exercises the real listener with no external traffic or
subscriptions. The host deployment tool separately verifies external egress.
