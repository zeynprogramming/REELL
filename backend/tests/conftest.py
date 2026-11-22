import os
import shutil
import tempfile

# Must be set before the app is imported.
os.environ["DATABASE_URL"] = "sqlite:///./test_reel.db"
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-0123456789"
UPLOAD_ROOT = tempfile.mkdtemp(prefix="reel-test-uploads-")
os.environ["UPLOAD_DIR"] = UPLOAD_ROOT
os.environ["CELERY_EAGER"] = "1"  # run queued jobs inline: no Redis needed for tests

import pytest
from fastapi.testclient import TestClient
from app.database import Base, SessionLocal, engine
from app.main import app
from app import models
from app.security import email_throttle, hash_password, ip_throttle

PASSWORD = "correct-horse-battery"

def make_user(email: str, role: str, password: str = PASSWORD, active: bool = True) -> int:
    with SessionLocal() as db:
        user = models.User(email=email, full_name=email.split("@")[0].title(), role=role, is_active=active, password_hash=hash_password(password))
        db.add(user); db.commit()
        return user.id

@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    email_throttle._hits.clear(); ip_throttle._hits.clear()
    yield
    Base.metadata.drop_all(bind=engine)
    shutil.rmtree(UPLOAD_ROOT, ignore_errors=True)

@pytest.fixture()
def client():
    return TestClient(app)

def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})

@pytest.fixture()
def admin_headers(client):
    make_user("admin@example.com", "admin")
    return {"Authorization": f"Bearer {login(client, 'admin@example.com').json()['access_token']}"}

@pytest.fixture()
def viewer_headers(client):
    make_user("viewer@example.com", "viewer")
    return {"Authorization": f"Bearer {login(client, 'viewer@example.com').json()['access_token']}"}
