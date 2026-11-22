def _recording(client, headers, duration=None):
    r = client.post("/api/recordings", json={"filename": "lesson.mp4", "status": "uploaded"}, headers=headers)
    assert r.status_code == 201
    rid = r.json()["id"]
    if duration:
        client.patch(f"/api/recordings/{rid}", json={"duration_seconds": duration}, headers=headers)
    return rid

def test_metadata_roundtrip_and_chapter_order(client, admin_headers):
    rid = _recording(client, admin_headers)
    body = {"title": " Intro ", "description": "Hello", "tags": ["python", "Python", " web "], "chapters": [{"time_seconds": 90, "title": "Second"}, {"time_seconds": 0, "title": "Start"}]}
    r = client.put(f"/api/recordings/{rid}/metadata", json=body, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["title"] == "Intro" and r.json()["tags"] == ["python", "web"]
    assert [c["title"] for c in r.json()["chapters"]] == ["Start", "Second"]
    ws = client.get(f"/api/recordings/{rid}/workspace", headers=admin_headers).json()
    assert ws["metadata"]["title"] == "Intro" and ws["transcript"] is None and ws["publications"] == []

def test_duplicate_chapter_times_rejected(client, admin_headers):
    rid = _recording(client, admin_headers)
    ch = [{"time_seconds": 5, "title": "A"}, {"time_seconds": 5, "title": "B"}]
    assert client.put(f"/api/recordings/{rid}/metadata", json={"chapters": ch}, headers=admin_headers).status_code == 422

def test_transcript_is_updated_not_duplicated(client, admin_headers):
    rid = _recording(client, admin_headers)
    client.put(f"/api/recordings/{rid}/transcript", json={"language": "hy", "content": "one"}, headers=admin_headers)
    client.put(f"/api/recordings/{rid}/transcript", json={"language": "hy", "content": "two"}, headers=admin_headers)
    items = client.get(f"/api/transcripts?recording_id={rid}", headers=admin_headers).json()
    assert len(items) == 1 and items[0]["content"] == "two"

def test_manual_publication_validates_link_and_can_be_deleted(client, admin_headers):
    rid = _recording(client, admin_headers)
    assert client.post(f"/api/recordings/{rid}/publications", json={"platform": "YouTube", "url": "javascript:alert(1)"}, headers=admin_headers).status_code == 422
    r = client.post(f"/api/recordings/{rid}/publications", json={"platform": "YouTube", "url": "https://youtu.be/abc", "visibility": "unlisted"}, headers=admin_headers)
    assert r.status_code == 201 and r.json()["published_at"] is not None
    assert client.delete(f"/api/publications/{r.json()['id']}", headers=admin_headers).status_code == 204

def test_viewer_cannot_change_but_can_read(client, admin_headers, viewer_headers):
    rid = _recording(client, admin_headers)
    assert client.get(f"/api/recordings/{rid}/workspace", headers=viewer_headers).status_code == 200
    assert client.put(f"/api/recordings/{rid}/metadata", json={"title": "x"}, headers=viewer_headers).status_code == 403

def test_consent_update_and_delete(client, admin_headers):
    c = client.post("/api/consents", json={"external_student_id": "STU-1", "photo_video_allowed": False}, headers=admin_headers).json()
    r = client.patch(f"/api/consents/{c['id']}", json={"photo_video_allowed": True}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["photo_video_allowed"] is True
    assert client.delete(f"/api/consents/{c['id']}", headers=admin_headers).status_code == 204
