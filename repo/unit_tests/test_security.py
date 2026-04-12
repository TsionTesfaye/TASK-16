"""Security hardening tests — crypto, masking, password hashing."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest

from src.security.crypto import (
    CorruptKeyError,
    KeyFileMissingError,
    decrypt_field,
    encrypt_field,
    reset_key_cache,
)
from src.security import masking


# ── AES-256-GCM encryption ──

class TestCrypto:
    def setup_method(self):
        # Use a temp key file to avoid touching /run/secrets
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".key")
        self.tmp.close()
        os.remove(self.tmp.name)  # start with no key file (first-init state)
        self.marker = self.tmp.name + ".initialized"
        if os.path.exists(self.marker):
            os.remove(self.marker)
        os.environ["RECLAIM_OPS_KEY_PATH"] = self.tmp.name
        reset_key_cache()
        # Reload module-level constant
        from src.security import crypto
        crypto.KEY_PATH = self.tmp.name

    def teardown_method(self):
        reset_key_cache()
        for p in (self.tmp.name, self.marker):
            if os.path.exists(p):
                os.remove(p)

    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "555-123-4567"
        ct, iv = encrypt_field(plaintext)
        assert ct is not None and iv is not None
        assert isinstance(ct, bytes) and isinstance(iv, bytes)
        assert len(iv) == 12
        # Ciphertext is different from plaintext
        assert plaintext.encode("utf-8") not in ct
        # Decrypt recovers original
        assert decrypt_field(ct, iv) == plaintext

    def test_encrypt_none_returns_none(self):
        ct, iv = encrypt_field(None)
        assert ct is None and iv is None
        ct, iv = encrypt_field("")
        assert ct is None and iv is None

    def test_decrypt_none_returns_none(self):
        assert decrypt_field(None, None) is None
        assert decrypt_field(None, b"x" * 12) is None

    def test_tampered_ciphertext_fails(self):
        ct, iv = encrypt_field("sensitive data")
        # Flip a byte in the ciphertext
        tampered = bytes([ct[0] ^ 1]) + ct[1:]
        assert decrypt_field(tampered, iv) is None

    def test_different_ivs_for_same_plaintext(self):
        ct1, iv1 = encrypt_field("same")
        ct2, iv2 = encrypt_field("same")
        assert iv1 != iv2
        assert ct1 != ct2

    def test_key_persisted_to_file(self):
        encrypt_field("anything")  # triggers first-time key generation
        assert os.path.exists(self.tmp.name)
        with open(self.tmp.name, "rb") as f:
            key = f.read()
        assert len(key) == 32  # AES-256

    def test_key_file_has_restricted_permissions(self):
        encrypt_field("anything")
        mode = os.stat(self.tmp.name).st_mode & 0o777
        assert mode == 0o600

    def test_marker_created_on_first_init(self):
        """After first-time key generation, the init marker must exist."""
        encrypt_field("anything")
        assert os.path.exists(self.marker)

    def test_key_loss_after_init_raises(self):
        """If the key is deleted AFTER init, refuse to regenerate.

        This protects against silent key rotation which would permanently
        destroy access to all previously-encrypted data.
        """
        # First init — generates key + marker
        encrypt_field("secret data")
        assert os.path.exists(self.tmp.name)
        assert os.path.exists(self.marker)

        # Simulate key loss (marker remains — this is the danger scenario)
        os.remove(self.tmp.name)
        reset_key_cache()

        with pytest.raises(KeyFileMissingError) as exc_info:
            encrypt_field("more data")
        assert "missing" in str(exc_info.value).lower()
        assert "marker" in str(exc_info.value).lower()

    def test_manual_reset_by_removing_marker_allows_reinit(self):
        """Admin can explicitly accept data loss by removing the marker file."""
        encrypt_field("initial")
        os.remove(self.tmp.name)
        os.remove(self.marker)  # admin explicit acknowledgement
        reset_key_cache()
        # Should now succeed (treated as fresh first-init)
        encrypt_field("new start")
        assert os.path.exists(self.tmp.name)
        assert os.path.exists(self.marker)

    def test_corrupt_key_raises(self):
        """A key file with wrong length must raise, not be overwritten."""
        # Write a garbage 10-byte "key"
        with open(self.tmp.name, "wb") as f:
            f.write(b"too_short!")
        reset_key_cache()
        with pytest.raises(CorruptKeyError) as exc_info:
            encrypt_field("x")
        assert "length" in str(exc_info.value).lower()
        # Verify the file was NOT overwritten
        with open(self.tmp.name, "rb") as f:
            assert f.read() == b"too_short!"

    def test_migration_creates_marker_for_existing_key(self):
        """If a key exists from a pre-marker install, the marker is backfilled."""
        # Simulate pre-marker install: write a valid key with no marker
        import secrets as _s
        with open(self.tmp.name, "wb") as f:
            f.write(_s.token_bytes(32))
        os.chmod(self.tmp.name, 0o600)
        assert not os.path.exists(self.marker)
        reset_key_cache()

        encrypt_field("migrate me")
        # Marker should now exist
        assert os.path.exists(self.marker)


# ── Masking ──

class TestMasking:
    def test_mask_phone_full(self):
        # 10 digits total → 6 bullets + "4567"
        assert masking.mask_phone("555-123-4567") == "••••••4567"

    def test_mask_phone_short(self):
        assert masking.mask_phone("12") == "****"

    def test_mask_phone_none(self):
        assert masking.mask_phone(None) is None
        assert masking.mask_phone("") is None

    def test_mask_address(self):
        assert masking.mask_address("123 Main St") == "[REDACTED ADDRESS]"
        assert masking.mask_address(None) is None

    def test_mask_last4(self):
        assert masking.mask_last4("4567") == "••••4567"
        assert masking.mask_last4("12") == "••••"
        assert masking.mask_last4(None) is None

    def test_mask_email(self):
        assert masking.mask_email("jane@example.com") == "j***@example.com"
        assert masking.mask_email(None) is None
        assert masking.mask_email("no-at-sign") is None


# ── bcrypt password hashing ──

class TestPasswordHashing:
    def setup_method(self):
        from src.database import init_db
        self.db = init_db(":memory:")

    def teardown_method(self):
        self.db.close()

    def _service(self):
        from src.repositories import (
            UserRepository, UserSessionRepository, SettingsRepository,
            AuditLogRepository,
        )
        from src.services.audit_service import AuditService
        from src.services.auth_service import AuthService
        audit = AuditService(AuditLogRepository(self.db))
        return AuthService(
            UserRepository(self.db),
            UserSessionRepository(self.db),
            SettingsRepository(self.db),
            audit,
        )

    def test_bcrypt_hash_format(self):
        svc = self._service()
        h = svc._hash_password("SecurePass123!")
        assert h.startswith("$2")  # bcrypt marker

    def test_bcrypt_verify_correct_password(self):
        svc = self._service()
        h = svc._hash_password("CorrectHorseBatteryStaple")
        assert svc._verify_password("CorrectHorseBatteryStaple", h) is True

    def test_bcrypt_verify_wrong_password(self):
        svc = self._service()
        h = svc._hash_password("CorrectPassword")
        assert svc._verify_password("WrongPassword", h) is False

    def test_pbkdf2_backward_compat(self):
        """Legacy PBKDF2 hashes from older user records must still verify."""
        import hashlib
        svc = self._service()
        salt = "abcdef1234567890"
        pw = "LegacyPassword"
        h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000).hex()
        stored = f"{salt}:{h}"
        assert svc._verify_password(pw, stored) is True
        assert svc._verify_password("wrong", stored) is False

    def test_long_password_not_truncated(self):
        svc = self._service()
        long_pw = "A" * 100  # > bcrypt's 72-byte limit
        h = svc._hash_password(long_pw)
        # Verify long password works
        assert svc._verify_password(long_pw, h) is True
        # A different long password must NOT match (bcrypt naive would truncate)
        other = "A" * 72 + "B" * 28
        assert svc._verify_password(other, h) is False

    def test_empty_hash_rejected(self):
        svc = self._service()
        assert svc._verify_password("anything", "") is False
        assert svc._verify_password("anything", None) is False


# ── CSRF enforcement via API ──

@pytest.fixture
def csrf_app(tmp_path, monkeypatch):
    """App fixture for CSRF tests — sets env vars that create_app needs."""
    from app import create_app
    monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("SESSION_KEY_PATH", str(tmp_path / "session_key"))
    import src.security.session_cookie as _sc
    _sc._key_cache = None

    db_path = str(tmp_path / "csrf_test.db")
    application = create_app(db_path=db_path)
    application.config["TESTING"] = True

    with application.app_context():
        from app import get_db
        from flask import g
        g.db_path = db_path
        db = get_db()
        from src.repositories import (
            StoreRepository, SettingsRepository, UserRepository,
        )
        from src.models.store import Store
        from src.models.user import User
        from src.models.settings import Settings
        from src.services.auth_service import AuthService
        from src.services.audit_service import AuditService
        from src.repositories import AuditLogRepository, UserSessionRepository
        store = StoreRepository(db).create(Store(code="S1", name="Test"))
        SettingsRepository(db).create(Settings(store_id=store.id))
        audit = AuditService(AuditLogRepository(db))
        auth = AuthService(
            UserRepository(db), UserSessionRepository(db),
            SettingsRepository(db), audit,
        )
        user_repo = UserRepository(db)
        user_repo.create(User(
            store_id=store.id, username="csrfuser",
            password_hash=auth._hash_password("TestPassword123!"),
            display_name="CSRF User", role="front_desk_agent",
        ))
        db.commit()

    return application


class TestCSRFEnforcement:
    def test_mutating_request_without_csrf_is_rejected(self, csrf_app):
        with csrf_app.test_client() as c:
            # Login to get session cookie
            r = c.post("/api/auth/login", json={
                "username": "csrfuser", "password": "TestPassword123!",
            })
            assert r.status_code == 200
            # Attempt a mutating request WITHOUT CSRF header
            r2 = c.post("/api/tickets", json={"foo": "bar"})
            assert r2.status_code == 403
            assert "CSRF" in r2.get_json()["error"]["message"]

    def test_mutating_request_with_valid_csrf_passes(self, csrf_app):
        with csrf_app.test_client() as c:
            r = c.post("/api/auth/login", json={
                "username": "csrfuser", "password": "TestPassword123!",
            })
            token = r.get_json()["data"]["csrf_token"]
            # Should pass CSRF but fail validation (missing fields)
            r2 = c.post("/api/tickets", json={}, headers={"X-CSRF-Token": token})
            assert r2.status_code == 400
            assert "Missing required fields" in r2.get_json()["error"]["message"]

    def test_mutating_request_with_wrong_csrf_rejected(self, csrf_app):
        with csrf_app.test_client() as c:
            c.post("/api/auth/login", json={
                "username": "csrfuser", "password": "TestPassword123!",
            })
            r2 = c.post("/api/tickets", json={}, headers={"X-CSRF-Token": "wrong_token"})
            assert r2.status_code == 403

    def test_get_request_bypasses_csrf(self, csrf_app):
        with csrf_app.test_client() as c:
            c.post("/api/auth/login", json={
                "username": "csrfuser", "password": "TestPassword123!",
            })
            # GET without CSRF header must still work
            r = c.get("/api/settings")
            assert r.status_code == 200

    def test_csrf_cookies_set_after_login(self, csrf_app):
        with csrf_app.test_client() as c:
            r = c.post("/api/auth/login", json={
                "username": "csrfuser", "password": "TestPassword123!",
            })
            # Both cookies present
            cookies = r.headers.getlist("Set-Cookie")
            joined = " ".join(cookies)
            assert "session_nonce=" in joined
            assert "csrf_token=" in joined
            assert "HttpOnly" in joined  # session cookie is httponly
            assert "SameSite=Strict" in joined
