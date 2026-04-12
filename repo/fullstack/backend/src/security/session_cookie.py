"""Signed session cookie helpers.

The browser-facing `session_nonce` cookie is HMAC-signed so a tampered
or fabricated cookie is rejected at the request boundary, before the
auth service ever runs a database lookup. The signature is computed
over the raw nonce using a server-side secret loaded from disk
(`SESSION_KEY_PATH`, default `/run/secrets/reclaim_ops_session_key`).

Cookie wire format:    "<nonce>.<base64url(hmac(key, nonce))>"

This is the same shape Flask's itsdangerous `Signer` produces; we
implement it locally so the surrounding system has zero new
dependencies and the secret never enters Python's logging or pickle
paths.
"""
import base64
import hmac
import hashlib
import logging
import os
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

SESSION_KEY_PATH = os.environ.get(
    "SESSION_KEY_PATH", "/run/secrets/reclaim_ops_session_key"
)
SESSION_KEY_BYTES = 32  # 256-bit secret

# In-memory cache so each signing operation does not re-read the file.
_key_cache: Optional[bytes] = None


class SessionKeyError(RuntimeError):
    """Raised when the session signing key is missing or unreadable."""


def _load_or_generate_key() -> bytes:
    """Load (or first-time-generate) the session signing key.

    The key file is created with mode 0600 on first start. If the file
    already exists we read it verbatim — we never overwrite an existing
    key, because that would invalidate every active session.
    """
    global _key_cache
    if _key_cache is not None:
        return _key_cache

    if os.path.exists(SESSION_KEY_PATH):
        try:
            with open(SESSION_KEY_PATH, "rb") as f:
                key = f.read()
        except OSError as e:
            raise SessionKeyError(
                f"Could not read session signing key {SESSION_KEY_PATH}: {e}"
            ) from e
        if len(key) < 16:
            raise SessionKeyError(
                f"Session signing key at {SESSION_KEY_PATH} is too short "
                f"({len(key)} bytes). Refusing to use a weak key."
            )
        _key_cache = key
        return key

    # First-time generation.
    logger.warning(
        "No session signing key at %s — generating one (first init)",
        SESSION_KEY_PATH,
    )
    key = secrets.token_bytes(SESSION_KEY_BYTES)
    try:
        key_dir = os.path.dirname(SESSION_KEY_PATH)
        if key_dir:
            os.makedirs(key_dir, exist_ok=True)
        with open(SESSION_KEY_PATH, "wb") as f:
            f.write(key)
        os.chmod(SESSION_KEY_PATH, 0o600)
    except OSError as e:
        raise SessionKeyError(
            f"Could not persist session signing key to {SESSION_KEY_PATH}: {e}"
        ) from e
    _key_cache = key
    return key


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def sign_session_nonce(nonce: str) -> str:
    """Return the wire-format signed cookie value for `nonce`."""
    if nonce is None:
        raise ValueError("nonce is required")
    key = _load_or_generate_key()
    sig = hmac.new(key, nonce.encode("utf-8"), hashlib.sha256).digest()
    return f"{nonce}.{_b64u(sig)}"


def verify_session_cookie(cookie_value: Optional[str]) -> Optional[str]:
    """Verify a signed session cookie and return the inner nonce.

    Returns None for any of:
      - missing cookie
      - malformed cookie (no signature segment)
      - signature mismatch (tampered or forged)

    Constant-time comparison via `hmac.compare_digest` to avoid timing
    leaks against the secret.
    """
    if not cookie_value:
        return None
    if "." not in cookie_value:
        return None
    nonce, _, sig_b64 = cookie_value.rpartition(".")
    if not nonce or not sig_b64:
        return None
    try:
        key = _load_or_generate_key()
    except SessionKeyError as e:
        logger.error("Session key load failed during verification: %s", e)
        return None
    expected = hmac.new(key, nonce.encode("utf-8"), hashlib.sha256).digest()
    expected_b64 = _b64u(expected)
    if not hmac.compare_digest(sig_b64, expected_b64):
        return None
    return nonce


def reset_key_cache() -> None:
    """Test helper — clears the in-memory key cache."""
    global _key_cache
    _key_cache = None
