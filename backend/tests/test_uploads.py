import os
import pytest
from conftest import UPLOAD_ROOT, login, make_user

MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x01" * 2048

def video(seed: int = 0) -> bytes:
    return MP4 + bytes([seed]) * 64

def upload(client, headers, name="lesson.mp4", body=None):
    return client.post("/api/recordings/upload", params={"filename": name}, content=video() if body is None else body,
                       headers={**headers, "Content-Type": "application/octet-stream"})

def test_upload_requires_authentication(client):
    assert client.post("/api/recordings/upload", params={"filename": "a.mp4"}, content=MP4).status_code == 401

def test_viewer_cannot_upload(client, viewer_headers):
    assert upload(client, viewer_headers).status_code == 403

def test_upload_stores_file_and_metadata(client, admin_headers):
    response = upload(client, admin_headers, name="Biology — Lesson 1.mp4")
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "Biology — Lesson 1.mp4" and body["status"] == "uploaded"
    assert body["file_size_bytes"] == len(video()) and len(body["checksum_sha256"]) == 64
    assert body["file_path"].startswith("recordings/") and body["file_path"].endswith(".mp4")
    assert os.path.isfile(os.path.join(UPLOAD_ROOT, body["file_path"]))
    assert os.listdir(os.path.join(UPLOAD_ROOT, "tmp")) == []  # no leftover partial files

def test_client_supplied_path_is_not_used(client, admin_headers):
    body = upload(client, admin_headers, name="../../etc/evil.mp4").json()
    assert body["filename"] == "evil.mp4" and ".." not in body["file_path"]

def test_rejects_bad_extension_and_content(client, admin_headers):
    assert upload(client, admin_headers, name="notes.exe").status_code == 415
    assert upload(client, admin_headers, name="fake.mp4", body=b"MZ" + b"\x00" * 100).status_code == 415
    assert upload(client, admin_headers, name="empty.mp4", body=b"").status_code in (400, 415)

def test_rejects_oversized_upload(client, admin_headers, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    os.makedirs(os.path.join(UPLOAD_ROOT, "tmp"), exist_ok=True)  # the fixture deletes the folder after each test; the app creates it at start-up
    big = MP4 + b"\x02" * (1024 * 1024 + 10)
    assert upload(client, admin_headers, name="big.mp4", body=big).status_code == 413
    assert os.listdir(os.path.join(UPLOAD_ROOT, "tmp")) == []

def test_duplicate_file_is_rejected(client, admin_headers):
    assert upload(client, admin_headers, name="a.mp4").status_code == 201
    duplicate = upload(client, admin_headers, name="b.mp4")
    assert duplicate.status_code == 409 and "already uploaded" in duplicate.json()["detail"]

def test_file_link_download_and_range(client, admin_headers):
    rec = upload(client, admin_headers).json()
    link = client.get(f"/api/recordings/{rec['id']}/file-link", headers=admin_headers).json()
    assert link["url"].startswith("/api/files/") and link["expires_in"] > 0
    full = client.get(link["url"])  # no Authorization header: the signed link is the credential
    assert full.status_code == 200 and full.content == video()
    assert full.headers["content-type"].startswith("video/mp4")
    part = client.get(link["url"], headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == video()[:10]
    attach = client.get(client.get(f"/api/recordings/{rec['id']}/file-link?download=true", headers=admin_headers).json()["url"])
    assert "attachment" in attach.headers["content-disposition"]

def test_viewer_can_get_file_link(client, admin_headers, viewer_headers):
    rec = upload(client, admin_headers).json()
    assert client.get(f"/api/recordings/{rec['id']}/file-link", headers=viewer_headers).status_code == 200

def test_file_link_needs_login_and_bad_tokens_are_rejected(client, admin_headers):
    rec = upload(client, admin_headers).json()
    assert client.get(f"/api/recordings/{rec['id']}/file-link").status_code == 401
    assert client.get("/api/files/not-a-token").status_code == 403
    access_token = admin_headers["Authorization"].split()[1]
    assert client.get(f"/api/files/{access_token}").status_code == 403  # sign-in token is not a download token

def test_download_token_is_not_a_sign_in_token(client, admin_headers):
    rec = upload(client, admin_headers).json()
    token = client.get(f"/api/recordings/{rec['id']}/file-link", headers=admin_headers).json()["url"].rsplit("/", 1)[1]
    assert client.get("/api/recordings", headers={"Authorization": f"Bearer {token}"}).status_code == 401

def test_missing_file_returns_404(client, admin_headers):
    rec = client.post("/api/recordings", json={"filename": "metadata-only.mp4"}, headers=admin_headers).json()
    assert rec["file_path"] is None
    assert client.get(f"/api/recordings/{rec['id']}/file-link", headers=admin_headers).status_code == 404

def test_file_path_cannot_be_set_through_the_api(client, admin_headers):
    rec = client.post("/api/recordings", json={"filename": "x.mp4", "file_path": "../../etc/passwd"}, headers=admin_headers).json()
    assert rec["file_path"] is None
    patched = client.patch(f"/api/recordings/{rec['id']}", json={"file_path": "/etc/passwd"}, headers=admin_headers).json()
    assert patched["file_path"] is None

def test_legacy_path_outside_storage_is_never_served(client, admin_headers):
    from app.database import SessionLocal
    from app import models
    with SessionLocal() as db:
        item = models.Recording(filename="legacy.mp4", file_path="../../../etc/passwd")
        db.add(item); db.commit(); rid = item.id
    assert client.get(f"/api/recordings/{rid}/file-link", headers=admin_headers).status_code == 404

def test_deleting_recording_removes_file(client, admin_headers):
    rec = upload(client, admin_headers).json()
    path = os.path.join(UPLOAD_ROOT, rec["file_path"])
    assert os.path.isfile(path)
    assert client.delete(f"/api/recordings/{rec['id']}", headers=admin_headers).status_code == 204
    assert not os.path.exists(path)

def test_storage_summary(client, admin_headers, viewer_headers):
    upload(client, admin_headers)
    summary = client.get("/api/storage/summary", headers=viewer_headers).json()
    assert summary["files"] == 1 and summary["total_bytes"] == len(video())
    assert ".mp4" in summary["allowed_extensions"] and summary["max_upload_bytes"] > 0
