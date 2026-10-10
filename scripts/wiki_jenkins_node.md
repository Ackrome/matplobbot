# jenkins_node.py

Provides a reproducible Node runtime for the Jenkins frontend regression gate.
`configuration()` validates the checked-in version/platform/checksum pin;
`provision()` downloads the official archive on a cache miss, verifies SHA-256,
copies only its single regular `bin/node` member, and checks the executable's exact
version, platform and architecture before returning its directory. `main()` prints
only that directory, so Jenkins can prepend it to PATH within the quality shell.

```sh
NODE_BIN_DIR="$(python scripts/jenkins_node.py)"
export PATH="$NODE_BIN_DIR:$PATH"
unset NODE_OPTIONS NODE_PATH
node --version
```

Dependencies are Python 3.11+ standard library, Linux x86_64 and HTTPS access to
nodejs.org on the first run. The default cache is the current user's private
`~/.cache/matplobbot/node`; it is outside the repository and deployment inputs.
No root access, global installation, package manager, npm or general tar extraction
is used. Directory ownership/permissions, target symlinks, archive checksum and
binary content are checked. Unique staging directories and atomic replacement
prevent partial downloads/executables from becoming cache entries. A corrupt
archive fails closed; a modified cached binary is restored from the verified
archive before any execution. The metadata probe has a minimal environment.

Update `node_runtime.json` only from official release checksums and align the
GitHub setup-node pin. Run the focused tests and replay the real Jenkins-user
quality gate after changing the runtime. Do not substitute a manually installed
host Node or a mutable latest/LTS download URL for the pinned contract.
