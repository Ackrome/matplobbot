# test_build_audit_requirements.py

## Purpose

Tests the audit requirements builder used by CI and deployment security gates.

## Public Tests

- `TestBuildAuditRequirements.test_builds_deduplicated_filtered_requirements`: verifies comments, editable installs, local package exclusions, duplicate pins, extras, and inline comments are handled correctly.
- `TestBuildAuditRequirements.test_conflicting_pins_fail_closed`: verifies conflicting package pins raise instead of silently producing an unsafe audit input.

## Usage

```bash
python -m unittest tests.test_build_audit_requirements -v
```

## Dependencies

Uses only Python standard library modules: `importlib.util`, `pathlib`, `tempfile`, and `unittest`.

## Side Effects

Creates temporary requirements files and an audit output file inside `TemporaryDirectory`; no repository files are modified.

## Maintenance Notes

Keep these tests aligned with the filtering rules in `scripts/build_audit_requirements.py`. Add a test before allowing new requirement-file syntax so CI cannot silently drop packages from the security audit.
