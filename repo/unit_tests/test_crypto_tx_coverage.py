"""Coverage for crypto edge cases, _tx rollback, and session_cookie
signing/verification error paths.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

import pytest

from src.database import get_connection, init_db


# ════════════════════════════════════════════════════════════
# Crypto — all error paths
# ════════════════════════════════════════════════════════════

class TestCryptoCoverage:
    def _fresh_key(self, tmp_path, monkeypatch):
        """Point the crypto module at a fresh key path."""
        import src.security.crypto as crypto
        key_path = str(tmp_path / "k.key")
        monkeypatch.setattr(crypto, "KEY_PATH", key_path)
        crypto.reset_key_cache()
        return crypto, key_path

    def _marker_path(self, crypto, key_path):
        return key_path + crypto.MARKER_SUFFIX

    def test_encrypt_then_decrypt_roundtrip(self, tmp_path, monkeypatch):
        crypto, _ = self._fresh_key(tmp_path, monkeypatch)
        ct, iv = crypto.encrypt_field("hello world")
        assert isinstance(ct, bytes) and isinstance(iv, bytes)
        pt = crypto.decrypt_field(ct, iv)
        assert pt == "hello world"

    def test_decrypt_with_wrong_iv_returns_none(self, tmp_path, monkeypatch):
        crypto, _ = self._fresh_key(tmp_path, monkeypatch)
        ct, iv = crypto.encrypt_field("secret")
        bad_iv = bytes([b ^ 0xFF for b in iv])
        assert crypto.decrypt_field(ct, bad_iv) is None

    def test_decrypt_with_tampered_ciphertext_returns_none(self, tmp_path, monkeypatch):
        crypto, _ = self._fresh_key(tmp_path, monkeypatch)
        ct, iv = crypto.encrypt_field("secret")
        tampered = bytes([ct[0] ^ 0xFF]) + ct[1:]
        assert crypto.decrypt_field(tampered, iv) is None

    def test_decrypt_with_none_inputs_returns_none(self, tmp_path, monkeypatch):
        crypto, _ = self._fresh_key(tmp_path, monkeypatch)
        assert crypto.decrypt_field(None, None) is None
        assert crypto.decrypt_field(b"", b"") is None

    def test_key_loss_after_init_raises(self, tmp_path, monkeypatch):
        crypto, key_path = self._fresh_key(tmp_path, monkeypatch)
        # Initialize the key
        crypto.load_or_generate_key()
        marker = self._marker_path(crypto, key_path)
        assert os.path.exists(key_path)
        assert os.path.exists(marker)

        # Delete the key but keep the marker — simulates POST-INIT LOSS
        os.remove(key_path)
        crypto.reset_key_cache()
        with pytest.raises(crypto.KeyFileMissingError):
            crypto.load_or_generate_key()

    def test_corrupt_key_raises(self, tmp_path, monkeypatch):
        crypto, key_path = self._fresh_key(tmp_path, monkeypatch)
        # Write an invalid-length "key"
        with open(key_path, "wb") as f:
            f.write(b"short")
        # Mark it as initialized so loader won't regenerate
        with open(self._marker_path(crypto, key_path), "w") as f:
            f.write("1")
        crypto.reset_key_cache()
        with pytest.raises(crypto.CorruptKeyError):
            crypto.load_or_generate_key()


# ════════════════════════════════════════════════════════════
# _tx — atomic rollback + savepoint rollback
# ════════════════════════════════════════════════════════════

@pytest.fixture
def db_conn(tmp_path):
    path = str(tmp_path / "tx.db")
    init_db(path).close()
    conn = get_connection(path)
    yield conn
    conn.close()


class TestAtomicCoverage:
    def test_atomic_rolls_back_on_exception(self, db_conn):
        from src.services._tx import atomic
        from src.repositories import StoreRepository
        from src.models.store import Store
        repo = StoreRepository(db_conn)
        repo.create(Store(code="SVC_BEFORE", name="Before"))
        db_conn.commit()

        with pytest.raises(RuntimeError, match="boom"):
            with atomic(db_conn):
                repo.create(Store(code="SVC_DURING", name="During"))
                raise RuntimeError("boom")

        # The "During" row must NOT be present — rollback honored.
        assert repo.get_by_code("SVC_DURING") is None
        # The "Before" row (committed earlier) must still be there.
        assert repo.get_by_code("SVC_BEFORE") is not None

    def test_atomic_commits_on_success(self, db_conn):
        from src.services._tx import atomic
        from src.repositories import StoreRepository
        from src.models.store import Store
        repo = StoreRepository(db_conn)
        with atomic(db_conn):
            repo.create(Store(code="SVC_OK", name="OK"))
        assert repo.get_by_code("SVC_OK") is not None

    def test_savepoint_rolls_back_only_inner_block(self, db_conn):
        from src.services._tx import atomic, savepoint
        from src.repositories import StoreRepository
        from src.models.store import Store
        repo = StoreRepository(db_conn)
        with atomic(db_conn):
            repo.create(Store(code="SP_OUTER", name="Outer"))
            try:
                with savepoint(db_conn):
                    repo.create(Store(code="SP_INNER", name="Inner"))
                    raise RuntimeError("inner fails")
            except RuntimeError:
                pass  # outer continues
        # Outer committed, inner was rolled back
        assert repo.get_by_code("SP_OUTER") is not None
        assert repo.get_by_code("SP_INNER") is None

    def test_savepoint_commits_on_success(self, db_conn):
        from src.services._tx import atomic, savepoint
        from src.repositories import StoreRepository
        from src.models.store import Store
        repo = StoreRepository(db_conn)
        with atomic(db_conn):
            with savepoint(db_conn):
                repo.create(Store(code="SP_OK", name="OK"))
        assert repo.get_by_code("SP_OK") is not None


# ════════════════════════════════════════════════════════════
# Session cookie — sign + verify + tampered/forged
# ════════════════════════════════════════════════════════════

class TestSessionCookieCoverage:
    @pytest.fixture
    def clean_key(self, tmp_path, monkeypatch):
        key_path = str(tmp_path / "sk")
        monkeypatch.setenv("SESSION_KEY_PATH", key_path)
        import src.security.session_cookie as sc
        monkeypatch.setattr(sc, "SESSION_KEY_PATH", key_path)
        sc._key_cache = None
        return sc

    def test_roundtrip_sign_verify(self, clean_key):
        sc = clean_key
        signed = sc.sign_session_nonce("abc123")
        assert "." in signed
        recovered = sc.verify_session_cookie(signed)
        assert recovered == "abc123"

    def test_tampered_signature_rejected(self, clean_key):
        sc = clean_key
        signed = sc.sign_session_nonce("abc123")
        val, sig = signed.rsplit(".", 1)
        bad = val + "." + ("X" * len(sig))
        assert sc.verify_session_cookie(bad) is None

    def test_no_dot_rejected(self, clean_key):
        sc = clean_key
        assert sc.verify_session_cookie("no-dot-here") is None

    def test_empty_cookie_rejected(self, clean_key):
        sc = clean_key
        assert sc.verify_session_cookie("") is None
        assert sc.verify_session_cookie(None) is None

    def test_key_file_persists_across_loads(self, clean_key):
        sc = clean_key
        sig1 = sc.sign_session_nonce("x")
        # Force a cache miss and reload from disk
        sc._key_cache = None
        sig2 = sc.sign_session_nonce("x")
        # Both signatures should verify
        assert sc.verify_session_cookie(sig1) == "x"
        assert sc.verify_session_cookie(sig2) == "x"
