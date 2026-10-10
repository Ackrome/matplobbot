"""Real persistence and HTTP/WS contracts for revocation and login throttling."""

import ipaddress
import os
import shutil
import subprocess
import unittest
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-unit-tests-at-least-32-bytes")

from fastapi import FastAPI, HTTPException, WebSocketException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from fastapi_stats_app import auth, bootstrap_admin, login_limits
from fastapi_stats_app.routers import auth_router, ws_router
from shared_lib.models import WebAccount, WebTokenRevocation


class AuthSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        WebAccount.__table__.create(self.engine)
        WebTokenRevocation.__table__.create(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.account = WebAccount(
            id=1,
            username="owner",
            role="admin",
            preferences={},
            password_hash=auth.get_password_hash("previous-secret"),
        )
        self.session.add(self.account)
        self.session.commit()
        self.db = SimpleNamespace(
            execute=AsyncMock(side_effect=self.session.execute),
            commit=AsyncMock(side_effect=self.session.commit),
            flush=AsyncMock(side_effect=self.session.flush),
            add=self.session.add,
        )
        self.app = FastAPI()
        self.app.include_router(auth_router.router, prefix="/api")
        self.app.dependency_overrides[auth.get_db_session_dependency] = lambda: self.db
        self.client = TestClient(self.app)

    def token(self):
        self.session.refresh(self.account)
        return auth.create_access_token({"sub": "1", "auth_version": self.account.auth_version})

    def headers(self, token):
        return {"Authorization": "Bearer " + token}

    async def test_logout_revokes_only_current_token_and_survives_new_db_session(self):
        first, second = self.token(), self.token()
        self.assertEqual(
            self.client.get("/api/auth/me", headers=self.headers(first)).status_code, 200
        )
        self.assertEqual(
            self.client.post("/api/auth/logout", headers=self.headers(first)).status_code, 200
        )
        self.session.close()
        # A new connection/session still reads the persisted revocation.
        self.assertEqual(
            self.client.get("/api/auth/me", headers=self.headers(first)).status_code, 401
        )
        self.assertEqual(
            self.client.get("/api/auth/me", headers=self.headers(second)).status_code, 200
        )
        await self.assert_ws_rejected(first)
        self.assertTrue(await self.stream_active(second))
        self.assertFalse(await self.stream_active(first))

    async def test_logout_all_revokes_old_tokens_but_allows_fresh_login(self):
        first, second = self.token(), self.token()
        self.assertEqual(
            self.client.post("/api/auth/logout-all", headers=self.headers(first)).status_code, 200
        )
        for token in (first, second):
            self.assertEqual(
                self.client.get("/api/auth/me", headers=self.headers(token)).status_code, 401
            )
            await self.assert_ws_rejected(token)
            self.assertFalse(await self.stream_active(token))
        with patch.object(auth_router, "enforce_login_limits", AsyncMock()):
            response = self.client.post(
                "/api/auth/login", data={"username": "owner", "password": "previous-secret"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/auth/me", headers=self.headers(response.json()["access_token"])
            ).status_code,
            200,
        )

    async def test_password_rotation_invalidates_existing_sessions(self):
        token = self.token()
        await bootstrap_admin.provision_admin(self.db, "owner", "rotated-secret")
        self.session.commit()
        with self.assertRaises(HTTPException):
            await auth.get_current_user(token, self.db)

    async def test_expired_revocations_are_pruned_and_legacy_claims_fail_closed(self):
        expired = auth.create_access_token({"sub": "1"}, timedelta(seconds=-120))
        import jwt

        claims = jwt.decode(expired, options={"verify_signature": False})
        await auth.revoke_session(self.db, 1, claims)
        token = self.token()
        current = auth.decode_access_token(token)
        await auth.revoke_session(self.db, 1, current)
        self.assertIsNone(self.session.get(WebTokenRevocation, claims["jti"]))
        claims = dict(current)
        claims.pop("jti")
        legacy = jwt.encode(claims, auth.SECRET_KEY, algorithm=auth.ALGORITHM)
        with self.assertRaises(HTTPException):
            await auth.get_current_user(legacy, self.db)

    @asynccontextmanager
    async def db_context(self):
        yield self.db

    async def assert_ws_rejected(self, token):
        with patch.object(auth, "get_session", self.db_context):
            with self.assertRaises(WebSocketException):
                await auth.get_ws_user(SimpleNamespace(query_params={"token": token}))

    async def stream_active(self, token):
        with patch.object(ws_router, "get_session", self.db_context):
            return await ws_router.websocket_account_is_active(
                {"id": 1, "token_claims": auth.decode_access_token(token)}
            )


class LoginLimitTests(unittest.IsolatedAsyncioTestCase):
    def request(self, peer="203.0.113.10", forwarded=""):
        return Request(
            {
                "type": "http",
                "client": (peer, 1234),
                "headers": [(b"x-forwarded-for", forwarded.encode())],
            }
        )

    def test_only_trusted_proxy_chain_can_supply_client_identity(self):
        trusted = (ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"))
        with patch.object(login_limits, "TRUSTED_PROXIES", trusted):
            self.assertEqual(
                login_limits.client_identity(self.request(forwarded="attacker-choice")),
                "203.0.113.10",
            )
            self.assertEqual(
                login_limits.client_identity(
                    self.request("172.18.0.4", "spoofed, 203.0.113.10, 127.0.0.1")
                ),
                "203.0.113.10",
            )

    async def test_shared_limiter_failure_and_limit_reject_before_password_lookup(self):
        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api")
        db = SimpleNamespace(execute=AsyncMock())
        app.dependency_overrides[auth.get_db_session_dependency] = lambda: db
        for result, error, status in ((17, None, 429), (None, ConnectionError("unavailable"), 503)):
            redis = SimpleNamespace(
                client=SimpleNamespace(eval=AsyncMock(return_value=result, side_effect=error))
            )
            with patch.object(login_limits, "redis_client", redis):
                response = TestClient(app).post(
                    "/api/auth/login", data={"username": "owner", "password": "bad"}
                )
            self.assertEqual(response.status_code, status)
            self.assertIn("Retry-After", response.headers)
            db.execute.assert_not_awaited()

    async def test_same_identity_uses_same_keys_and_no_password_is_transmitted(self):
        redis = SimpleNamespace(client=SimpleNamespace(eval=AsyncMock(return_value=0)))
        with patch.object(login_limits, "redis_client", redis):
            await login_limits.enforce_login_limits(self.request(), "Owner")
            await login_limits.enforce_login_limits(self.request(), "owner")
        calls = redis.client.eval.call_args_list
        self.assertEqual(calls[0], calls[1])
        self.assertNotIn("owner", str(calls[0]))


@unittest.skipUnless(shutil.which("node"), "Node is required for logout frontend tests")
class LogoutFrontendTests(unittest.TestCase):
    def test_confirmed_failed_and_cross_account_logout(self):
        source = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const all=fs.readFileSync('main_site_frontend/js/navbar.js','utf8');
const source=all.slice(all.indexOf('let logoutPending = false;'),all.indexOf('async function checkAuthAndRenderNavbar'));
let token='first', response={status:500,ok:false}, calls=[],alerts=[],buttons=[{disabled:false}];
const ctx={AbortController,setTimeout,clearTimeout,NAV_API_BASE:'/api',translate:key=>key,
document:{querySelectorAll:()=>buttons},
localStorage:{getItem:()=>token,removeItem:()=>{token=null;}},
window:{location:{href:'/account'},alert:text=>alerts.push(text)},
fetch:async(url,opts)=>{calls.push({url,opts});return response;}};
vm.createContext(ctx);vm.runInContext(source,ctx);
(async()=>{
assert.equal(await ctx.window.performLogout(),false);assert.equal(token,'first');
assert.equal(ctx.window.location.href,'/account');assert.equal(alerts.length,1);assert.equal(buttons[0].disabled,false);
response={status:200,ok:true};assert.equal(await ctx.window.performLogout(true),true);
assert.equal(calls.at(-1).url,'/api/auth/logout-all');assert.equal(calls.at(-1).opts.method,'POST');
assert.equal(calls.at(-1).opts.headers.Authorization,'Bearer first');assert.equal(token,null);
token='first';ctx.window.location.href='/account';let resolve;
ctx.fetch=()=>new Promise(done=>{resolve=done;});
const pending=ctx.window.performLogout();assert.equal(await ctx.window.performLogout(),false);
token='second';resolve({status:200,ok:true});await pending;
assert.equal(token,'second');assert.equal(ctx.window.location.href,'/account');
ctx.fetch=async()=>({status:401,ok:false});await ctx.window.performLogout();assert.equal(token,null);
})().catch(err=>{console.error(err);process.exitCode=1;});
"""
        result = subprocess.run(
            ["node", "-e", source], capture_output=True, text=True, encoding="utf-8", timeout=20
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
