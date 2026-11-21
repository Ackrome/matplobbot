# Jenkins deployment waiter tests

`TestJenkinsDeployment` runs the real curl transport against a loopback-only
Jenkins HTTP fixture. It verifies the authenticated submit, exact queue and build
identity, matching smoke artifact, safe output, terminal failures, cancellation,
timeouts and a dropped dispatch response. Run it with
`python -m unittest discover -s tests -p test_jenkins_deploy_wait.py`.

The suite uses the Python standard library and curl. It starts a temporary HTTP
server on a random local port and closes it after each test. The payload and
credentials belong to the fixture. Keep the fixture contract aligned with the
Jenkins Remote API and `Jenkinsfile.groovy` after changes to either.

The same HTTP fixture covers a valid sanitized failure artifact, unavailable
diagnostics, and rejection of foreign commit/build IDs, unapproved stage/code
pairs and extra fields. Failure paths do not read the success artifact.
It also checks that a prepare status is valid during production deployment,
while an early-only preflight status is rejected during that stage.
