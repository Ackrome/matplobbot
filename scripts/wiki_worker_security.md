# Worker runtime security policy selection

`worker_security.py` binds the worker's named AppArmor user-namespace permission to
the exact repository policy bytes. It uses only Python's standard library and
the Docker CLI; installation additionally needs Linux root and AppArmor 4.0.

- `profile_name(root)` derives an immutable name from the policy template SHA-256.
- `profile_text(root)` renders its exact UTF-8 source.
- `docker_uses_apparmor()` queries Docker's security options, including when the
  client and daemon run on different operating systems.
- `apparmor_security_option(root)` verifies the exact protected, root-owned
  persistent policy file on an AppArmor daemon host. It raises on missing,
  different, symlinked or writable policy. A daemon without AppArmor returns
  `None`, so callers omit the AppArmor option for Docker Desktop compatibility.
- `verify_installed_profile(name, text)` validates retained policy identity and
  installed bytes for rollback, without relying on the current source checkout.
- `install_policy(root)` performs explicitly authorized root provisioning only.
  It adds one hash-named file and loads it if absent, never replaces a different
  file or reloads a live policy, and retains older profiles for rollback.

Examples:

```sh
python scripts/worker_security.py policy-name
python scripts/worker_security.py emit-profile
sudo python3 scripts/worker_security.py install
python scripts/worker_security.py check
```

Run installation/checks on the Docker daemon host when AppArmor is enabled; a
remote client must not substitute its own policy store. Non-root Docker-group
users cannot read the kernel's loaded-profile list on Ubuntu; root installation
checks that list, while ordinary selection must be followed by an actual named
profile container and isolated renderer probe before maintenance. Compose must
receive exactly one AppArmor option, because ordinary sequence merging can retain
both old and new labels. Record the selected policy with the release's runtime
configuration and preserve old profile files for rollback and reboot.

Policy loading is the only mutating operation. It changes neither global kernel
settings nor other profiles, containers, images or network configuration. A
parser failure leaves a matching persistent file for diagnosis and an explicit
retry; rendering remains fail-closed. Tests cover content drift, missing/incorrect
runtime state, daemon capability errors and add-only installation behavior.
