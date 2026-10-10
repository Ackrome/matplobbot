# Worker AppArmor policy template

`worker-apparmor.template` provides the explicit user-namespace permission needed
by bubblewrap on Ubuntu 24.04 with AppArmor's restricted unprivileged namespaces.
Only worker and disposable probe containers select the generated profile. There
is no executable-path attachment and no global sysctl change.

`scripts/worker_security.py` hashes every template byte, replaces its single
`@PROFILE_NAME@` placeholder, and verifies or installs that exact named policy.
For example, `python scripts/worker_security.py emit-profile` prints the source;
an authorized root operator runs `install` on the Docker daemon host. The file
persists under `/etc/apparmor.d` and previous hash-named profiles remain for rollback.

The profile uses Ubuntu's documented `flags=(unconfined) { userns, }` exception.
It is not the renderer's isolation boundary. Non-root execution, capability drop,
seccomp, no-new-privileges, read-only container root, resource limits, and the
mandatory bubblewrap filesystem/network/PID namespaces remain required. Missing
or mismatched policy must fail before deployment stops live services. An AppArmor
4.0 parser and kernel are required on hosts that use this policy; Docker daemons
without AppArmor use the existing independent sandbox boundary.

Any template edit intentionally creates a new profile name. Do not replace or
remove a profile used by an existing container or retained release. Verify the
actual six-format render suite and isolation regressions on the destination
kernel before treating a policy change as accepted.

On the Ubuntu 6.8 host, Docker's default masked/read-only proc paths also prevent
bubblewrap from mounting a fresh proc filesystem in its new PID namespace. Only
worker and disposable probe containers use `systempaths=unconfined` to permit
that mount. This does not bind the outer `/proc` into the renderer. Non-root UID,
zero effective/permitted/bounding capabilities, no-new-privileges and denied
kernel-setting writes are checked in both the outer worker and inner sandbox;
the separate PID/filesystem/network and child-cleanup regressions still apply.
See [Moby's nested rootless-container explanation](https://github.com/moby/buildkit/blob/master/docs/rootless.md#docker).

Primary reference: [Ubuntu 24.04 release notes](https://documentation.ubuntu.com/release-notes/24.04/#unprivileged-user-namespace-restrictions).
