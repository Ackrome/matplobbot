Based on `repomix-output.xml`, these are the highest-impact improvements I’d prioritize:

1. Fix broken access control in Studio APIs (serious data leak risk). Many project endpoints don’t enforce `owner_id`, so authenticated users can read/modify other users’ projects.
   [studio_router.py#L134](/c:/Projects/matplobbot/fastapi_stats_app/routers/studio_router.py#L134), [studio_router.py#L148](/c:/Projects/matplobbot/fastapi_stats_app/routers/studio_router.py#L148), [studio_router.py#L154](/c:/Projects/matplobbot/fastapi_stats_app/routers/studio_router.py#L154), [studio_router.py#L173](/c:/Projects/matplobbot/fastapi_stats_app/routers/studio_router.py#L173), [studio_router.py#L255](/c:/Projects/matplobbot/fastapi_stats_app/routers/studio_router.py#L255), [studio_router.py#L283](/c:/Projects/matplobbot/fastapi_stats_app/routers/studio_router.py#L283)

2. Remove privilege escalation in auth registration. New password-based users are created as `admin`.
   [auth_router.py#L26](/c:/Projects/matplobbot/fastapi_stats_app/routers/auth_router.py#L26)

3. Enforce secure auth defaults. JWT has a hardcoded fallback secret.
   [auth.py#L17](/c:/Projects/matplobbot/fastapi_stats_app/auth.py#L17)

4. Add role checks for admin-only stats actions (especially sending Telegram messages).
   [stats_router.py#L188](/c:/Projects/matplobbot/fastapi_stats_app/routers/stats_router.py#L188)

5. Lock down WebSocket user streams. Any valid token can subscribe to `/ws/users/{user_id}` for arbitrary users.
   [ws_router.py#L223](/c:/Projects/matplobbot/fastapi_stats_app/routers/ws_router.py#L223)

6. Fix scheduler runtime bugs.
   [scheduler_app/config.py#L15](/c:/Projects/matplobbot/scheduler_app/config.py#L15) uses `logging` without import, and [scheduler_app/main.py#L137](/c:/Projects/matplobbot/scheduler_app/main.py#L137) references `scheduler` out of scope on shutdown.

7. Clean dependency management. `requirements.txt` has duplicates/unpinned libs and inconsistent shared-lib versioning with `version_bumper.py`.
   [requirements.txt#L4](/c:/Projects/matplobbot/requirements.txt#L4), [requirements.txt#L9](/c:/Projects/matplobbot/requirements.txt#L9), [requirements.txt#L26](/c:/Projects/matplobbot/requirements.txt#L26), [version_bumper.py#L88](/c:/Projects/matplobbot/version_bumper.py#L88)

8. Add quality gates in CI (tests/lint/type checks) before publish/deploy. Current pipeline auto-bumps/releases but has no validation stage.
   [ci-cd.yml#L35](/c:/Projects/matplobbot/.github/workflows/ci-cd.yml#L35)

9. Improve production isolation. Prod compose mounts source code into API container.
   [docker-compose.prod.yml#L110](/c:/Projects/matplobbot/docker-compose.prod.yml#L110)

10. Reduce avoidable load. Bot middleware fetches Telegram avatars on every update; stats WS polls DB every 2s; schedule router creates new HTTP sessions per request.
   [bot/logger.py#L47](/c:/Projects/matplobbot/bot/logger.py#L47), [ws_router.py#L100](/c:/Projects/matplobbot/fastapi_stats_app/routers/ws_router.py#L100), [schedule_router.py#L16](/c:/Projects/matplobbot/fastapi_stats_app/routers/schedule_router.py#L16)

11. Harden LaTeX project compile path handling. `extractall()` on cache zip and path filtering are too permissive.
   [tasks.py#L394](/c:/Projects/matplobbot/shared_lib/tasks.py#L394), [tasks.py#L401](/c:/Projects/matplobbot/shared_lib/tasks.py#L401)

12. Strengthen deployment security posture. Jenkins deploy uses root SSH with host key checks disabled and aggressive system prune.
   [Jenkinsfile.groovy#L38](/c:/Projects/matplobbot/Jenkinsfile.groovy#L38), [Jenkinsfile.groovy#L63](/c:/Projects/matplobbot/Jenkinsfile.groovy#L63)