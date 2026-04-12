import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fullstack", "backend"))

from src.database import init_db


@pytest.fixture
def db_conn():
    conn = init_db(":memory:")
    yield conn
    conn.close()
