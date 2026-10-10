import uuid

from fastapi.testclient import TestClient

from app.api import create_app
from tests.support import fresh_slug


def _client(svc):
    return TestClient(create_app(svc))


def test_create_get_and_list(svc):
    client = _client(svc)
    slug = fresh_slug()
    created = client.post("/tenants", json={"slug": slug, "name": "Acme"})
    assert created.status_code == 201
    body = created.json()
    tenant_id = body["tenant"]["id"]
    task_id = body["task"]["id"]
    assert body["tenant"]["status"] == "provisioning"
    assert body["task"]["type"] == "deploy"

    fetched = client.get(f"/tenants/{tenant_id}")
    assert fetched.status_code == 200
    assert fetched.json()["slug"] == slug

    listed = client.get("/tenants", params={"status": "provisioning"})
    assert listed.status_code == 200
    assert any(item["id"] == tenant_id for item in listed.json()["items"])

    task = client.get(f"/tasks/{task_id}")
    assert task.status_code == 200
    assert task.json()["tenant_id"] == tenant_id

    tasks = client.get("/tasks", params={"tenant_id": tenant_id})
    assert tasks.status_code == 200
    assert tasks.json()["items"][0]["id"] == task_id


def test_error_bodies(svc):
    client = _client(svc)
    missing = client.get(f"/tenants/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "tenant_not_found"

    bad = client.post("/tenants", json={"slug": "No", "name": "Acme"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_request"

    slug = fresh_slug()
    assert client.post("/tenants", json={"slug": slug, "name": "Acme"}).status_code == 201
    again = client.post("/tenants", json={"slug": slug, "name": "Other"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "tenant_already_exists"

    gone = client.get(f"/tasks/{uuid.uuid4()}")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "task_not_found"

    junk = client.post(
        "/tenants",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert junk.status_code == 400
    assert junk.json()["error"]["code"] == "invalid_request"


def test_patch_and_delete_status_codes(svc):
    client = _client(svc)
    created = client.post("/tenants", json={"slug": fresh_slug(), "name": "Acme"})
    tenant = created.json()["tenant"]
    task = created.json()["task"]

    early = client.patch(
        f"/tenants/{tenant['id']}",
        json={"name": "Nope", "version": tenant["version"]},
    )
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "tenant_update_not_allowed"

    blocked = client.delete(f"/tenants/{tenant['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "tenant_update_not_allowed"

    svc.apply_progress(uuid.uuid4(), task["id"], "done")
    current = client.get(f"/tenants/{tenant['id']}").json()
    stale = client.patch(
        f"/tenants/{tenant['id']}",
        json={"name": "Nope", "version": current["version"] - 1},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "tenant_version_conflict"

    patched = client.patch(
        f"/tenants/{tenant['id']}",
        json={"name": "Acme Inc", "version": current["version"]},
    )
    assert patched.status_code == 200
    assert patched.json()["tenant"]["status"] == "updating"
    assert patched.json()["task"]["type"] == "update"

    svc.apply_progress(uuid.uuid4(), patched.json()["task"]["id"], "done")
    deleted = client.delete(f"/tenants/{tenant['id']}")
    assert deleted.status_code == 202
    assert deleted.json()["tenant"]["status"] == "destroying"
    assert deleted.json()["task"]["type"] == "destroy"


def test_bad_page_and_filter(svc):
    client = _client(svc)
    bad_limit = client.get("/tenants", params={"limit": 0})
    assert bad_limit.status_code == 400
    assert bad_limit.json()["error"]["code"] == "invalid_request"
    bad_status = client.get("/tasks", params={"status": "nope"})
    assert bad_status.status_code == 400
    assert bad_status.json()["error"]["code"] == "invalid_request"
