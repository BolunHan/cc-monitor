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
    client_id: str
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

    def create_token(
        self, device_name: str, ttl_seconds: int = 0, client_id: str = "",
    ) -> TokenInfo:
        """Generate a new token for a device.

        Args:
            device_name: Human-readable device identifier.
            ttl_seconds: Token lifetime in seconds. 0 means never expires.
            client_id: Unique client UUID for identifying this device.

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
            "client_id": client_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        self._tokens[token] = entry
        self._save()
        logger.info("Created token for '%s' (client: %s)", device_name, client_id[:8] if client_id else "-")
        return self._to_info(entry)

    def register_token(
        self, token: str, device_name: str, ttl_seconds: int = 0,
        client_id: str = "",
    ) -> TokenInfo:
        """Register a pre-existing token string with TokenManager.

        Unlike create_token, this does not generate a new token -- it
        registers the given token value directly. Used by PairingManager
        for QR tokens where the token is pre-generated.

        Args:
            token: The pre-existing token string to register.
            device_name: Human-readable device identifier.
            ttl_seconds: Token lifetime in seconds. 0 means never expires.
            client_id: Unique client UUID for identifying this device.

        Returns:
            TokenInfo for the registered token.

        Raises:
            ValueError: If the token is already registered.
        """
        if token in self._tokens:
            raise ValueError(f"Token already registered")
        now = datetime.now(timezone.utc)
        expires_at = (
            _NO_EXPIRY_SENTINEL
            if ttl_seconds == 0
            else now + timedelta(seconds=ttl_seconds)
        )
        entry = {
            "token": token,
            "device_name": device_name,
            "client_id": client_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        self._tokens[token] = entry
        self._save()
        logger.info("Registered token for '%s'", device_name)
        return self._to_info(entry)

    def is_token_expired(self, token: str) -> bool:
        """Check if a token is known and expired.

        Returns False if the token is valid or unknown (never existed).
        Returns True only if the token exists but has passed its expiry.
        """
        entry = self._tokens.get(token)
        if entry is None:
            return False
        return self._to_info(entry).expired

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
            client_id=entry.get("client_id", ""),
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


_QR_TOKEN_TIMEOUT = timedelta(minutes=5)
_PAIRING_REQUESTS_FILE = "pairing_requests.json"


@dataclass
class PairingRequest:
    """A pending device pairing request."""
    id: str
    device_name: str
    requested_at: datetime
    status: str  # "pending", "approved", "denied"
    pairing_code: str = ""


class PairingManager:
    """Manages device pairing via QR tokens and approval requests.

    QR tokens are short-lived (5 min confirmation window) and stored in memory
    only. Approval requests are persisted to disk.
    """

    def __init__(
        self,
        data_dir: Path,
        token_manager: TokenManager,
        ttl_seconds: int = 604800,
    ):
        self._data_dir = data_dir
        self._token_manager = token_manager
        self._ttl_seconds = ttl_seconds
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # In-memory: QR token -> {token, created_at}
        self._qr_tokens: dict[str, dict] = {}
        # Disk-backed: request_id -> PairingRequest dict
        self._requests: dict[str, dict] = self._load_requests()

    # ------------------------------------------------------------------
    # QR Token pairing
    # ------------------------------------------------------------------

    def create_qr_token(self) -> tuple[str, datetime]:
        """Generate a pending QR pairing token.

        The token is NOT yet active -- it must be confirmed via
        confirm_qr_token() within 5 minutes.

        Returns:
            Tuple of (token, expires_at).
        """
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = (
            _NO_EXPIRY_SENTINEL
            if self._ttl_seconds == 0
            else now + timedelta(seconds=self._ttl_seconds)
        )

        self._qr_tokens[token] = {
            "created_at": now.isoformat(),
            "ttl_seconds": self._ttl_seconds,
        }
        return token, expires_at

    def confirm_qr_token(
        self, token: str, device_name: str, client_id: str = "",
    ) -> TokenInfo | None:
        """Confirm a pending QR token and activate it.

        The QR token itself becomes the active auth token.

        Args:
            token: The pending QR token.
            device_name: Human-readable device name.
            client_id: Unique client UUID.

        Returns:
            TokenInfo if confirmed, None if token unknown or expired.
        """
        pending = self._qr_tokens.pop(token, None)
        if pending is None:
            return None

        created_at = datetime.fromisoformat(pending["created_at"])
        if datetime.now(timezone.utc) - created_at > _QR_TOKEN_TIMEOUT:
            return None

        # Register the QR token itself as a valid auth token
        return self._token_manager.register_token(
            token, device_name, ttl_seconds=pending["ttl_seconds"],
            client_id=client_id,
        )

    def expire_stale_qr_tokens(self) -> int:
        """Remove QR tokens that were never confirmed within the 5-min window."""
        now = datetime.now(timezone.utc)
        expired = []
        for token, entry in self._qr_tokens.items():
            created_at = datetime.fromisoformat(entry["created_at"])
            if now - created_at > _QR_TOKEN_TIMEOUT:
                expired.append(token)
        for token in expired:
            del self._qr_tokens[token]
        if expired:
            logger.info("Expired %d stale QR tokens", len(expired))
        return len(expired)

    # ------------------------------------------------------------------
    # Approval-based pairing
    # ------------------------------------------------------------------

    def create_request(
        self, device_name: str, pairing_code: str = "",
        client_id: str = "",
    ) -> str:
        """Submit a pairing request for manual approval.

        Args:
            device_name: Human-readable device identifier.
            pairing_code: Optional 6-digit code for identification.
            client_id: Unique client UUID.

        Returns:
            The request ID for polling.
        """
        request_id = secrets.token_urlsafe(16)
        now = datetime.now(timezone.utc)
        self._requests[request_id] = {
            "id": request_id,
            "device_name": device_name,
            "pairing_code": pairing_code,
            "client_id": client_id,
            "requested_at": now.isoformat(),
            "status": "pending",
        }
        self._save_requests()
        logger.info(
            "Pairing request '%s' from '%s' (client: %s, code: %s)",
            request_id, device_name, client_id[:8] if client_id else "-", pairing_code,
        )
        return request_id

    def get_request(self, request_id: str) -> PairingRequest | None:
        """Get a pairing request by ID."""
        entry = self._requests.get(request_id)
        if entry is None:
            return None
        return self._to_request(entry)

    def get_pending(self) -> list[PairingRequest]:
        """List all pending pairing requests (not yet approved or denied)."""
        return [
            self._to_request(e)
            for e in self._requests.values()
            if e["status"] == "pending"
        ]

    def approve_request(self, request_id: str) -> TokenInfo | None:
        """Approve a pending pairing request and issue a token.

        Args:
            request_id: The request to approve.

        Returns:
            TokenInfo with the new token, or None if not found/already resolved.
        """
        entry = self._requests.get(request_id)
        if entry is None or entry["status"] != "pending":
            return None

        entry["status"] = "approved"
        self._save_requests()
        return self._token_manager.create_token(
            entry["device_name"],
            ttl_seconds=self._ttl_seconds,
            client_id=entry.get("client_id", ""),
        )

    def deny_request(self, request_id: str) -> bool:
        """Deny a pending pairing request.

        Args:
            request_id: The request to deny.

        Returns:
            True if denied, False if not found/already resolved.
        """
        entry = self._requests.get(request_id)
        if entry is None or entry["status"] != "pending":
            return False

        entry["status"] = "denied"
        self._save_requests()
        logger.info("Denied pairing request '%s'", request_id)
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _to_request(self, entry: dict) -> PairingRequest:
        return PairingRequest(
            id=entry["id"],
            device_name=entry["device_name"],
            pairing_code=entry.get("pairing_code", ""),
            requested_at=datetime.fromisoformat(entry["requested_at"]),
            status=entry["status"],
        )

    def get_device_list(self) -> list[dict]:
        """Return all paired (active) devices with their token info."""
        devices = []
        for token, entry in self._token_manager._tokens.items():
            info = self._token_manager._to_info(entry)
            devices.append({
                "device_name": info.device_name,
                "client_id": info.client_id,
                "created_at": info.created_at.isoformat(),
                "expires_at": info.expires_at.isoformat(),
                "expired": info.expired,
                "token_prefix": token[:12] + "...",
            })
        return devices

    def revoke_device(self, token_prefix: str) -> bool:
        """Revoke a device by token prefix match."""
        for token in list(self._token_manager._tokens.keys()):
            if token.startswith(token_prefix.rstrip(".")):
                return self._token_manager.revoke_token(token)
        return False

    def _load_requests(self) -> dict:
        path = self._data_dir / _PAIRING_REQUESTS_FILE
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load pairing requests: %s", exc)
            return {}

    def _save_requests(self) -> None:
        path = self._data_dir / _PAIRING_REQUESTS_FILE
        path.write_text(json.dumps(self._requests, indent=2))
