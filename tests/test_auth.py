"""Tests for cc_monitor.auth — TokenManager and PairingManager."""

from datetime import datetime, timedelta, timezone

import pytest

from cc_monitor.auth import TokenManager, TokenInfo


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
