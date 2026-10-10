# jenkins_release_parameters.py

Migrates an existing Jenkins job before `buildWithParameters` so new release inputs
cannot be silently dropped. `configure(xml)` adds missing `SOURCE_COMMIT`
string and `RELEASE_MANIFEST_B64` text definitions and clears their defaults. It
requires the known Git-backed CpsScmFlowDefinition and `Jenkinsfile.groovy`, changes
its sole main branch selector to `${SOURCE_COMMIT}`, and disables lightweight
checkout for parameter expansion. Unexpected job/SCM/branch/script or parameter
types fail. All other configuration and credential references remain unchanged.
`install(fetch, job, apply=False)` checks, optionally compares and saves configuration,
then verifies parameters and SCM binding again. CLI defaults to dry run; `--apply` explicitly writes and never queues
a build. Example: `python scripts/jenkins_release_parameters.py --job-url
http://jenkins-lan:8080/job/matplobbot-deploy --resolve-ip 192.168.1.130 --apply`.

Dependencies: Python standard library, curl and `JENKINS_USER`/`JENKINS_TOKEN`.
The workflow uses its existing Jenkins credential and verified LAN resolution.
Credentials stay in curl's stdin configuration; private temporary XML/cookie files
are deleted, response bodies are not logged, and redirects are not followed.
Read/Configure denial fails before deployment. Jenkins lacks atomic config CAS;
avoid concurrent operator edits despite the immediate before-write comparison.
Tests cover idempotence, unrelated configuration preservation, conflict refusal,
dry-run behavior, concurrent edits and reread verification.
