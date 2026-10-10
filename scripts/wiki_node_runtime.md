# node_runtime.json

Checked-in Node runtime pin shared by the Jenkins bootstrap contract and the
GitHub Actions setup-node version. Fields are exact `version`, `platform`,
`architecture` and SHA-256 of the official release archive. The current target is
Linux x64 Node 24.21.0 (Krypton LTS), verified on 2026-10-10 against the official
[release index](https://nodejs.org/dist/index.json) and
[SHASUMS256.txt](https://nodejs.org/dist/v24.21.0/SHASUMS256.txt).
The [release schedule](https://github.com/nodejs/Release) lists Node 24 as supported
through April 2028; Node 20 is already end-of-life.

`jenkins_node.configuration()` consumes this file. No execution or side effects
occur from reading it; provisioning uses only the official HTTPS origin and this
checksum. On update, review the official checksum, change the exact setup-node
version in `.github/workflows/ci-cd.yml`, run `tests.test_jenkins_node`, and repeat
the actual Jenkins-user gate. Versioned cache entries leave other runtimes intact.
