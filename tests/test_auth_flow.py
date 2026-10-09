import hashlib
import hmac
import io
import json
import os
import time
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlencode

FASTAPI_AVAILABLE = True
try:
    from fastapi import Depends, FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests-at-least-32-bytes")
    os.environ.setdefault("BOT_TOKEN", "123456:test-token")

    from fastapi_stats_app import auth as fastapi_auth
    from fastapi_stats_app import bootstrap_admin
    from fastapi_stats_app.routers import auth_router
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class TestAuthFlow(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        token_patch = patch.object(fastapi_auth, "BOT_TOKEN", "123456:test-token")
        token_patch.start()
        self.addCleanup(token_patch.stop)
        self.app = FastAPI()
        self.app.include_router(auth_router.router, prefix="/api")
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _mock_db(self, *, account=None):
        db = Mock()
        execute_result = Mock()
        execute_result.scalar_one_or_none.return_value = account
        db.execute = AsyncMock(return_value=execute_result)
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = Mock()
        return db

    def _build_webapp_init_data(self, user_data, *, auth_date=None):
        params = {
            "auth_date": str(auth_date if auth_date is not None else int(time.time())),
            "query_id": "test-query",
            "user": json.dumps(user_data, separators=(",", ":")),
        }
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
        secret_key = hmac.new(
            b"WebAppData",
            fastapi_auth.BOT_TOKEN.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        params["hash"] = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return urlencode(params)

    def test_register_is_disabled_by_default(self):
        db = self._mock_db(account=None)
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db

        response = self.client.post(
            "/api/auth/register",
            json={"username": "newuser", "password": "StrongPass123"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Password registration is disabled.")
        self.assertFalse(db.add.called)

    def test_register_creates_non_admin_user_when_enabled(self):
        db = self._mock_db(account=None)
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db

        with patch.object(auth_router, "AUTH_PASSWORD_REGISTRATION_ENABLED", True):
            response = self.client.post(
                "/api/auth/register",
                json={"username": "newuser", "password": "StrongPass123"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"status": "success"})
        self.assertTrue(db.add.called)
        created_account = db.add.call_args.args[0]
        self.assertEqual(created_account.role, "user")

    def test_login_returns_bearer_token(self):
        account = SimpleNamespace(
            id=7,
            role="user",
            password_hash=fastapi_auth.get_password_hash("s3cret-pass"),
        )
        db = self._mock_db(account=account)
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db

        response = self.client.post(
            "/api/auth/login",
            data={"username": "john", "password": "s3cret-pass"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "bearer")
        decoded = fastapi_auth.decode_access_token(body["access_token"])
        self.assertEqual(decoded["sub"], "7")
        self.assertEqual(decoded["role"], "user")
        self.assertEqual(decoded["iss"], fastapi_auth.JWT_ISSUER)
        self.assertEqual(decoded["aud"], fastapi_auth.JWT_AUDIENCE)
        self.assertIn("iat", decoded)
        self.assertIn("nbf", decoded)
        self.assertIn("exp", decoded)

    async def test_deployment_admin_can_log_in_and_provisioning_is_idempotent(self):
        # Exercise real persistence and the login query without a live PostgreSQL service.
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        bootstrap_admin.WebAccount.__table__.create(engine)
        session = Session(engine, expire_on_commit=False)
        self.addCleanup(engine.dispose)
        self.addCleanup(session.close)
        db = self._mock_db()
        db.execute = AsyncMock(side_effect=session.execute)
        db.add = Mock(side_effect=session.add)
        db.flush = AsyncMock(side_effect=session.flush)
        password = "a deployment secret with $pecial ' characters"
        result = await bootstrap_admin.provision_admin(db, "deployment-admin", password)
        session.commit()
        self.assertEqual(result, "created")
        session.expire_all()
        account = session.scalar(
            select(bootstrap_admin.WebAccount).where(
                bootstrap_admin.WebAccount.username == "deployment-admin"
            )
        )
        self.assertEqual(account.role, "admin")
        self.assertIsNone(account.telegram_id)
        self.assertNotEqual(account.password_hash, password)
        original_hash = account.password_hash
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db

        response = self.client.post(
            "/api/auth/login", data={"username": "deployment-admin", "password": password}
        )
        self.assertEqual(response.status_code, 200)
        claims = fastapi_auth.decode_access_token(response.json()["access_token"])
        self.assertEqual((claims["sub"], claims["role"]), (str(account.id), "admin"))
        for username, supplied_password in (
            ("absent-account", password),
            ("deployment-admin", "wrong"),
        ):
            response = self.client.post(
                "/api/auth/login", data={"username": username, "password": supplied_password}
            )
            self.assertEqual(response.status_code, 401)
        result = await bootstrap_admin.provision_admin(db, "deployment-admin", password)
        self.assertEqual(result, "unchanged")
        self.assertEqual(account.password_hash, original_hash)
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    async def test_deployment_admin_password_rotation_preserves_identity_and_preferences(self):
        account = SimpleNamespace(
            id=70,
            role="admin",
            telegram_id=None,
            password_hash=fastapi_auth.get_password_hash("previous-secret"),
            preferences={"language": "ru"},
        )
        db = self._mock_db(account=account)
        self.assertEqual(
            await bootstrap_admin.provision_admin(db, "deployment-admin", "rotated-secret"),
            "password synchronized",
        )
        self.assertTrue(fastapi_auth.verify_password("rotated-secret", account.password_hash))
        self.assertFalse(fastapi_auth.verify_password("previous-secret", account.password_hash))
        self.assertEqual(account.id, 70)
        self.assertEqual(account.preferences, {"language": "ru"})
        db.add.assert_not_called()

    async def test_deployment_admin_rejects_account_collisions_without_mutation(self):
        for role, telegram_id in (("user", None), ("admin", 123), ("user", 123)):
            with self.subTest(role=role, telegram_id=telegram_id):
                account = SimpleNamespace(
                    role=role, telegram_id=telegram_id, password_hash="original-hash"
                )
                db = self._mock_db(account=account)
                with self.assertRaisesRegex(
                    bootstrap_admin.AdminProvisioningError, "dedicated deployment admin"
                ):
                    await bootstrap_admin.provision_admin(db, "taken-name", "secret-value")
                self.assertEqual(account.password_hash, "original-hash")
                self.assertEqual((account.role, account.telegram_id), (role, telegram_id))
                db.add.assert_not_called()
                db.flush.assert_not_awaited()

    async def test_deployment_admin_rejects_empty_and_default_credentials(self):
        for username, password in (
            ("", "secret"),
            (" ", "secret"),
            ("admin", ""),
            ("admin", " "),
            ("admin", "admin"),
            ("admin", "PASSWORD"),
            ("admin", "123456"),
        ):
            with self.subTest(username=username, password=password):
                db = self._mock_db()
                with self.assertRaises(bootstrap_admin.AdminProvisioningError):
                    await bootstrap_admin.provision_admin(db, username, password)
                db.execute.assert_not_awaited()
                db.add.assert_not_called()

    async def test_deployment_admin_invalid_stored_hash_fails_closed(self):
        account = SimpleNamespace(role="admin", telegram_id=None, password_hash="invalid")
        db = self._mock_db(account=account)
        with self.assertRaisesRegex(bootstrap_admin.AdminProvisioningError, "hash is invalid"):
            await bootstrap_admin.provision_admin(db, "admin", "secret-value")
        self.assertEqual(account.password_hash, "invalid")
        db.flush.assert_not_awaited()

    async def test_deployment_admin_transaction_rolls_back_on_failure_and_closes_pool(self):
        db_context = AsyncMock()
        db = self._mock_db()
        transaction = AsyncMock()
        db.begin = Mock(return_value=transaction)
        db_context.__aenter__.return_value = db
        with (
            patch.object(bootstrap_admin, "init_db_pool", new_callable=AsyncMock),
            patch.object(bootstrap_admin, "close_db_pool", new_callable=AsyncMock) as close,
            patch.object(bootstrap_admin, "get_session", return_value=db_context),
            patch.object(bootstrap_admin, "provision_admin", new_callable=AsyncMock) as provision,
            patch.dict(os.environ, {"STATS_USER": "configured", "STATS_PASS": "secret"}),
        ):
            provision.side_effect = RuntimeError("database unavailable")
            with self.assertRaises(RuntimeError):
                await bootstrap_admin.bootstrap_admin()
            provision.assert_awaited_once_with(db, "configured", "secret")
            self.assertIs(transaction.__aexit__.call_args.args[0], RuntimeError)
            close.assert_awaited_once()

    def test_deployment_admin_cli_suppresses_secret_bearing_database_errors(self):
        with (
            patch.object(bootstrap_admin, "bootstrap_admin", new_callable=AsyncMock) as provision,
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            provision.side_effect = RuntimeError("SQL parameters contain a secret password hash")
            self.assertEqual(bootstrap_admin.main(), 1)
            self.assertEqual(stderr.getvalue(), "Admin provisioning FAILED (RuntimeError).\n")

    def test_jwt_decoder_rejects_tampered_signature(self):
        token = fastapi_auth.create_access_token({"sub": "7", "role": "user"})
        replacement = "A" if token[-1] != "A" else "B"

        with self.assertRaises(fastapi_auth.JWTError):
            fastapi_auth.decode_access_token(f"{token[:-1]}{replacement}")

    def test_jwt_decoder_requires_standard_claims(self):
        now = int(time.time())
        token = fastapi_auth.jwt.encode(
            {
                "sub": "7",
                "iat": now,
                "nbf": now,
                "exp": now + 60,
                "iss": fastapi_auth.JWT_ISSUER,
            },
            fastapi_auth.SECRET_KEY,
            algorithm=fastapi_auth.ALGORITHM,
        )

        with self.assertRaises(fastapi_auth.JWTError):
            fastapi_auth.decode_access_token(token)

    def test_jwt_decoder_rejects_wrong_audience(self):
        now = int(time.time())
        token = fastapi_auth.jwt.encode(
            {
                "sub": "7",
                "iat": now,
                "nbf": now,
                "exp": now + 60,
                "iss": fastapi_auth.JWT_ISSUER,
                "aud": "another-service",
            },
            fastapi_auth.SECRET_KEY,
            algorithm=fastapi_auth.ALGORITHM,
        )

        with self.assertRaises(fastapi_auth.JWTError):
            fastapi_auth.decode_access_token(token)

    def test_jwt_encoder_rejects_non_numeric_subject(self):
        with self.assertRaises(ValueError):
            fastapi_auth.create_access_token({"sub": "not-an-account", "role": "user"})

    def test_login_rejects_invalid_password(self):
        account = SimpleNamespace(
            id=8,
            role="user",
            password_hash=fastapi_auth.get_password_hash("correct-pass"),
        )
        db = self._mock_db(account=account)
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db

        response = self.client.post(
            "/api/auth/login",
            data={"username": "john", "password": "wrong-pass"},
        )

        self.assertEqual(response.status_code, 401)

    def test_telegram_webapp_init_data_verifier_accepts_valid_payload(self):
        init_data = self._build_webapp_init_data(
            {
                "id": 12345,
                "first_name": "Ivan",
                "last_name": "Petrov",
                "username": "ivan",
            }
        )

        parsed = fastapi_auth.parse_verified_telegram_webapp_init_data(init_data)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["id"], 12345)
        self.assertEqual(parsed["first_name"], "Ivan")

    def _build_widget_payload(self, auth_date):
        payload = {"id": 12345, "first_name": "Ivan", "auth_date": auth_date}
        text = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
        payload["hash"] = hmac.new(
            hashlib.sha256(fastapi_auth.BOT_TOKEN.encode()).digest(), text.encode(), hashlib.sha256
        ).hexdigest()
        return payload

    def test_widget_accepts_only_fresh_signed_payloads(self):
        now = 2_000_000_000
        with patch.object(fastapi_auth.time, "time", return_value=now):
            self.assertTrue(
                fastapi_auth.verify_telegram_authorization(self._build_widget_payload(now))
            )
            for timestamp in (now - 86401, now + 61, "bad", None, True):
                with self.subTest(timestamp=timestamp):
                    self.assertFalse(
                        fastapi_auth.verify_telegram_authorization(
                            self._build_widget_payload(timestamp)
                        )
                    )
            payload = self._build_widget_payload(now)
            payload["first_name"] = "Tampered"
            self.assertFalse(fastapi_auth.verify_telegram_authorization(payload))

    def test_widget_endpoint_rejects_stale_signature_before_database_write(self):
        db = self._mock_db()
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db
        response = self.client.post(
            "/api/auth/telegram", json=self._build_widget_payload(int(time.time()) - 365 * 86400)
        )
        self.assertEqual(response.status_code, 403)
        db.execute.assert_not_awaited()

    def test_export_receipt_is_owner_bound_and_cannot_authenticate(self):
        receipt = fastapi_auth.create_account_export_token(7)
        self.assertTrue(fastapi_auth.verify_account_export_token(receipt, 7))
        self.assertFalse(fastapi_auth.verify_account_export_token(receipt, 8))
        with self.assertRaises(fastapi_auth.JWTError):
            fastapi_auth.decode_access_token(receipt)
        login_token = fastapi_auth.create_access_token({"sub": "7"})
        self.assertFalse(fastapi_auth.verify_account_export_token(login_token, 7))

    def test_account_delete_requires_explicit_confirmation_and_recent_export(self):
        self.app.dependency_overrides[auth_router.get_current_user] = lambda: {"id": 7}
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: (
            self._mock_db()
        )
        with patch.object(auth_router, "delete_account_data", AsyncMock()) as erase:
            missing = self.client.request("DELETE", "/api/auth/account", json={})
            bad = self.client.request(
                "DELETE",
                "/api/auth/account",
                json={
                    "confirmation": "DELETE",
                    "export_token": "not-a-receipt",
                },
            )
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(bad.status_code, 409)
        erase.assert_not_awaited()

    def test_account_export_then_delete_scopes_to_current_owner(self):
        db = self._mock_db()
        self.app.dependency_overrides[auth_router.get_current_user] = lambda: {"id": 7}
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db
        with (
            patch.object(
                auth_router,
                "export_account_data",
                AsyncMock(
                    return_value={
                        "account": {"id": 7},
                        "projects": [],
                    }
                ),
            ) as export,
            patch.object(auth_router, "delete_account_data", AsyncMock(return_value=True)) as erase,
        ):
            downloaded = self.client.get("/api/auth/account/export")
            response = self.client.request(
                "DELETE",
                "/api/auth/account",
                json={
                    "confirmation": "DELETE",
                    "export_token": downloaded.json()["deletion_token"],
                    "account_id": 999,
                },
            )
        self.assertEqual(downloaded.headers["cache-control"], "no-store")
        self.assertEqual(response.status_code, 200)
        export.assert_awaited_once_with(db, account_id=7)
        erase.assert_awaited_once_with(db, 7)

    def test_telegram_webapp_init_data_verifier_rejects_tampering(self):
        init_data = self._build_webapp_init_data({"id": 12345, "first_name": "Ivan"})
        tampered = init_data.replace("Ivan", "Eve")

        parsed = fastapi_auth.parse_verified_telegram_webapp_init_data(tampered)

        self.assertIsNone(parsed)

    def test_telegram_webapp_init_data_verifier_rejects_stale_payload(self):
        init_data = self._build_webapp_init_data(
            {"id": 12345, "first_name": "Ivan"},
            auth_date=int((datetime.now(UTC) - timedelta(days=2)).timestamp()),
        )

        parsed = fastapi_auth.parse_verified_telegram_webapp_init_data(init_data)

        self.assertIsNone(parsed)

    def test_logout_returns_success_for_authenticated_user(self):
        self.app.dependency_overrides[auth_router.get_current_user] = lambda: {
            "id": 1,
            "role": "user",
        }

        response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success"})

    def test_update_preferences_merges_existing_namespaces(self):
        account = SimpleNamespace(
            preferences={
                "calendar_sync": {
                    "enabled": True,
                    "custom_profiles": [{"id": "custom-1", "name": "Group 1"}],
                },
                "useShortNames": False,
            }
        )
        db = self._mock_db(account=account)
        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db
        self.app.dependency_overrides[auth_router.get_current_user] = lambda: {
            "id": 1,
            "username": "Test User",
            "role": "user",
            "preferences": account.preferences,
            "db_obj": account,
        }

        response = self.client.put(
            "/api/auth/preferences",
            json={
                "preferences": {
                    "entity": {"type": "group", "id": "group-1", "name": "Group 1"},
                    "modules": ["Core"],
                    "useShortNames": True,
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            account.preferences["calendar_sync"]["custom_profiles"][0]["id"],
            "custom-1",
        )
        self.assertEqual(account.preferences["entity"]["id"], "group-1")
        self.assertEqual(account.preferences["modules"], ["Core"])
        self.assertTrue(account.preferences["useShortNames"])
        self.assertEqual(response.json()["preferences"], account.preferences)

    def test_update_preferences_locks_latest_account_before_merging(self):
        stale_account = auth_router.WebAccount(
            id=1,
            username="Test User",
            role="user",
            preferences={"useShortNames": False},
        )
        locked_account = auth_router.WebAccount(
            id=1,
            username="Test User",
            role="user",
            preferences={
                "calendar_sync": {
                    "enabled": True,
                    "custom_profiles": [{"id": "custom-2", "name": "Group 2"}],
                },
                "useShortNames": False,
            },
        )
        db = self._mock_db(account=locked_account)

        self.app.dependency_overrides[auth_router.get_db_session_dependency] = lambda: db
        self.app.dependency_overrides[auth_router.get_current_user] = lambda: {
            "id": 1,
            "username": "Test User",
            "role": "user",
            "preferences": {"useShortNames": False},
            "db_obj": stale_account,
        }

        response = self.client.put(
            "/api/auth/preferences",
            json={
                "preferences": {
                    "entity": {"type": "group", "id": "group-2", "name": "Group 2"},
                    "modules": ["Core"],
                    "useShortNames": True,
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        db.execute.assert_awaited()
        self.assertEqual(
            locked_account.preferences["calendar_sync"]["custom_profiles"][0]["id"],
            "custom-2",
        )
        self.assertEqual(locked_account.preferences["entity"]["id"], "group-2")
        self.assertTrue(locked_account.preferences["useShortNames"])
        self.assertEqual(response.json()["preferences"], locked_account.preferences)

    async def test_expired_jwt_is_rejected_by_get_current_user(self):
        expired_token = fastapi_auth.create_access_token(
            {
                "sub": "1",
                "role": "user",
            },
            expires_delta=timedelta(seconds=-5),
        )
        account = SimpleNamespace(
            id=1,
            role="user",
            telegram_id=None,
            username="u1",
            preferences={},
        )
        db = self._mock_db(account=account)

        with self.assertRaises(HTTPException) as ctx:
            await fastapi_auth.get_current_user(token=expired_token, db=db)

        self.assertEqual(getattr(ctx.exception, "status_code", None), 401)

    def test_admin_non_admin_access_matrix(self):
        app = FastAPI()

        @app.get("/admin-only")
        def admin_only(_user: dict = Depends(fastapi_auth.require_admin)):
            return {"status": "ok"}

        app.dependency_overrides[fastapi_auth.get_current_user] = lambda: {
            "id": 2,
            "role": "user",
        }
        client = TestClient(app)
        user_response = client.get("/admin-only")
        self.assertEqual(user_response.status_code, 403)

        app.dependency_overrides[fastapi_auth.get_current_user] = lambda: {
            "id": 1,
            "role": "admin",
        }
        admin_response = client.get("/admin-only")
        self.assertEqual(admin_response.status_code, 200)
