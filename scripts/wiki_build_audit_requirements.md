# build_audit_requirements.py

## Purpose

Builds the filtered `audit-requirements.txt` file consumed by `pip-audit` gates.

## Public Functions

- `build_audit_requirements(requirement_files, output_path, excluded_packages)`: reads one or more requirements files, skips editable/local packages, deduplicates matching package pins, fails on conflicting pins, writes the filtered output, and returns the emitted lines.
- `parse_args(argv)`: parses CLI arguments for custom input files, output path, and excluded package names.
- `main(argv=None)`: command-line entry point.

## Usage

```bash
python scripts/build_audit_requirements.py
python scripts/build_audit_requirements.py -o audit-requirements.txt
python scripts/build_audit_requirements.py -r requirements.txt -r scheduler_app/requirements.txt
```

## Dependencies

Only Python standard library modules are used: `argparse`, `pathlib`, and `sys`.

## Side Effects

Writes the selected output file, `audit-requirements.txt` by default. The script raises an error for nested requirement includes, constraints, unsupported pip options, and conflicting pins so the audit gate fails closed.

## Maintenance Notes

Keep `DEFAULT_REQUIREMENT_FILES` aligned with runtime requirement files used by Docker, CI, and deployment. Add exclusions only for local in-repo packages that cannot be audited as third-party distributions, and document any scanner-level advisory ignore in the calling workflow.
