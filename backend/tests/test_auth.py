import pytest
from conftest import PASSWORD, login, make_user

DATA_ENDPOINTS = ["/api/dashboard/summary", "/api/recordings", "/api/jobs", "/api/transcripts",
                  "/api/video-metadata", "/api/publications", "/api/integrations", "/api/consents"]

@pytest.mark.parametrize("path", DATA_ENDPOINTS)
def test_data_endpoints_require_authentication(client, path):
    assert client.get(path).status_code == 401

def test_invalid_token_rejected(client):
    assert client.get("/api/recordings", headers={"Authorization": "Bearer not-a-token"}).status_code == 401

def test_login_success_and_me(client):
    make_user("admin@example.com", "admin")
    response = login(client, "  ADMIN@example.com ")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["user"]["role"] == "admin"
    assert "password" not in str(body["user"]).lower()
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "admin@example.com"

def test_login_failures_use_same_message(client):
    make_user("admin@example.com", "admin")
    wrong_pw = login(client, "admin@example.com", "wrong-password")
    unknown = login(client, "nobody@example.com", "wrong-password")
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["detail"] == unknown.json()["detail"]

def test_inactive_user_cannot_login(client):
    make_user("off@example.com", "viewer", active=False)
    assert login(client, "off@example.com").status_code == 401

def test_login_is_rate_limited(client):
    make_user("admin@example.com", "admin")
    for _ in range(5):
        assert login(client, "admin@example.com", "bad-password").status_code == 401
    blocked = login(client, "admin@example.com", PASSWORD)
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers

def test_viewer_is_read_only(client, viewer_headers):
    assert client.get("/api/recordings", headers=viewer_headers).status_code == 200
    denied = client.post("/api/recordings", json={"filename": "x.mp4"}, headers=viewer_headers)
    assert denied.status_code == 403

def test_editor_can_write_but_not_manage_users(client):
    make_user("editor@example.com", "editor")
    headers = {"Authorization": f"Bearer {login(client, 'editor@example.com').json()['access_token']}"}
    assert client.post("/api/recordings", json={"filename": "x.mp4"}, headers=headers).status_code == 201
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.get("/api/audit-logs", headers=headers).status_code == 403

def test_admin_creates_user_and_duplicate_rejected(client, admin_headers):
    payload = {"email": "New@Example.com", "full_name": "New User", "password": "a-long-password", "role": "editor"}
    created = client.post("/api/users", json=payload, headers=admin_headers)
    assert created.status_code == 201 and created.json()["email"] == "new@example.com"
    assert client.post("/api/users", json=payload, headers=admin_headers).status_code == 409
    assert login(client, "new@example.com", "a-long-password").status_code == 200

def test_user_validation(client, admin_headers):
    base = {"email": "a@example.com", "full_name": "A", "password": "a-long-password"}
    assert client.post("/api/users", json={**base, "password": "short"}, headers=admin_headers).status_code == 422
    assert client.post("/api/users", json={**base, "email": "not-an-email"}, headers=admin_headers).status_code == 422
    assert client.post("/api/users", json={**base, "role": "superuser"}, headers=admin_headers).status_code == 422

def test_admin_cannot_demote_or_deactivate_self(client, admin_headers):
    me = client.get("/api/auth/me", headers=admin_headers).json()
    assert client.patch(f"/api/users/{me['id']}", json={"role": "viewer"}, headers=admin_headers).status_code == 400
    assert client.patch(f"/api/users/{me['id']}", json={"is_active": False}, headers=admin_headers).status_code == 400

def test_deactivating_user_revokes_existing_token(client, admin_headers):
    uid = make_user("viewer@example.com", "viewer")
    token = login(client, "viewer@example.com").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/recordings", headers=headers).status_code == 200
    assert client.patch(f"/api/users/{uid}", json={"is_active": False}, headers=admin_headers).status_code == 200
    assert client.get("/api/recordings", headers=headers).status_code == 401

def test_change_password_revokes_old_token(client):
    make_user("admin@example.com", "admin")
    old = {"Authorization": f"Bearer {login(client, 'admin@example.com').json()['access_token']}"}
    wrong = client.post("/api/auth/change-password", json={"current_password": "nope-nope-nope", "new_password": "another-long-pass"}, headers=old)
    assert wrong.status_code == 400
    changed = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "another-long-pass"}, headers=old)
    assert changed.status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401
    new = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=new).status_code == 200
    assert login(client, "admin@example.com", PASSWORD).status_code == 401
    assert login(client, "admin@example.com", "another-long-pass").status_code == 200

def test_audit_log_records_events_without_secrets(client, admin_headers):
    login(client, "admin@example.com", "bad-password")
    logs = client.get("/api/audit-logs", headers=admin_headers)
    assert logs.status_code == 200
    actions = {entry["action"] for entry in logs.json()}
    assert {"login_success", "login_failed"} <= actions
    assert "bad-password" not in logs.text and PASSWORD not in logs.text
