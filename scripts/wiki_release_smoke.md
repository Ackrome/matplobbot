# release_smoke.sh

Runs the post-deployment acceptance sequence from a checked-in file. Usage on the
application host, from its release checkout:

```sh
bash scripts/release_smoke.sh <accepted-40-character-commit> </dev/null
```

The script reads effective API-container administrator settings with shell-safe
quoting, then checks API and scheduler health, positive administrator login,
authenticated leaderboard access, local/public WebSocket upgrades and anonymous
access rejection. Credentials and bearer tokens are never printed. Temporary
login responses are removed on exit.

Only after these checks does it call `deploy.sh --finalize`. A final Python check
requires `current.json` to be successful for the expected commit and all pending
markers to be absent. The completion line contains that verified commit. Jenkins
requires the exact line independently of SSH's exit status.

Dependencies: Bash, Docker Compose, curl, Python 3, sed, grep, mktemp and the deployed
application. Side effects: deployment-administrator login, authenticated health
requests and finalizing the release pointer after positive checks. It does not
deploy images or migrate schemas. Run only for the authorized candidate release.

Never stream this script to `bash -s`: Docker Compose `exec -T` disables the TTY
but can still consume inherited stdin. Jenkins build 347 returned zero while its
credential-read command drained the remaining streamed script. File execution and
explicit `/dev/null` on credential reading and finalization prevent that failure.
Keep tests that actively drain input and require the exact completion marker;
ordinary mocked exit codes did not detect this bug.
