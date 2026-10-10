# test_jenkins_node.py

`JenkinsNodeTests` exercises real temporary archive/cache operations with synthetic
binary contents; only download, host identity and process execution are replaced.
It proves that checksum failures precede parsing/execution, a tar symlink cannot
be extracted, cached executable corruption is repaired from verified bytes,
unsupported hosts and wrong runtime metadata fail, and both gates bind the same
checked-in version. Platform ownership checks are replaced for Windows portability.

Run `python -m unittest tests.test_jenkins_node -v` with the project virtualenv.
Dependencies are unittest, PyYAML and `scripts/jenkins_node.py`. Tests create only
temporary directories and perform no network calls or real Node execution.
Actual download/platform execution and the complete Jenkins Python 3.12 gate must
also pass before accepting a runtime change; these fixtures do not replace that
host proof. Extend negative tests when changing cache or extraction behavior.
