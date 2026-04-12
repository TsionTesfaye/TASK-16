import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

from app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Tests run without TLS certs — explicitly opt into dev mode
    monkeypatch.setenv("RECLAIM_OPS_DEV_MODE", "true")
    monkeypatch.setenv("RECLAIM_OPS_REQUIRE_TLS", "false")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    db_path = str(tmp_path / "test.db")
    application = create_app(db_path=db_path)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    with app.test_client() as client:
        yield client
