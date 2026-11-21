# Deployed release evidence lookup

`ReleaseEvidence.resolve()` finds a completed `ci-cd.yml` main push whose exact
`Deploy and Verify Jenkins Smoke` job succeeded. It selects the latest deployment
completion among the recent workflow runs. An explicit `--run-id` selects only
that run. It verifies the Actions ZIP checksum, archived source SHA and run ID,
four immutable image references and their RC acceptance record. An expired
artifact from the latest successful deployment is unavailable evidence.

```sh
python3 scripts/release_baseline.py --output previous-accepted-release.json
```

The CLI uses `GITHUB_REPOSITORY` and `GH_TOKEN` with Actions read permission.
The standard library handles HTTPS, JSON and ZIP input. The GitHub credential
stays on the GitHub API request when an artifact download redirects. The script
writes a small JSON record with `passed`, `unsupported` or `error` and does not
contact the deployment host. Keep the workflow path, smoke job name and artifact
naming convention aligned with `ci-cd.yml`.
