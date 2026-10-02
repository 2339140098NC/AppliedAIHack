"""Signed OAuth state that any Vercel instance can verify."""

import hashlib
import hmac
import secrets
import time

from caseboard.errors import CaseboardError

_MAX_AGE_SECONDS = 600


def issue_state(secret: str) -> str:
    """Return a state value that expires in ten minutes."""
    body = f"{int(time.time())}.{secrets.token_hex(8)}"
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def check_state(secret: str, state: str) -> None:
    """Reject a missing, forged, or expired state."""
    try:
        body, signature = state.rsplit(".", 1)
        issued = int(body.split(".", 1)[0])
    except (ValueError, IndexError) as exc:
        raise CaseboardError("Clio login state did not match") from exc
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    expired = time.time() - issued > _MAX_AGE_SECONDS
    if expired or not hmac.compare_digest(signature, expected):
        raise CaseboardError("Clio login state did not match")
