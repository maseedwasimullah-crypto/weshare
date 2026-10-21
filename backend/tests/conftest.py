"""Shared pytest fixtures for the WeShare! backend test suite.

The test database is always separate from the development database:

* set ``TEST_DATABASE_URL`` to run against a disposable PostgreSQL database,
* otherwise an isolated SQLite file in the system temp folder is used.

``DATABASE_URL`` is overwritten here *before* ``app.config`` is imported so the
application can never touch the developer database while testing.
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    _tmp_dir = Path(tempfile.mkdtemp(prefix="weshare-tests-"))
    TEST_DATABASE_URL = f"sqlite:///{(_tmp_dir / 'weshare_test.db').as_posix()}"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-" + "0" * 48)
os.environ["DEV_VERIFICATION_TOKENS"] = "true"
os.environ["EMAIL_HOST"] = ""
os.environ["EMAIL_FROM"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

STRONG_PASSWORD = "Str0ng!Passw0rd#1"


@pytest.fixture(scope="session", autouse=True)
def prepared_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def blocked_terms_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("moderation") / "blocked_terms.txt"
    path.write_text("forbiddenterm\n# comment line\n\n", encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def promote_admin():
    """Grant the administrator role to an existing account (test helper)."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User

    def _promote(email: str):
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                raise AssertionError(f"no account for {email}")
            user.role = "admin"
            session.commit()
            return user

    return _promote


@pytest.fixture
def use_blocked_terms(blocked_terms_file, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "moderation_blocked_terms_file", str(blocked_terms_file))
    yield blocked_terms_file


def register(client, email, password=STRONG_PASSWORD, verify=True):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "confirm_password": password},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    if verify:
        token = data.get("verification_token")
        assert token, f"no verification token returned: {data}"
        verified = client.post("/api/auth/verify", json={"token": token})
        assert verified.status_code == 200, verified.text
    return data


def login(client, email, password=STRONG_PASSWORD):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}
