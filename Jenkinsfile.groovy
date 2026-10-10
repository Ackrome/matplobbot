pipeline {
    agent any

    parameters {
        string(name: 'SOURCE_COMMIT', defaultValue: '', description: 'Required full source commit accepted by CI')
        text(name: 'RELEASE_MANIFEST_B64', defaultValue: '', description: 'Base64 accepted CI manifest, including immutable image digests and RC/restore evidence')
        string(name: 'DEPLOY_HOST', defaultValue: '192.168.1.40', description: 'LAN hostname or private IP of app-vm; it must resolve to exactly one RFC1918 address')
        string(name: 'DEPLOY_HOST_FINGERPRINT', defaultValue: '', description: 'Optional override for pinned SHA256 host key fingerprint from APP_VM_SHA256')
        string(name: 'DEPLOY_ADMIN_USERNAME', defaultValue: 'matplobbot-deploy', description: 'Dedicated unlinked password administrator for deployment smoke checks; never use a Telegram or ordinary account')
    }


    environment {
        DEFAULT_DEPLOY_HOST_FINGERPRINT = credentials('APP_VM_SHA256')
        DEPLOY_PATH = '~/matplobbot'

        PROD_BOT_TOKEN = credentials('PROD_BOT_TOKEN')
        PROD_ADMIN_USER_IDS = credentials('PROD_ADMIN_USER_IDS')
        PROD_GITHUB_TOKEN = credentials('PROD_GITHUB_TOKEN')
        PROD_POSTGRES_USER = credentials('PROD_POSTGRES_USER')
        PROD_POSTGRES_PASSWORD = credentials('PROD_POSTGRES_PASSWORD')
        PROD_POSTGRES_DB = credentials('PROD_POSTGRES_DB')
        PROD_STATS_PASS = credentials('PROD_STATS_PASS')
        PROD_PUBLIC_API_URL = credentials('PROD_PUBLIC_API_URL')
        PROD_PUBLIC_SITE_URL = credentials('PROD_PUBLIC_SITE_URL')
        PROD_JWT_SECRET_KEY = credentials('PROD_JWT_SECRET_KEY')
        PROD_SUB_URL = credentials('PROD_SUB_URL')
        PROD_MAIL_CREDENTIAL_KEY = credentials('MAIL_CREDENTIAL_KEY')
    }

    options { disableConcurrentBuilds() }

    stages {
        stage('Pin Accepted Source') {
            steps {
                sh '''
                    set -eu
                    printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'
                    test -n "$RELEASE_MANIFEST_B64"
                    # The job's SCM definition must itself load Jenkinsfile from this SHA.
                    test "$(git rev-parse HEAD)" = "$SOURCE_COMMIT"
                    git fetch origin "$SOURCE_COMMIT"
                    git checkout --detach "$SOURCE_COMMIT"
                    mkdir -p .release-state
                    python3 scripts/release_manifest.py decode --commit "$SOURCE_COMMIT" --output .release-state/accepted.json
                    python3 scripts/release_manifest.py verify .release-state/accepted.json --require-rc
                '''
            }
        }

        stage('Pre-Deploy Quality Gate') {
            steps {
                script {
                    env.FAIL_STAGE = 'Pre-Deploy Quality Gate'
                    sh '''
                        bash -euo pipefail <<'BASH'

                        LOG_FILE="$WORKSPACE/quality_gate_stage.log"
                        : > "$LOG_FILE"
                        {

                        PYTHON_BIN="${PYTHON_BIN:-python3}"
                        if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
                          PYTHON_BIN=python
                        fi
                        if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
                          echo "ERROR: python3/python is required for the pre-deploy quality gate."
                          exit 1
                        fi

                        "$PYTHON_BIN" -m venv .jenkins-venv
                        . .jenkins-venv/bin/activate

                        python -m pip install --upgrade pip
                        python -m pip install -e .
                        python -m pip install -r requirements.txt -r fastapi_stats_app/requirements.txt -r scheduler_app/requirements.txt
                        python -m pip install -r requirements-validation.txt

                        python - <<'PY'
import importlib
import sys

required_modules = [
    "aiohttp",
    "aiogram",
    "fastapi",
    "fastapi.testclient",
    "passlib",
    "sqlalchemy",
    "yaml",
]
missing = []
for module_name in required_modules:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        missing.append(f"{module_name}: {exc}")

if missing:
    print("ERROR: required test/runtime imports are unavailable:")
    for item in missing:
        print(f"- {item}")
    sys.exit(1)
PY

                        ruff check . --select E9,F63,F7,F82

                        python scripts/build_audit_requirements.py
                        # PYSEC-2024-277 is a disputed joblib deserialization advisory with no fixed
                        # release as of 2026-05-20. It is pulled transitively by matplobblib via
                        # scikit-learn, and this project does not load untrusted joblib pickle files.
                        python -m pip_audit --strict -r audit-requirements.txt \
                          --ignore-vuln PYSEC-2024-277

                        export JWT_SECRET_KEY="jenkins-test-secret"
                        export BOT_TOKEN="123456:test-token"
                        export ADMIN_USER_IDS=""

                        NODE_BIN_DIR="$(python scripts/jenkins_node.py)"
                        export PATH="$NODE_BIN_DIR:$PATH"
                        unset NODE_OPTIONS NODE_PATH
                        node --version
                        set +e
                        coverage run --branch -m unittest discover -s tests -v 2>&1 | tee unittest_output.log
                        test_status="${PIPESTATUS[0]}"
                        set -e
                        if [ "$test_status" -ne 0 ]; then
                          exit "$test_status"
                        fi

                        if grep -Eiq 'fastapi is not installed|ModuleNotFoundError|No module named' unittest_output.log; then
                          echo "ERROR: unittest output indicates tests were skipped or degraded because dependencies are missing."
                          exit 1
                        fi

                        coverage report --skip-covered
                        } 2>&1 | tee -a "$LOG_FILE"
BASH
                    '''
                }
            }
        }

        stage('Deploy to Production') {
            steps {
                script {
                    env.FAIL_STAGE = 'Deploy to Production'
                    withCredentials([sshUserPrivateKey(credentialsId: 'app-vm-ssh-key', keyFileVariable: 'SSH_KEY_FILE', usernameVariable: 'SSH_USER')]) {
                        withEnv(["RELEASE_SOURCE=${params.SOURCE_COMMIT}"]) {
                            sh '''
                                bash -euo pipefail <<'BASH'

                                LOG_FILE="$WORKSPACE/deploy_stage.log"
                                : > "$LOG_FILE"
                                {

                                chmod 600 "$SSH_KEY_FILE"
                                DEPLOY_HOST="$(bash "$WORKSPACE/scripts/resolve_private_ipv4.sh" "${DEPLOY_HOST:-192.168.1.40}")"

                                mkdir -p "$HOME/.ssh"
                                touch "$HOME/.ssh/known_hosts"

                                # Strict host key pinning by fingerprint.
                                # The Jenkins credential APP_VM_SHA256 is the default source.
                                # The DEPLOY_HOST_FINGERPRINT build parameter can override it when needed.
                                EFFECTIVE_DEPLOY_HOST_FINGERPRINT="${DEPLOY_HOST_FINGERPRINT:-${DEFAULT_DEPLOY_HOST_FINGERPRINT:-}}"
                                if [ -z "$EFFECTIVE_DEPLOY_HOST_FINGERPRINT" ]; then
                                  echo "ERROR: no deploy host fingerprint configured. Set Jenkins credential APP_VM_SHA256 or provide DEPLOY_HOST_FINGERPRINT."
                                  exit 1
                                fi

                                SCANNED_FP="$(ssh-keyscan -T 5 -t ed25519 "$DEPLOY_HOST" 2>/dev/null | ssh-keygen -lf - -E sha256 2>/dev/null | awk 'NR==1 {print $2}' || true)"
                                if [ -z "$SCANNED_FP" ]; then
                                  echo "ERROR: failed to read host fingerprint for $DEPLOY_HOST"
                                  exit 1
                                fi
                                if [ "$SCANNED_FP" != "$EFFECTIVE_DEPLOY_HOST_FINGERPRINT" ]; then
                                  echo "ERROR: host fingerprint mismatch for $DEPLOY_HOST"
                                  echo "Expected: $EFFECTIVE_DEPLOY_HOST_FINGERPRINT"
                                  echo "Actual:   $SCANNED_FP"
                                  exit 1
                                fi
                                echo "Host fingerprint verified for $DEPLOY_HOST"

                                ssh-keyscan -H "$DEPLOY_HOST" >> "$HOME/.ssh/known_hosts" 2>/dev/null || true
                                sort -u "$HOME/.ssh/known_hosts" -o "$HOME/.ssh/known_hosts"

                                SSH_OPTS="-i $SSH_KEY_FILE -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOME/.ssh/known_hosts"

                                # Keep deployment repo deterministic and recover from local drift.
                                # If deploy path exists but is not a git worktree, preserve it and bootstrap fresh clone.
                                # Reset first, then switch branch, so tracked local edits cannot block checkout.
                                ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "DEPLOY_PATH='$DEPLOY_PATH' REPO_URL='https://github.com/Ackrome/matplobbot' SOURCE_COMMIT='$SOURCE_COMMIT' bash -se" <<'REMOTE_EOF'
set -euo pipefail

DEPLOY_DIR="${DEPLOY_PATH/#~/$HOME}"
if [ -e "$DEPLOY_DIR" ] && [ ! -d "$DEPLOY_DIR" ]; then
  echo "ERROR: deploy path is not a directory: $DEPLOY_DIR"
  exit 1
fi

if ! git -C "$DEPLOY_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  mkdir -p "$DEPLOY_DIR"
  if [ -n "$(ls -A "$DEPLOY_DIR" 2>/dev/null)" ]; then
    BACKUP_DIR="${DEPLOY_DIR}.pre_git_$(date +%Y%m%d%H%M%S)"
    mv "$DEPLOY_DIR" "$BACKUP_DIR"
    mkdir -p "$DEPLOY_DIR"
    echo "Existing non-git deploy directory moved to $BACKUP_DIR"
  fi
  git clone --origin origin "$REPO_URL" "$DEPLOY_DIR"
fi

cd "$DEPLOY_DIR"
git remote set-url origin "$REPO_URL"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'
git fetch origin "$SOURCE_COMMIT"
mkdir -p .release-state
if [ ! -d ".release-state/candidates/$SOURCE_COMMIT" ]; then
  git worktree add --detach ".release-state/candidates/$SOURCE_COMMIT" "$SOURCE_COMMIT"
fi
REMOTE_EOF

                                # Verify the candidate away from live bind mounts. prepare saves
                                # the legacy/current runtime first and stops all bind-mounted
                                # services before switching source in a bounded maintenance window.
                                printf '%s' "$RELEASE_MANIFEST_B64" | ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "cd $DEPLOY_PATH && python3 .release-state/candidates/$SOURCE_COMMIT/scripts/release_manifest.py decode --stdin --commit $SOURCE_COMMIT --output .release-state/accepted.json"
                                ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "cd $DEPLOY_PATH && python3 .release-state/candidates/$SOURCE_COMMIT/scripts/release_deploy.py prepare .release-state/accepted.json --candidate .release-state/candidates/$SOURCE_COMMIT"

                                # Build the complete payload locally, then atomically replace the
                                # remote file. Optional values stay in the same SSH stream and no
                                # secret values are printed to the Jenkins log.
                                EXPECTED_ENV_KEYS="BOT_TOKEN ADMIN_USER_IDS GITHUB_TOKEN POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL STATS_USER STATS_PASS PUBLIC_API_URL PUBLIC_SITE_URL JWT_SECRET_KEY REDIS_URL PROXY_URL TELEGRAM_PROXY_URL TELEGRAM_PROXY_TRANSPORT SUB_URL MAIL_CREDENTIAL_KEY"
                                [ -z "${PROD_OUTLINE_ACCESS_KEY:-}" ] || EXPECTED_ENV_KEYS="$EXPECTED_ENV_KEYS OUTLINE_ACCESS_KEY"
                                [ -z "${PROD_TELEGRAM_REQUEST_RETRY_ATTEMPTS:-}" ] || EXPECTED_ENV_KEYS="$EXPECTED_ENV_KEYS TELEGRAM_REQUEST_RETRY_ATTEMPTS"
                                [ -z "${PROD_TELEGRAM_REQUEST_RETRY_DELAY_SECONDS:-}" ] || EXPECTED_ENV_KEYS="$EXPECTED_ENV_KEYS TELEGRAM_REQUEST_RETRY_DELAY_SECONDS"
                                {
                                    printf '%s\n' '# Generated by Jenkins'
                                    printf 'BOT_TOKEN=%s\n' "$PROD_BOT_TOKEN"
                                    printf 'ADMIN_USER_IDS=%s\n' "$PROD_ADMIN_USER_IDS"
                                    printf 'GITHUB_TOKEN=%s\n' "$PROD_GITHUB_TOKEN"
                                    printf 'POSTGRES_USER=%s\n' "$PROD_POSTGRES_USER"
                                    printf 'POSTGRES_PASSWORD=%s\n' "$PROD_POSTGRES_PASSWORD"
                                    printf 'POSTGRES_DB=%s\n' "$PROD_POSTGRES_DB"
                                    printf 'DATABASE_URL=postgresql://%s:%s@postgres:5432/%s\n' "$PROD_POSTGRES_USER" "$PROD_POSTGRES_PASSWORD" "$PROD_POSTGRES_DB"
                                    printf 'STATS_USER=%s\n' "${DEPLOY_ADMIN_USERNAME:-matplobbot-deploy}"
                                    printf 'STATS_PASS=%s\n' "$PROD_STATS_PASS"
                                    printf 'PUBLIC_API_URL=%s\n' "$PROD_PUBLIC_API_URL"
                                    printf 'PUBLIC_SITE_URL=%s\n' "$PROD_PUBLIC_SITE_URL"
                                    printf 'JWT_SECRET_KEY=%s\n' "$PROD_JWT_SECRET_KEY"
                                    printf '%s\n' 'REDIS_URL=redis://redis:6379/0'
                                    printf '%s\n' 'PROXY_URL=socks5://proxy:20170'
                                    printf '%s\n' 'TELEGRAM_PROXY_URL=socks5://proxy:20170'
                                    printf '%s\n' 'TELEGRAM_PROXY_TRANSPORT=tcp'
                                    printf 'SUB_URL=%s\n' "$PROD_SUB_URL"
                                    printf 'MAIL_CREDENTIAL_KEY=%s\n' "$PROD_MAIL_CREDENTIAL_KEY"

                                    if [ -n "${PROD_OUTLINE_ACCESS_KEY:-}" ]; then
                                        printf 'OUTLINE_ACCESS_KEY=%s\n' "$PROD_OUTLINE_ACCESS_KEY"
                                    fi

                                    if [ -n "${PROD_TELEGRAM_REQUEST_RETRY_ATTEMPTS:-}" ]; then
                                        printf 'TELEGRAM_REQUEST_RETRY_ATTEMPTS=%s\n' "$PROD_TELEGRAM_REQUEST_RETRY_ATTEMPTS"
                                    fi

                                    if [ -n "${PROD_TELEGRAM_REQUEST_RETRY_DELAY_SECONDS:-}" ]; then
                                        printf 'TELEGRAM_REQUEST_RETRY_DELAY_SECONDS=%s\n' "$PROD_TELEGRAM_REQUEST_RETRY_DELAY_SECONDS"
                                    fi
                                } | ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "cd $DEPLOY_PATH && bash ./deploy.sh --write-env .env $EXPECTED_ENV_KEYS"

                                ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "cd $DEPLOY_PATH && bash ./deploy.sh --manifest .release-state/accepted.json"
                                } 2>&1 | tee -a "$LOG_FILE"
BASH
                            '''
                        }
                    }
                }
            }
        }

        stage('Post-Deploy Smoke Checks') {
            steps {
                script {
                    env.FAIL_STAGE = 'Post-Deploy Smoke Checks'
                    withCredentials([sshUserPrivateKey(credentialsId: 'app-vm-ssh-key', keyFileVariable: 'SSH_KEY_FILE', usernameVariable: 'SSH_USER')]) {
                        sh '''
                            bash -euo pipefail <<'BASH'

                            LOG_FILE="$WORKSPACE/smoke_stage.log"
                            : > "$LOG_FILE"
                            {

                            chmod 600 "$SSH_KEY_FILE"
                            DEPLOY_HOST="$(bash "$WORKSPACE/scripts/resolve_private_ipv4.sh" "${DEPLOY_HOST:-192.168.1.40}")"
                            mkdir -p "$HOME/.ssh"
                            touch "$HOME/.ssh/known_hosts"

                            EFFECTIVE_DEPLOY_HOST_FINGERPRINT="${DEPLOY_HOST_FINGERPRINT:-${DEFAULT_DEPLOY_HOST_FINGERPRINT:-}}"
                            if [ -z "$EFFECTIVE_DEPLOY_HOST_FINGERPRINT" ]; then
                              echo "ERROR: no deploy host fingerprint configured. Set Jenkins credential APP_VM_SHA256 or provide DEPLOY_HOST_FINGERPRINT."
                              exit 1
                            fi

                            SCANNED_FP="$(ssh-keyscan -T 5 -t ed25519 "$DEPLOY_HOST" 2>/dev/null | ssh-keygen -lf - -E sha256 2>/dev/null | awk 'NR==1 {print $2}' || true)"
                            if [ -z "$SCANNED_FP" ]; then
                              echo "ERROR: failed to read host fingerprint for $DEPLOY_HOST"
                              exit 1
                            fi
                            if [ "$SCANNED_FP" != "$EFFECTIVE_DEPLOY_HOST_FINGERPRINT" ]; then
                              echo "ERROR: host fingerprint mismatch for $DEPLOY_HOST"
                              echo "Expected: $EFFECTIVE_DEPLOY_HOST_FINGERPRINT"
                              echo "Actual:   $SCANNED_FP"
                              exit 1
                            fi
                            echo "Host fingerprint verified for $DEPLOY_HOST"

                            ssh-keyscan -H "$DEPLOY_HOST" >> "$HOME/.ssh/known_hosts" 2>/dev/null || true
                            sort -u "$HOME/.ssh/known_hosts" -o "$HOME/.ssh/known_hosts"

                            SSH_OPTS="-i $SSH_KEY_FILE -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOME/.ssh/known_hosts"

                            SMOKE_RESULT_FILE="$(mktemp)"
                            trap 'rm -f "$SMOKE_RESULT_FILE"' EXIT
                            ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "cd $DEPLOY_PATH && bash scripts/release_smoke.sh $SOURCE_COMMIT" </dev/null | tee "$SMOKE_RESULT_FILE"
                            if ! grep -Fxq "Release smoke and finalization completed: $SOURCE_COMMIT" "$SMOKE_RESULT_FILE"; then
                              echo "ERROR: remote smoke exited without verified release completion."
                              exit 1
                            fi
                            } 2>&1 | tee -a "$LOG_FILE"
BASH
                        '''
                    }
                }
            }
        }
    }

    post {
        failure {
            script {
                def adminIds = (env.PROD_ADMIN_USER_IDS ?: '')
                    .split(',')
                    .collect { it.trim() }
                    .findAll { it }

                if (!env.PROD_BOT_TOKEN?.trim() || adminIds.isEmpty()) {
                    echo 'Skip Telegram failure notification: PROD_BOT_TOKEN or PROD_ADMIN_USER_IDS not configured.'
                    return
                }

                def failedStage = env.FAIL_STAGE ?: 'unknown'
                def stageLogFile = (failedStage == 'Post-Deploy Smoke Checks') ? 'smoke_stage.log' : ((failedStage == 'Pre-Deploy Quality Gate') ? 'quality_gate_stage.log' : 'deploy_stage.log')
                def stageLogContent = fileExists(stageLogFile) ? readFile(file: stageLogFile) : ''
                def stageLogLines = stageLogContent ? stageLogContent.readLines() : []
                def tailLines = stageLogLines.size() > 40 ? stageLogLines[-40..-1] : stageLogLines
                def logTail = tailLines.join('\n')
                def errorLine = tailLines.reverse().find {
                    def low = it.toLowerCase()
                    low.contains('error') || low.contains('failed') || low.contains('exit code')
                } ?: 'No explicit error line found'
                def clippedLogTail = logTail.length() > 2500 ? logTail[-2500..-1] : logTail

                def message = """matplobbot deployment FAILED
Job: ${env.JOB_NAME} #${env.BUILD_NUMBER}
Stage: ${failedStage}
Result: ${currentBuild.currentResult}
URL: ${env.BUILD_URL}
Error: ${errorLine}

Log tail:
${clippedLogTail}
"""

                writeFile file: 'deploy_failure_notify.txt', text: message
                withCredentials([sshUserPrivateKey(credentialsId: 'app-vm-ssh-key', keyFileVariable: 'SSH_KEY_FILE', usernameVariable: 'SSH_USER')]) {
                    sh '''
                            set +e
                            TG_CHAT_ID="$(printf '%s' "$PROD_ADMIN_USER_IDS" | awk -F, '{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $1); print $1; exit}')"
                            if [ -z "$TG_CHAT_ID" ]; then
                              echo "Skip Telegram failure notification: no usable admin chat ID."
                              exit 0
                            fi

                            # First try direct egress from Jenkins.
                            if curl -fsS --connect-timeout 20 --max-time 45 -X POST "https://api.telegram.org/bot$PROD_BOT_TOKEN/sendMessage" \
                              --data-urlencode "chat_id=$TG_CHAT_ID" \
                              --data-urlencode "text@deploy_failure_notify.txt" \
                              --data-urlencode "disable_web_page_preview=true" \
                              >/dev/null; then
                              exit 0
                            fi

                            echo "Direct Telegram notify failed; trying deploy-host SOCKS proxy..."

                            chmod 600 "$SSH_KEY_FILE"
                            DEPLOY_HOST="$(bash "$WORKSPACE/scripts/resolve_private_ipv4.sh" "${DEPLOY_HOST:-192.168.1.40}")"
                            mkdir -p "$HOME/.ssh"
                            touch "$HOME/.ssh/known_hosts"

                            EFFECTIVE_DEPLOY_HOST_FINGERPRINT="${DEPLOY_HOST_FINGERPRINT:-${DEFAULT_DEPLOY_HOST_FINGERPRINT:-}}"
                            if [ -z "$EFFECTIVE_DEPLOY_HOST_FINGERPRINT" ]; then
                              echo "ERROR: no deploy host fingerprint configured. Set Jenkins credential APP_VM_SHA256 or provide DEPLOY_HOST_FINGERPRINT."
                              exit 1
                            fi

                            SCANNED_FP="$(ssh-keyscan -T 5 -t ed25519 "$DEPLOY_HOST" 2>/dev/null | ssh-keygen -lf - -E sha256 2>/dev/null | awk 'NR==1 {print $2}' || true)"
                            if [ -z "$SCANNED_FP" ]; then
                              echo "ERROR: failed to read host fingerprint for $DEPLOY_HOST"
                              exit 1
                            fi
                            if [ "$SCANNED_FP" != "$EFFECTIVE_DEPLOY_HOST_FINGERPRINT" ]; then
                              echo "ERROR: host fingerprint mismatch for $DEPLOY_HOST"
                              echo "Expected: $EFFECTIVE_DEPLOY_HOST_FINGERPRINT"
                              echo "Actual:   $SCANNED_FP"
                              exit 1
                            fi
                            echo "Host fingerprint verified for $DEPLOY_HOST"

                            ssh-keyscan -H "$DEPLOY_HOST" >> "$HOME/.ssh/known_hosts" 2>/dev/null || true
                            sort -u "$HOME/.ssh/known_hosts" -o "$HOME/.ssh/known_hosts"
                            SSH_OPTS="-i $SSH_KEY_FILE -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOME/.ssh/known_hosts"

                            ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" \
                              "curl -fsS --connect-timeout 20 --max-time 60 --proxy socks5h://127.0.0.1:20170 -X POST \"https://api.telegram.org/bot$PROD_BOT_TOKEN/sendMessage\" --data-urlencode \"chat_id=$TG_CHAT_ID\" --data-urlencode \"text@-\" --data-urlencode \"disable_web_page_preview=true\" >/dev/null" \
                              < deploy_failure_notify.txt || true
                        '''
                }
            }
        }
        always {
            echo 'Deployment finished.'
        }
    }
}
