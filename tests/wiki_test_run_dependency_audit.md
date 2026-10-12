# test_run_dependency_audit.py

## Purpose

Verify that temporary PyPI failures can recover while the dependency security gate
continues to reject vulnerabilities, incomplete audits and permanent errors.

## Main components

- `TestNetworkErrorClassification` checks typed transport errors, selected HTTP
  statuses, TLS exclusions and cyclic cause/context graphs.
- `TestRealAuditEntrypoint` runs the real installed `pip_audit` module entrypoint.
  Only dependency collection and HTTP responses are replaced with fixtures; the
  actual scanner parsing, PyPI response handling, strict mode, ignore policy and
  exit behavior are exercised, including a finding after a recovered timeout.
- `TestAuditProviderParity` checks both GitHub workflows and Jenkins use the shared
  runner with a twenty-minute wall-clock limit.

## Usage

```powershell
./.venv/Scripts/python.exe -m unittest tests.test_run_dependency_audit -v
```

## Dependencies and side effects

Uses unittest, requests, PyYAML, packaging and the pinned validation dependency
`pip-audit`. Fixtures create temporary requirement files and fake HTTP responses.
No real dependency installation, external request, waiting or deployment occurs.
Tests capture scanner output, restore `sys.argv` and remove temporary files.

## Maintenance

Keep the real-entrypoint cases when upgrading pip-audit: upstream may change how
network errors are wrapped in service errors or `SystemExit`. A security finding
following a timeout must stop immediately, without inheriting an earlier error's
context. TLS errors veto retry even when another exception-graph branch contains a
retryable timeout. Keep provider checks aligned with intentional timeout changes.
