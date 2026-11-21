# Jenkins production preflight

`jenkins_production_preflight.sh` checks the production host before Jenkins runs
dependency installs, tests or image pulls. Jenkins pins the accepted commit and
then invokes `bash scripts/jenkins_production_preflight.sh` with its existing SSH
key binding, private host, ED25519 fingerprint and live deployment path.

The script archives a fixed list of files from `SOURCE_COMMIT` and uses Git,
OpenSSH, tar and the host Python to run the reviewed `release_deploy.py preflight`
in a temporary directory. Both sides remove their temporary files. The probe
reads Git status, deployed release state, filesystem capacity and installed
worker policy. It does not write to the live checkout, switch containers, pull
images or clean disk caches. A connection or stuck preflight is time bounded.

When maintaining the check, keep the archive list aligned with the preflight's
imports and worker template, and keep the exit status mapping in Jenkins and
the failure codes accepted by `jenkins_deploy_wait.py` aligned. Keep the
fingerprint check and strict checking against the exact scanned host key. Repair
or bootstrap the live checkout separately if the probe cannot open it.
