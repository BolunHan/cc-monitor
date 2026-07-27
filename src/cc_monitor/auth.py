"""Authentication — token lifecycle and pairing request management."""

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_NO_EXPIRY_SENTINEL = datetime(9999, 12, 31, tzinfo=timezone.utc)
_TOKENS_FILE = "tokens.json"


@dataclass
class TokenInfo:
    """Information about an authentication token."""

    token: str
    device_name: str
    created_at: datetime
    expires_at: datetime

    @property
    def expired(self) -> bool:
        """Whether the token has passed its expiration time."""
        return datetime.now(timezone.utc) >= self.expires_at


class TokenManager:
    """Manages authentication token lifecycle and persistence.

    Tokens are stored in <data_dir>/tokens.json as a JSON dict keyed by token.
    """

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._tokens: dict[str, dict] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_token(self, device_name: str, ttl_seconds: int = 0) -> TokenInfo:
        """Generate a new token for a device.

        Args:
            device_name: Human-readable device identifier.
            ttl_seconds: Token lifetime in seconds. 0 means never expires.

        Returns:
            TokenInfo for the newly created token.
        """
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = (
            _NO_EXPIRY_SENTINEL
            if ttl_seconds == 0
            else now + timedelta(seconds=ttl_seconds)
        )

        entry = {
            "token": token,
            "device_name": device_name,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        self._tokens[token] = entry
        self._save()
        logger.info("Created token for '%s' (expires: %s)", device_name, expires_at)
        return self._to_info(entry)

    def validate_token(self, token: str) -> TokenInfo | None:
        """Check if a token is valid.

        Args:
            token: The bearer token to validate.

        Returns:
            TokenInfo if valid, None if invalid or expired.
        """
        entry = self._tokens.get(token)
        if entry is None:
            return None
        info = self._to_info(entry)
        if info.expired:
            return None
        return info

    def rotate_token(self, old_token: str, device_name: str) -> TokenInfo | None:
        """Create a new token and revoke the old one.

        Args:
            old_token: The current valid token.
            device_name: Device name (must match the old token's device).

        Returns:
            TokenInfo for the new token, or None if old_token is invalid.
        """
        old_entry = self._tokens.get(old_token)
        if old_entry is None:
            return None

        old_info = self._to_info(old_entry)
        if old_info.expired:
            return None

        if old_info.device_name != device_name:
            return None

        # Preserve the original TTL by computing remaining time,
        # or use the old entry's expiry to compute TTL
        old_expires = datetime.fromisoformat(old_entry["expires_at"])
        if old_expires == _NO_EXPIRY_SENTINEL:
            ttl = 0
        else:
            ttl = max(
                0, int((old_expires - datetime.now(timezone.utc)).total_seconds())
            )

        # Revoke old token
        del self._tokens[old_token]

        # Create new token with same remaining TTL
        new_info = self.create_token(device_name, ttl_seconds=ttl)
        logger.info("Rotated token for '%s'", device_name)
        return new_info

    def revoke_token(self, token: str) -> bool:
        """Revoke a specific token.

        Args:
            token: The token to revoke.

        Returns:
            True if the token existed and was revoked.
        """
        if token in self._tokens:
            del self._tokens[token]
            self._save()
            logger.info("Revoked token")
            return True
        return False

    def revoke_all(self) -> int:
        """Revoke all tokens.

        Returns:
            Number of tokens revoked.
        """
        count = len(self._tokens)
        self._tokens.clear()
        self._save()
        logger.info("Revoked all %d tokens", count)
        return count

    def prune_expired(self) -> int:
        """Remove all expired tokens.

        Returns:
            Number of tokens pruned.
        """
        expired = [t for t, e in self._tokens.items() if self._to_info(e).expired]
        for t in expired:
            del self._tokens[t]
        if expired:
            self._save()
            logger.info("Pruned %d expired tokens", len(expired))
        return len(expired)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _to_info(self, entry: dict) -> TokenInfo:
        return TokenInfo(
            token=entry["token"],
            device_name=entry["device_name"],
            created_at=datetime.fromisoformat(entry["created_at"]),
            expires_at=datetime.fromisoformat(entry["expires_at"]),
        )

    def _find_token(self, token: str) -> dict | None:
        """Exposed for test assertions — not part of public API."""
        return self._tokens.get(token)

    def _load(self) -> dict:
        path = self._data_dir / _TOKENS_FILE
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load tokens file: %s", exc)
            return {}

    def _save(self) -> None:
        path = self._data_dir / _TOKENS_FILE
        path.write_text(json.dumps(self._tokens, indent=2))
