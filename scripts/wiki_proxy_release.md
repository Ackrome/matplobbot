# Independent proxy release

On the Docker host, in the live application checkout, use the exact image and
source commit from a successful **Proxy Image Release** workflow.

```sh
python3 scripts/proxy_release.py apply --commit "$SOURCE_SHA" --image "$PROXY_DIGEST"
python3 scripts/proxy_release.py rollback
```

`apply()` pulls and checks the OCI digest and revision, then recreates only the
`proxy` service with the existing Compose configuration, cache and secret mounts.
`rollback()` restores the previous known image without a pull. An existing local
image can serve as the observed baseline for the first managed rollout.

The tool needs Docker Compose, registry access for `apply`, Linux file locks,
the managed application checkout and its existing proxy settings. It checks
container health and a SOCKS request to Telegram before recording success.
A failed candidate triggers recovery. If recovery cannot be verified, the
private attempt record remains and `rollback` retries its saved target.
The application rollout shares the maintenance lock and honors the proxy's
separately recorded image during an application rollback. The fixed retained
image tags protect the current and rollback versions from ordinary dangling
image cleanup. Do not edit `.release-state` records or remove retained images
while recovery is pending.
