# Worker AppArmor policy preflight regressions

`test_worker_security.py` verifies the pure policy selection and guarded host
provisioning contract in `scripts/worker_security.py`. Run it with
`python -m unittest tests.test_worker_security -v` from the repository root.

`WorkerPolicyTests` checks immutable content-derived names, retained rollback
identity, exact protected root-owned installed bytes, missing policy, symlinks,
malformed daemon capability responses, daemon-based no-AppArmor handling, and
root-only add-only provisioning that never reloads an existing matching policy.
Temporary directories and mocked subprocesses keep these tests portable and
side-effect-free; they neither load a host profile nor create containers.

They deliberately do not claim kernel compatibility. Run the real
`test_render_sandbox.py` integration suite in the accepted worker image under the
exact named profile, including all six formats and isolation/process regressions,
on an AppArmor host. Ordinary non-root preflight cannot read AppArmor securityfs;
the actual named-profile container probe must establish loadedness before any
deployment or rollback maintenance.
