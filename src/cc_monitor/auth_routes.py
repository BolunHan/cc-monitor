"""Auth middleware and API routes for cc-monitor."""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from cc_monitor.auth import PairingManager, TokenManager
from cc_monitor.tls import CertConfig

logger = logging.getLogger(__name__)

# Paths that skip auth even from non-localhost clients
_UNAUTHED_PATHS = {
    "/api/auth/pair/qr",
    "/api/auth/pair/request",
    "/api/auth/pair/qr/confirm",
    "/api/version",
}
# Paths that are always unauthed when they start with these prefixes
_UNAUTHED_PREFIXES = ("/api/auth/pair/request/",)


def create_auth_middleware(token_manager: TokenManager):
    """Create an ASGI middleware that enforces Bearer token auth.

    Localhost (127.0.0.1, ::1) bypasses auth entirely.
    Certain paths (/api/auth/pair/*, /api/version) are unauthenticated.
    All other /api/* paths require a valid Bearer token.
    """

    async def middleware(request: Request, call_next):
        # Static files, root, non-API paths — always allowed
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Localhost always authorized
        client_ip = request.client.host if request.client else None
        if client_ip in ("127.0.0.1", "::1"):
            return await call_next(request)

        # Unauthenticated paths
        if request.url.path in _UNAUTHED_PATHS:
            return await call_next(request)
        if request.url.path.startswith(_UNAUTHED_PREFIXES):
            return await call_next(request)

        # Check Bearer token (header or query param for EventSource)
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        if not token:
            token = request.query_params.get("token", "").strip()
        if not token:
            return JSONResponse(
                {"detail": "unauthorized"},
                status_code=401,
                headers={"X-Token-Expired": "false"},
            )

        info = token_manager.validate_token(token)
        if info is None:
            # Check if it's an expired token vs. invalid
            is_expired = token_manager.is_token_expired(token)
            return JSONResponse(
                {"detail": "unauthorized"},
                status_code=401,
                headers={"X-Token-Expired": str(is_expired).lower()},
            )

        response = await call_next(request)
        response.headers["X-Token-Expires"] = info.expires_at.isoformat()
        return response

    return middleware


def _get_lan_ip() -> str:
    """Auto-detect the LAN IP by connecting a UDP socket to known gateways."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        for gw in ("192.168.1.1", "192.168.0.1", "192.168.3.1", "10.0.0.1"):
            try:
                s.connect((gw, 1))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except OSError:
                continue
        s.close()
    except Exception:
        pass
    return "127.0.0.1"


def create_auth_router(
    token_manager: TokenManager,
    pairing_manager: PairingManager,
    cert_config: CertConfig,
    ttl_seconds: int = 604800,
    lan_host: str = "",
    broadcast_callback=None,
) -> APIRouter:
    """Create a FastAPI router with all /api/auth/* endpoints.

    Args:
        token_manager: Token lifecycle manager.
        pairing_manager: Pairing request manager.
        cert_config: TLS certificate configuration.
        ttl_seconds: Default token TTL for info responses.
        broadcast_callback: Optional async callable(event_type, data)
            called after state-changing operations to push SSE updates
            to connected clients.
        lan_host: LAN IP for QR pairing payload.

    Returns:
        A FastAPI APIRouter with auth endpoints.
    """
    router = APIRouter()

    async def _broadcast(event_type: str, **data):
        """Push a pairing/device event to all SSE subscribers."""
        if broadcast_callback:
            try:
                await broadcast_callback(event_type, data)
            except Exception:
                pass

    @router.get("/api/auth/pair/qr")
    async def get_qr_pairing_payload(request: Request):
        """Return the QR code pairing payload.

        The returned token is PENDING — it must be confirmed via
        POST /api/auth/pair/qr/confirm within 5 minutes.
        """
        token, expires_at = pairing_manager.create_qr_token()
        port = request.url.port or 9876

        # Use the LAN IP passed from main(), or auto-detect
        host = lan_host if lan_host else _get_lan_ip()

        return JSONResponse({
            "host": host,
            "port": port,
            "cert_sha256": cert_config.fingerprint,
            "token": token,
            "expires_at": expires_at.isoformat(),
        })

    @router.post("/api/auth/pair/qr/confirm")
    async def confirm_qr_pairing(request: Request):
        """Confirm a QR-scanned token and activate it.

        The token must have been generated via GET /api/auth/pair/qr
        within the last 5 minutes.
        """
        body = await request.json()
        token = body.get("token", "")
        device_name = body.get("device_name", "Unknown Device")
        client_id = body.get("client_id", "")

        info = pairing_manager.confirm_qr_token(token, device_name, client_id)
        if info is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired QR token. Re-scan the QR code.",
            )

        await _broadcast("device_update")
        return JSONResponse({
            "status": "paired",
            "token": info.token,
            "expires_at": info.expires_at.isoformat(),
        })

    @router.post("/api/auth/pair/request")
    async def submit_pairing_request(request: Request):
        """Submit a pairing request for manual approval.

        If a request with the same pairing_code was already approved,
        returns the token directly (claim flow after CLI approval).
        """
        body = await request.json()
        device_name = body.get("device_name", "Unknown Device")
        pairing_code = body.get("pairing_code", "")
        client_id = body.get("client_id", "")
        device_meta = body.get("device_meta", None)

        # Check if a request with this code was already approved
        pairing_manager._requests = pairing_manager._load_requests()
        pending = pairing_manager.get_pending()
        for req in pending:
            if req.pairing_code == pairing_code:
                # Still pending — duplicate submit, return existing request_id
                return JSONResponse({
                    "request_id": req.id,
                    "status": "pending",
                    "pairing_code": pairing_code,
                })

        # Check if any resolved request with this code was approved
        for entry in pairing_manager._requests.values():
            if entry.get("pairing_code") == pairing_code and entry["status"] == "approved":
                # Re-claim: create a new token for this client
                token_info = token_manager.create_token(
                    device_name, ttl_seconds=ttl_seconds, client_id=client_id,
                    meta=device_meta,
                )
                return JSONResponse({
                    "status": "approved",
                    "token": token_info.token,
                    "expires_at": token_info.expires_at.isoformat(),
                })

        # New request
        request_id = pairing_manager.create_request(device_name, pairing_code, client_id)

        await _broadcast("pairing_request", request_id=request_id,
                         device_name=device_name, pairing_code=pairing_code,
                         status="pending")

        return JSONResponse({
            "request_id": request_id,
            "status": "pending",
            "pairing_code": pairing_code,
        })

    @router.get("/api/auth/pair/request/{request_id}/status")
    async def get_pairing_request_status(request_id: str):
        """Poll the status of a pairing request."""
        # Reload from disk to pick up CLI approvals
        pairing_manager._requests = pairing_manager._load_requests()
        req = pairing_manager.get_request(request_id)
        if req is None:
            raise HTTPException(status_code=404, detail="Request not found")

        response = {
            "request_id": req.id,
            "status": req.status,
        }
        if req.status == "approved":
            response["approved"] = True

        return JSONResponse(response)

    @router.get("/api/auth/pair/requests")
    async def list_pending_requests():
        """List all pending pairing requests."""
        pending = pairing_manager.get_pending()
        return JSONResponse({
            "requests": [
                {
                    "id": r.id,
                    "device_name": r.device_name,
                    "pairing_code": r.pairing_code,
                    "requested_at": r.requested_at.isoformat(),
                    "status": r.status,
                }
                for r in pending
            ]
        })

    @router.post("/api/auth/pair/request/{request_id}/approve")
    async def approve_pairing_request(request_id: str):
        """Approve a pending pairing request and return the token."""
        info = pairing_manager.approve_request(request_id)
        if info is None:
            raise HTTPException(
                status_code=404,
                detail="Request not found or already resolved",
            )

        await _broadcast("pairing_resolved", request_id=request_id, status="approved")
        await _broadcast("device_update")

        return JSONResponse({
            "status": "approved",
            "token": info.token,
            "expires_at": info.expires_at.isoformat(),
        })

    @router.post("/api/auth/pair/request/{request_id}/deny")
    async def deny_pairing_request(request_id: str):
        """Deny a pending pairing request."""
        if not pairing_manager.deny_request(request_id):
            raise HTTPException(
                status_code=404,
                detail="Request not found or already resolved",
            )
        await _broadcast("pairing_resolved", request_id=request_id, status="denied")
        return JSONResponse({"status": "denied"})

    @router.post("/api/auth/token/rotate")
    async def rotate_token(request: Request):
        """Rotate the current token — returns a new token, revokes old."""
        auth_header = request.headers.get("Authorization", "")
        old_token = auth_header.removeprefix("Bearer ").strip()

        body = await request.json()
        device_name = body.get("device_name", "Unknown Device")

        info = token_manager.rotate_token(old_token, device_name)
        if info is None:
            raise HTTPException(
                status_code=401,
                detail="Token invalid or expired — re-pair required",
            )

        return JSONResponse({
            "token": info.token,
            "expires_at": info.expires_at.isoformat(),
        })

    @router.delete("/api/auth/token")
    async def revoke_own_token(request: Request):
        """Revoke the current token."""
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()

        if token_manager.revoke_token(token):
            await _broadcast("device_update")
            return JSONResponse({"status": "revoked"})
        raise HTTPException(status_code=404, detail="Token not found")

    @router.get("/api/auth/token/info")
    async def token_info(request: Request):
        """Return info about the current token."""
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()

        info = token_manager.validate_token(token)
        if info is None:
            raise HTTPException(status_code=401, detail="Token invalid or expired")

        return JSONResponse({
            "device_name": info.device_name,
            "created_at": info.created_at.isoformat(),
            "expires_at": info.expires_at.isoformat(),
            "ttl_seconds": ttl_seconds,
        })

    @router.get("/api/auth/devices")
    async def list_devices():
        """List all paired devices (reloads tokens from disk)."""
        # Reload to pick up CLI changes
        token_manager._tokens = token_manager._load()
        devices = pairing_manager.get_device_list()
        return JSONResponse({"devices": devices})

    @router.delete("/api/auth/devices/{client_id}")
    async def revoke_device(client_id: str):
        """Revoke all tokens for a device by client_id."""
        count = pairing_manager.revoke_device(client_id)
        if count > 0:
            await _broadcast("device_update")
            return JSONResponse({"status": "revoked", "count": count})
        raise HTTPException(status_code=404, detail="Device not found")

    return router
