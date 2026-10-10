# Worker syscall profile

`worker-seccomp.json` is copied from the Apache-2.0-licensed Moby profiles project:
https://github.com/moby/profiles/blob/main/seccomp/default.json
Source downloaded 2026-10-10; source SHA-256:
`6416b47770785a41ac59073cdc77d9fe98517df2799dc83ef207e622de3053f6`.

It retains Docker's default-deny syscall policy, with explicit namespace setup
exceptions for `clone`, `unshare`, `setns`, `mount`, `umount2`, `pivot_root`, `chroot`
and `mount_setattr`. These let a non-root worker create bubblewrap's nested user,
mount, network and PID namespaces. All container capabilities are dropped and
no-new-privileges is enabled. No Docker socket or host namespace is exposed.

Compose selects this profile only for the compiler worker. Its outer AppArmor
profile is unconfined because Docker's generic profile denies nested mounts;
bubblewrap installs the actual minimal filesystem/process/network boundary before
any untrusted source is parsed. Other services retain Docker's default policies.

Revalidate the real integration suite after changing Docker, kernel, bubblewrap,
or this profile. Do not replace it with seccomp=unconfined. Deployments whose host
policy forbids unprivileged user namespaces must fail the render acceptance gate.
