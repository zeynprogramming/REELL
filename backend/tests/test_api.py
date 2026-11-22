def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_recording_crud_and_dashboard(client, admin_headers):
    created = client.post("/api/recordings", json={"filename": "lesson-01.mp4"}, headers=admin_headers)
    assert created.status_code == 201
    recording_id = created.json()["id"]
    assert client.get("/api/dashboard/summary", headers=admin_headers).json()["total_recordings"] == 1

    updated = client.patch(f"/api/recordings/{recording_id}", json={"status": "ready"}, headers=admin_headers)
    assert updated.status_code == 200
    assert updated.json()["status"] == "ready"

    assert client.get("/api/recordings/99999", headers=admin_headers).status_code == 404
    assert client.delete(f"/api/recordings/{recording_id}", headers=admin_headers).status_code == 204

def test_job_creation_rules(client, admin_headers):
    meta_only = client.post("/api/recordings", json={"filename": "lesson-02.mp4"}, headers=admin_headers).json()
    assert client.post("/api/jobs", json={"recording_id": 99999, "job_type": "video_validation"}, headers=admin_headers).status_code == 404
    no_file = client.post("/api/jobs", json={"recording_id": meta_only["id"], "job_type": "video_validation"}, headers=admin_headers)
    assert no_file.status_code == 400 and "no uploaded file" in no_file.json()["detail"]
    unknown = client.post("/api/jobs", json={"recording_id": meta_only["id"], "job_type": "transcribe_everything"}, headers=admin_headers)
    assert unknown.status_code == 400
    assert client.get("/api/jobs?status=queued", headers=admin_headers).json() == []

def test_jobs_cannot_be_edited_by_hand(client, admin_headers):
    assert client.patch("/api/jobs/1", json={"status": "completed"}, headers=admin_headers).status_code == 405
