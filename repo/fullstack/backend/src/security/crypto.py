"""Field-level encryption at rest — AES-256-GCM.

The encryption key is loaded from an external file
(default: /run/secrets/reclaim_ops_key).

Key lifecycle rules:
- On the very first initialization (no key file AND no marker file),
  a new 256-bit key is generated, persisted, and a marker file is
  created alongside it to record that initialization has occurred.
- On every subsequent startup, the key MUST be present. If the key
  file is missing but the marker exists, the system REFUSES to
  regenerate and raises KeyFileMissingError — silent key rotation
  would permanently destroy access to all previously-encrypted data.
- If the key file is present but corrupted (wrong length), the system
  raises CorruptKeyError rather than overwriting it.

The key is NEVER stored in the database and NEVER returned in API responses.
"""
import logging
import os
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

KEY_PATH = os.environ.get("RECLAIM_OPS_KEY_PATH", "/run/secrets/reclaim_ops_key")
MARKER_SUFFIX = ".initialized"
IV_LENGTH = 12  # 96 bits, recommended for AES-GCM
KEY_LENGTH = 32  # 256 bits

_key_cache: Optional[bytes] = None


class KeyFileMissingError(RuntimeError):
    """Raised when the key file is missing after initial setup (post-init loss)."""


class CorruptKeyError(RuntimeError):
    """Raised when the key file exists but is unreadable or wrong length."""


def _marker_path() -> str:
    return KEY_PATH + MARKER_SUFFIX


def _write_marker() -> None:
    marker = _marker_path()
    with open(marker, "w") as f:
        f.write("initialized")
    try:
        os.chmod(marker, 0o600)
    except OSError:
        pass


def load_or_generate_key() -> bytes:
    """Load the encryption key, generating it ONLY on first initialization.

    Raises KeyFileMissingError if the key was previously initialized but is
    now missing — this prevents silent key rotation that would permanently
    destroy access to all existing encrypted fields.

    Raises CorruptKeyError if the key file is present but unreadable or has
    an invalid length.
    """
    global _key_cache
    if _key_cache is not None:
        return _key_cache

    marker = _marker_path()
    key_exists = os.path.exists(KEY_PATH)
    marker_exists = os.path.exists(marker)

    # ── Normal path: key file present — load it ──
    if key_exists:
        try:
            with open(KEY_PATH, "rb") as f:
                key = f.read()
        except OSError as e:
            raise CorruptKeyError(
                f"Could not read encryption key file {KEY_PATH}: {e}"
            ) from e

        if len(key) != KEY_LENGTH:
            raise CorruptKeyError(
                f"Encryption key at {KEY_PATH} has wrong length "
                f"({len(key)} bytes, expected {KEY_LENGTH}). Refusing to overwrite."
            )

        # Migrate pre-marker installations: if key exists but marker is missing,
        # create it so future detection works.
        if not marker_exists:
            try:
                _write_marker()
                logger.info("Created init marker for existing key at %s", KEY_PATH)
            except OSError as e:
                logger.warning("Could not create init marker %s: %s", marker, e)

        _key_cache = key
        logger.info("Loaded encryption key from %s", KEY_PATH)
        return key

    # ── Key file missing ──
    if marker_exists:
        # Post-initialization key loss — REFUSE to regenerate
        raise KeyFileMissingError(
            f"Encryption key missing at {KEY_PATH} but initialization marker "
            f"{marker} exists. The key has been lost or deleted AFTER initial "
            f"setup. Refusing to regenerate because all existing encrypted "
            f"fields would become permanently unrecoverable. "
            f"Restore the key from a secure backup, or — if you accept total "
            f"loss of encrypted data — manually delete the marker file to "
            f"force re-initialization."
        )

    # ── First-time initialization: no key, no marker ──
    logger.warning(
        "No encryption key found at %s and no init marker — performing "
        "first-time initialization",
        KEY_PATH,
    )
    key = AESGCM.generate_key(bit_length=256)
    try:
        key_dir = os.path.dirname(KEY_PATH)
        if key_dir:
            os.makedirs(key_dir, exist_ok=True)
        with open(KEY_PATH, "wb") as f:
            f.write(key)
        os.chmod(KEY_PATH, 0o600)
        _write_marker()
        logger.info("Encryption key successfully initialized at %s", KEY_PATH)
    except OSError as e:
        raise CorruptKeyError(
            f"Could not persist encryption key to {KEY_PATH}: {e}. "
            f"Refusing to use an ephemeral in-memory key — encrypted data "
            f"would be lost on restart."
        ) from e

    _key_cache = key
    return key


def encrypt_field(plaintext: Optional[str]) -> Tuple[Optional[bytes], Optional[bytes]]:
    """Encrypt a plaintext string.

    Returns (ciphertext, iv) as bytes. Both are None if plaintext is None or empty.
    The ciphertext includes the AES-GCM authentication tag.
    """
    if plaintext is None or plaintext == "":
        return None, None
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)

    key = load_or_generate_key()
    aesgcm = AESGCM(key)
    iv = os.urandom(IV_LENGTH)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), associated_data=None)
    return ciphertext, iv


def decrypt_field(ciphertext: Optional[bytes], iv: Optional[bytes]) -> Optional[str]:
    """Decrypt ciphertext back to its original string.

    Returns None if ciphertext or iv is None.
    Returns None and logs an error if authentication fails (tampered ciphertext).
    """
    if ciphertext is None or iv is None:
        return None

    key = load_or_generate_key()
    aesgcm = AESGCM(key)
    try:
        plaintext_bytes = aesgcm.decrypt(iv, ciphertext, associated_data=None)
        return plaintext_bytes.decode("utf-8")
    except Exception as e:
        logger.error("Failed to decrypt field (possible tampering or key mismatch): %s", e)
        return None


def reset_key_cache() -> None:
    """Test helper — clears the in-memory key cache."""
    global _key_cache
    _key_cache = None
