# Wait for the Jenkins deployment

`jenkins_deploy_wait.py` preflights the Jenkins job parameters and submits one
accepted release. `deploy()` follows the queue item returned by that submit,
verifies its build number and queue ID, and checks the archived smoke result for
the same commit. `JenkinsTransport` pins requests to the LAN address with curl.

```sh
python3 scripts/jenkins_deploy_wait.py \
  --job-url http://192.168.1.130:8080/job/matplobbot-deploy \
  --resolve-ip 192.168.1.130 --deploy-host 192.168.1.40 \
  --commit "$GITHUB_SHA" --manifest release-manifest-accepted.json
```

The workflow runs the Jenkins SCM and parameter installer first. The caller
provides the existing `JENKINS_USER` and `JENKINS_TOKEN` environment values. The
helper uses the Python standard library, curl and the Remote API. It submits a
deployment and reports the exact queue and build links in the Actions summary.
Jenkins must archive `release-smoke.json` after its post-deploy smoke step. The
CI identity needs access to the queue, the job and build artifact.

For a completed `FAILURE`, Jenkins also archives `release-failure.json`. The
waiter accepts only a matching commit and build number, with an approved stage
and code, from the exact queued build. It displays the code in the Actions
summary and keeps the run failed. Missing or invalid diagnostics fall back to
the original Jenkins result. The artifact never carries an exception string,
console output, credentials or arbitrary context.
The production deployment stage can report the same checkout and resource
blockers as the early preflight when `release_deploy.py prepare` detects them
before maintenance. Jenkins captures the status of that SSH invocation separately
from other commands in the stage.

Polling uses a single 40-minute budget. A timeout or interrupted dispatch can
leave an accepted build running. Inspect the recorded Jenkins queue or build
before deliberately rerunning. The helper retries transient reads and makes one
dispatch attempt. Capped response bodies stay out of the Actions summary.
