pipeline {
    agent any

    parameters {
        string(name: 'BOT_IMAGE_TAG', defaultValue: 'latest', description: 'Docker image tag for the bot')
        string(name: 'WORKER_IMAGE_TAG', defaultValue: 'latest', description: 'Docker image tag for the worker')
        string(name: 'API_IMAGE_TAG', defaultValue: 'latest', description: 'Docker image tag for the API')
        string(name: 'SCHEDULER_IMAGE_TAG', defaultValue: 'latest', description: 'Docker image tag for the scheduler')
        string(name: 'DEPLOY_HOST_FINGERPRINT', defaultValue: '', description: 'Optional override for pinned SHA256 host key fingerprint from APP_VM_SHA256')
    }


    environment {
        DEFAULT_DEPLOY_HOST_FINGERPRINT = credentials('APP_VM_SHA256')
        DEPLOY_HOST = 'app-vm.panthera-banjo.ts.net'
        DEPLOY_PATH = '~/matplobbot'

        PROD_BOT_TOKEN = credentials('PROD_BOT_TOKEN')
        PROD_ADMIN_USER_IDS = credentials('PROD_ADMIN_USER_IDS')
        PROD_GITHUB_TOKEN = credentials('PROD_GITHUB_TOKEN')
        PROD_POSTGRES_USER = credentials('PROD_POSTGRES_USER')
        PROD_POSTGRES_PASSWORD = credentials('PROD_POSTGRES_PASSWORD')
        PROD_POSTGRES_DB = credentials('PROD_POSTGRES_DB')
        PROD_STATS_PASS = credentials('PROD_STATS_PASS')
        PROD_STATS_USER = credentials('PROD_STATS_USER')
        PROD_PUBLIC_API_URL = credentials('PROD_PUBLIC_API_URL')
        PROD_JWT_SECRET_KEY = credentials('PROD_JWT_SECRET_KEY')
        PROD_SUB_URL = credentials('PROD_SUB_URL')
    }

    stages {
        stage('Deploy to Production') {
            steps {
                script {
                    env.FAIL_STAGE = 'Deploy to Production'
                    withCredentials([sshUserPrivateKey(credentialsId: 'app-vm-ssh-key', keyFileVariable: 'SSH_KEY_FILE', usernameVariable: 'SSH_USER')]) {
                        withEnv([
                            "BOT_TAG=${params.BOT_IMAGE_TAG}",
                            "API_TAG=${params.API_IMAGE_TAG}",
                            "SCHEDULER_TAG=${params.SCHEDULER_IMAGE_TAG}",
                            "WORKER_TAG=${params.WORKER_IMAGE_TAG}",
                        ]) {
                            sh '''
                                bash -euo pipefail <<'BASH'

                                LOG_FILE="$WORKSPACE/deploy_stage.log"
                                : > "$LOG_FILE"
                                {

                                chmod 600 "$SSH_KEY_FILE"

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

                                SCANNED_FP="$(ssh-keyscan -t ed25519 "$DEPLOY_HOST" 2>/dev/null | ssh-keygen -lf - -E sha256 | awk 'NR==1 {print $2}')"
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
                                ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "DEPLOY_PATH='$DEPLOY_PATH' REPO_URL='https://github.com/Ackrome/matplobbot' bash -se" <<'REMOTE_EOF'
set -euo pipefail

DEPLOY_DIR="${DEPLOY_PATH/#\~/$HOME}"
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
git fetch origin main
git reset --hard
git clean -fd
git checkout -B main origin/main
git reset --hard origin/main
git clean -fd
REMOTE_EOF

                                # Generate .env on remote host for production services.
                                ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "cat > $DEPLOY_PATH/.env" <<EOF
# Generated by Jenkins
BOT_TOKEN=$PROD_BOT_TOKEN
ADMIN_USER_IDS=$PROD_ADMIN_USER_IDS
GITHUB_TOKEN=$PROD_GITHUB_TOKEN
POSTGRES_USER=$PROD_POSTGRES_USER
POSTGRES_PASSWORD=$PROD_POSTGRES_PASSWORD
POSTGRES_DB=$PROD_POSTGRES_DB
DATABASE_URL=postgresql://$PROD_POSTGRES_USER:$PROD_POSTGRES_PASSWORD@postgres:5432/$PROD_POSTGRES_DB
STATS_USER=$PROD_STATS_USER
STATS_PASS=$PROD_STATS_PASS
PUBLIC_API_URL=$PROD_PUBLIC_API_URL
JWT_SECRET_KEY=$PROD_JWT_SECRET_KEY
REDIS_URL=redis://redis:6379/0
PROXY_URL=socks5://proxy:20170
SUB_URL=$PROD_SUB_URL
EOF

                                # Safer cleanup policy than full system prune.
                                ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "docker image prune -af --filter 'until=168h' && docker container prune -f --filter 'until=24h'"

                                ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "cd $DEPLOY_PATH && chmod +x deploy.sh || true && bash ./deploy.sh $BOT_TAG $API_TAG $SCHEDULER_TAG $WORKER_TAG"
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
                            mkdir -p "$HOME/.ssh"
                            touch "$HOME/.ssh/known_hosts"

                            EFFECTIVE_DEPLOY_HOST_FINGERPRINT="${DEPLOY_HOST_FINGERPRINT:-${DEFAULT_DEPLOY_HOST_FINGERPRINT:-}}"
                            if [ -z "$EFFECTIVE_DEPLOY_HOST_FINGERPRINT" ]; then
                              echo "ERROR: no deploy host fingerprint configured. Set Jenkins credential APP_VM_SHA256 or provide DEPLOY_HOST_FINGERPRINT."
                              exit 1
                            fi

                            SCANNED_FP="$(ssh-keyscan -t ed25519 "$DEPLOY_HOST" 2>/dev/null | ssh-keygen -lf - -E sha256 | awk 'NR==1 {print $2}')"
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

                            ssh $SSH_OPTS "$SSH_USER@$DEPLOY_HOST" "cd $DEPLOY_PATH && bash -s" <<'REMOTE_EOF'
set -eu

. ./.env

retry_http() {
  url="$1"
  attempts="${2:-30}"
  sleep_seconds="${3:-2}"
  i=1
  while [ "$i" -le "$attempts" ]; do
    if curl -fsS "$url" >/dev/null; then
      echo "Smoke check OK: $url"
      return 0
    fi
    echo "Waiting for $url ($i/$attempts)..."
    sleep "$sleep_seconds"
    i=$((i + 1))
  done
  echo "Smoke check FAILED: $url"
  return 1
}

# Service health endpoints
retry_http "http://127.0.0.1:9583/api/stats/health" 40 3
retry_http "http://127.0.0.1:9584/health" 40 3

# Leaderboard endpoint contract:
# 1) if STATS_USER/STATS_PASS are valid admin credentials, authenticated request must return 200
# 2) otherwise, endpoint must still be reachable and protected (401/403)
auth_checked=0
if [ -n "${STATS_USER:-}" ] && [ -n "${STATS_PASS:-}" ]; then
  LOGIN_RESP_FILE="$(mktemp)"
  LOGIN_STATUS="$(curl -sS -o "$LOGIN_RESP_FILE" -w '%{http_code}' -X POST "http://127.0.0.1:9583/api/auth/login" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode "username=${STATS_USER}" \
    --data-urlencode "password=${STATS_PASS}" || true)"

  if [ "$LOGIN_STATUS" = "200" ]; then
    TOKEN="$(sed -n 's/.*"access_token":"\\([^"]*\\)".*/\\1/p' "$LOGIN_RESP_FILE")"
    if [ -z "$TOKEN" ]; then
      echo "Smoke check FAILED: could not parse access_token from login response"
      rm -f "$LOGIN_RESP_FILE"
      exit 1
    fi

    LEADERBOARD_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' \
      -H "Authorization: Bearer ${TOKEN}" \
      "http://127.0.0.1:9583/api/stats/leaderboard" || true)"

    if [ "$LEADERBOARD_STATUS" = "200" ]; then
      echo "Smoke check OK: leaderboard endpoint (authenticated)"
      auth_checked=1
    else
      echo "Smoke check FAILED: authenticated leaderboard returned HTTP $LEADERBOARD_STATUS"
      rm -f "$LOGIN_RESP_FILE"
      exit 1
    fi
  else
    echo "Smoke check WARN: /api/auth/login returned HTTP $LOGIN_STATUS for STATS_USER; falling back to protected-endpoint contract"
  fi

  rm -f "$LOGIN_RESP_FILE"
else
  echo "Smoke check WARN: STATS_USER/STATS_PASS missing in .env; falling back to protected-endpoint contract"
fi

if [ "$auth_checked" -eq 0 ]; then
  PROTECTED_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:9583/api/stats/leaderboard" || true)"
  if [ "$PROTECTED_STATUS" = "401" ] || [ "$PROTECTED_STATUS" = "403" ]; then
    echo "Smoke check OK: leaderboard endpoint is protected (HTTP $PROTECTED_STATUS)"
  else
    echo "Smoke check FAILED: leaderboard endpoint returned unexpected HTTP $PROTECTED_STATUS without auth"
    exit 1
  fi
fi
REMOTE_EOF
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
                def stageLogFile = (failedStage == 'Post-Deploy Smoke Checks') ? 'smoke_stage.log' : 'deploy_stage.log'
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
                    withEnv(["TG_CHAT_ID=${adminIds[0]}"]) {
                        sh '''
                            set +e

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
                            mkdir -p "$HOME/.ssh"
                            touch "$HOME/.ssh/known_hosts"

                            EFFECTIVE_DEPLOY_HOST_FINGERPRINT="${DEPLOY_HOST_FINGERPRINT:-${DEFAULT_DEPLOY_HOST_FINGERPRINT:-}}"
                            if [ -z "$EFFECTIVE_DEPLOY_HOST_FINGERPRINT" ]; then
                              echo "ERROR: no deploy host fingerprint configured. Set Jenkins credential APP_VM_SHA256 or provide DEPLOY_HOST_FINGERPRINT."
                              exit 1
                            fi

                            SCANNED_FP="$(ssh-keyscan -t ed25519 "$DEPLOY_HOST" 2>/dev/null | ssh-keygen -lf - -E sha256 | awk 'NR==1 {print $2}')"
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
        }
        always {
            echo 'Deployment finished.'
        }
    }
}
