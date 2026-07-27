"""Tests for cc_monitor.auth — TokenManager, PairingManager, and auth middleware."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from cc_monitor.auth import TokenManager, TokenInfo, PairingManager, PairingRequest
from cc_monitor.auth_routes import create_auth_middleware, create_auth_router
from cc_monitor.tls import CertConfig


class TestTokenManagerCreate:
    def test_create_token_returns_token_info(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        info = tm.create_token("Pixel 8")

        assert isinstance(info.token, str)
        assert len(info.token) >= 32
        assert info.device_name == "Pixel 8"

    def test_create_token_with_ttl(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        info = tm.create_token("Pixel 8", ttl_seconds=3600)

        expected_latest = datetime.now(timezone.utc) + timedelta(seconds=3600)
        # Allow 5 seconds of clock skew
        assert abs((info.expires_at - expected_latest).total_seconds()) < 5

    def test_create_token_no_expiry(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        info = tm.create_token("Pixel 8", ttl_seconds=0)

        assert not info.expired
        # Far-future expiry
        assert info.expires_at > datetime.now(timezone.utc) + timedelta(days=365 * 100)


class TestTokenManagerValidate:
    def test_valid_token_returns_info(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        created = tm.create_token("Pixel 8")
        info = tm.validate_token(created.token)

        assert info is not None
        assert info.device_name == "Pixel 8"

    def test_invalid_token_returns_none(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        assert tm.validate_token("bogus-token") is None

    def test_expired_token_returns_none(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        created = tm.create_token("Pixel 8", ttl_seconds=-1)  # already expired

        info = tm.validate_token(created.token)
        assert info is None


class TestTokenManagerRotate:
    def test_rotate_produces_new_token(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        old = tm.create_token("Pixel 8")
        new = tm.rotate_token(old.token, "Pixel 8")

        assert new is not None
        assert new.token != old.token
        assert new.device_name == "Pixel 8"

    def test_rotate_invalidates_old_token(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        old = tm.create_token("Pixel 8")
        tm.rotate_token(old.token, "Pixel 8")

        assert tm.validate_token(old.token) is None

    def test_rotate_with_invalid_token_returns_none(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        assert tm.rotate_token("bogus", "Pixel 8") is None

    def test_rotate_with_no_expiry_preserves_no_expiry(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        old = tm.create_token("Pixel 8", ttl_seconds=0)
        new = tm.rotate_token(old.token, "Pixel 8")

        assert new is not None
        assert not new.expired

    def test_rotate_with_wrong_device_name_returns_none(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        old = tm.create_token("Pixel 8")
        new = tm.rotate_token(old.token, "Galaxy S25")

        assert new is None
        # Original token should still be valid
        assert tm.validate_token(old.token) is not None


class TestTokenManagerRevoke:
    def test_revoke_removes_token(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        created = tm.create_token("Pixel 8")
        assert tm.revoke_token(created.token)
        assert tm.validate_token(created.token) is None

    def test_revoke_unknown_token_returns_false(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        assert not tm.revoke_token("bogus")

    def test_revoke_all_clears_all(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        tm.create_token("Device A")
        tm.create_token("Device B")
        count = tm.revoke_all()
        assert count == 2


class TestTokenManagerPrune:
    def test_prune_removes_expired(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        expired = tm.create_token("Old Device", ttl_seconds=-1)
        valid = tm.create_token("New Device", ttl_seconds=3600)

        count = tm.prune_expired()
        assert count == 1
        assert tm._find_token(expired.token) is None


class TestTokenManagerPersistence:
    def test_tokens_survive_reload(self, tmp_path):
        tm1 = TokenManager(data_dir=tmp_path)
        created = tm1.create_token("Pixel 8")

        tm2 = TokenManager(data_dir=tmp_path)
        info = tm2.validate_token(created.token)
        assert info is not None
        assert info.device_name == "Pixel 8"


class TestPairingManagerQR:
    def test_create_qr_token_returns_token_and_expiry(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)
        token, expires_at = pm.create_qr_token()

        assert len(token) >= 32
        assert expires_at > datetime.now(timezone.utc)

    def test_qr_token_is_pending_until_confirmed(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        token, _ = pm.create_qr_token()
        # Token should NOT be valid yet -- it's pending
        assert tm.validate_token(token) is None

    def test_confirm_qr_token_activates_it(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        token, _ = pm.create_qr_token()
        info = pm.confirm_qr_token(token, "Pixel 8")

        assert info is not None
        assert info.device_name == "Pixel 8"
        assert tm.validate_token(token) is not None

    def test_confirm_with_wrong_token_returns_none(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        assert pm.confirm_qr_token("bogus-token", "Pixel 8") is None

    def test_confirm_twice_fails(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        token, _ = pm.create_qr_token()
        pm.confirm_qr_token(token, "Pixel 8")
        assert pm.confirm_qr_token(token, "Pixel 8") is None  # already used

    def test_expire_stale_qr_tokens(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        token, _ = pm.create_qr_token()
        # Force expiry by manipulating internal state
        pm._qr_tokens[token]["created_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=6)
        ).isoformat()

        count = pm.expire_stale_qr_tokens()
        assert count == 1
        assert pm.confirm_qr_token(token, "Pixel 8") is None


class TestPairingManagerApproval:
    def test_create_request_returns_request_id(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        req_id = pm.create_request("Pixel 8")
        req = pm.get_request(req_id)

        assert req is not None
        assert req.device_name == "Pixel 8"
        assert req.status == "pending"

    def test_approve_issues_token(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        req_id = pm.create_request("Pixel 8")
        info = pm.approve_request(req_id)

        assert info is not None
        assert info.device_name == "Pixel 8"
        assert tm.validate_token(info.token) is not None
        assert pm.get_request(req_id).status == "approved"

    def test_deny_sets_status(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        req_id = pm.create_request("Pixel 8")
        assert pm.deny_request(req_id)
        assert pm.get_request(req_id).status == "denied"

    def test_approve_nonexistent_returns_none(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        assert pm.approve_request("nonexistent") is None

    def test_get_pending_returns_only_pending(self, tmp_path):
        tm = TokenManager(data_dir=tmp_path)
        pm = PairingManager(data_dir=tmp_path, token_manager=tm)

        r1 = pm.create_request("Device A")
        r2 = pm.create_request("Device B")
        pm.approve_request(r1)

        pending = pm.get_pending()
        assert len(pending) == 1
        assert pending[0].id == r2


UNAUTHED_PATHS = {
    "/api/auth/pair/qr",
    "/api/auth/pair/request",
    "/api/auth/pair/request/",
    "/api/version",
}


def _build_test_app(tmp_path, token_manager=None, pairing_manager=None):
    """Build a minimal FastAPI app with auth middleware for testing."""
    from fastapi import FastAPI, Request

    app = FastAPI()

    if token_manager is None:
        token_manager = TokenManager(data_dir=tmp_path)
    if pairing_manager is None:
        pairing_manager = PairingManager(
            data_dir=tmp_path, token_manager=token_manager
        )

    cert_config = CertConfig(
        certfile=tmp_path / "cert.pem",
        keyfile=tmp_path / "key.pem",
        fingerprint="sha256:deadbeef",
    )

    router = create_auth_router(token_manager, pairing_manager, cert_config)
    app.include_router(router)
    app.middleware("http")(create_auth_middleware(token_manager))

    # Add a protected test endpoint
    @app.get("/api/test-protected")
    async def test_protected():
        return {"ok": True}

    return app, token_manager, pairing_manager


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_localhost_bypasses_auth(self, tmp_path):
        app, _, _ = _build_test_app(tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            resp = await client.get("/api/test-protected")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, tmp_path):
        app, _, _ = _build_test_app(tmp_path)
        transport = ASGITransport(app=app, client=("10.0.0.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://10.0.0.1") as client:
            resp = await client.get("/api/test-protected")
        assert resp.status_code == 401
        assert resp.json()["error"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, tmp_path):
        app, _, _ = _build_test_app(tmp_path)
        transport = ASGITransport(app=app, client=("10.0.0.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://10.0.0.1") as client:
            resp = await client.get(
                "/api/test-protected",
                headers={"Authorization": "Bearer invalid-token"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_passes(self, tmp_path):
        app, tm, _ = _build_test_app(tmp_path)
        info = tm.create_token("Test Device")
        transport = ASGITransport(app=app, client=("10.0.0.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://10.0.0.1") as client:
            resp = await client.get(
                "/api/test-protected",
                headers={"Authorization": f"Bearer {info.token}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauth_paths_skip_auth(self, tmp_path):
        app, _, _ = _build_test_app(tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://10.0.0.1") as client:
            resp = await client.get("/api/auth/pair/qr")
        assert resp.status_code == 200  # not 401
