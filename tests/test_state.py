import re
import uuid

import pytest

from app.errors import AppError
from tests.support import arrive_active, arrive_deploy_failed, fresh_slug

STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


def test_create_starts_provisioning(svc):
    tenant, task = svc.create_tenant(fresh_slug(), "  Acme  ")
    assert tenant["status"] == "provisioning"
    assert tenant["version"] == 1
    assert tenant["name"] == "Acme"
    assert STAMP.fullmatch(tenant["created_at"])
    assert STAMP.fullmatch(tenant["updated_at"])
    assert task["type"] == "deploy"
    assert task["status"] == "accepted"
    assert task["tenant_id"] == tenant["id"]


def test_deploy_done_makes_tenant_active(svc):
    tenant, task = svc.create_tenant(fresh_slug(), "Acme")
    assert svc.apply_progress(uuid.uuid4(), task["id"], "in_progress") == "applied"
    mid = svc.get_tenant(tenant["id"])
    assert mid["status"] == "provisioning"
    assert mid["version"] == 1
    assert svc.get_task(task["id"])["status"] == "in_progress"

    assert svc.apply_progress(uuid.uuid4(), task["id"], "done") == "applied"
    done = svc.get_tenant(tenant["id"])
    assert done["status"] == "active"
    assert done["version"] == 2
    assert svc.get_task(task["id"])["status"] == "done"


def test_deploy_failed(svc):
    tenant = arrive_deploy_failed(svc)
    assert tenant["status"] == "failed"
    assert tenant["version"] == 2


def test_terminal_result_without_in_progress_still_applies(svc):
    tenant, task = svc.create_tenant(fresh_slug(), "Acme")
    assert svc.apply_progress(uuid.uuid4(), task["id"], "done") == "applied"
    assert svc.get_tenant(tenant["id"])["status"] == "active"


def test_update_done_returns_to_active(svc):
    tenant = arrive_active(svc)
    updated, task = svc.update_tenant(tenant["id"], "Acme Inc", tenant["version"])
    assert updated["status"] == "updating"
    assert updated["name"] == "Acme Inc"
    assert updated["version"] == tenant["version"] + 1
    svc.apply_progress(uuid.uuid4(), task["id"], "in_progress")
    svc.apply_progress(uuid.uuid4(), task["id"], "done")
    final = svc.get_tenant(tenant["id"])
    assert final["status"] == "active"
    assert final["name"] == "Acme Inc"
    assert final["version"] == updated["version"] + 1


def test_update_failed(svc):
    tenant = arrive_active(svc)
    updated, task = svc.update_tenant(tenant["id"], "Acme Inc", tenant["version"])
    svc.apply_progress(uuid.uuid4(), task["id"], "failed")
    final = svc.get_tenant(tenant["id"])
    assert final["status"] == "failed"
    assert final["name"] == "Acme Inc"


def test_destroy_done(svc):
    tenant = arrive_active(svc)
    destroying, task = svc.delete_tenant(tenant["id"])
    assert destroying["status"] == "destroying"
    svc.apply_progress(uuid.uuid4(), task["id"], "in_progress")
    svc.apply_progress(uuid.uuid4(), task["id"], "done")
    final = svc.get_tenant(tenant["id"])
    assert final["status"] == "destroyed"


def test_destroy_failed_then_delete_again(svc):
    tenant = arrive_active(svc)
    _destroying, task = svc.delete_tenant(tenant["id"])
    svc.apply_progress(uuid.uuid4(), task["id"], "failed")
    failed = svc.get_tenant(tenant["id"])
    assert failed["status"] == "failed"
    again, task2 = svc.delete_tenant(tenant["id"])
    assert again["status"] == "destroying"
    svc.apply_progress(uuid.uuid4(), task2["id"], "done")
    assert svc.get_tenant(tenant["id"])["status"] == "destroyed"


def test_slug_stays_taken_after_destroy(svc):
    slug = fresh_slug()
    tenant, task = svc.create_tenant(slug, "Acme")
    svc.apply_progress(uuid.uuid4(), task["id"], "done")
    _row, destroy = svc.delete_tenant(tenant["id"])
    svc.apply_progress(uuid.uuid4(), destroy["id"], "done")
    with pytest.raises(AppError) as caught:
        svc.create_tenant(slug, "Other")
    assert caught.value.code == "tenant_already_exists"


def test_patch_rejected_until_active(svc):
    tenant, _task = svc.create_tenant(fresh_slug(), "Acme")
    with pytest.raises(AppError) as caught:
        svc.update_tenant(tenant["id"], "Nope", tenant["version"])
    assert caught.value.code == "tenant_update_not_allowed"


def test_patch_rejects_stale_version_when_status_matches(svc):
    tenant = arrive_active(svc)
    with pytest.raises(AppError) as caught:
        svc.update_tenant(tenant["id"], "Nope", tenant["version"] - 1)
    assert caught.value.code == "tenant_version_conflict"


def test_delete_rejected_while_provisioning(svc):
    tenant, _task = svc.create_tenant(fresh_slug(), "Acme")
    with pytest.raises(AppError) as caught:
        svc.delete_tenant(tenant["id"])
    assert caught.value.code == "tenant_update_not_allowed"


def test_delete_rejected_while_updating(svc):
    tenant = arrive_active(svc)
    svc.update_tenant(tenant["id"], "Busy", tenant["version"])
    with pytest.raises(AppError) as caught:
        svc.delete_tenant(tenant["id"])
    assert caught.value.code == "tenant_update_not_allowed"


def test_missing_tenant_and_bad_slug(svc):
    with pytest.raises(AppError) as missing:
        svc.get_tenant(uuid.uuid4())
    assert missing.value.code == "tenant_not_found"
    with pytest.raises(AppError) as bad:
        svc.create_tenant("A", "Acme")
    assert bad.value.code == "invalid_request"
    with pytest.raises(AppError) as blank:
        svc.create_tenant(fresh_slug(), "   ")
    assert blank.value.code == "invalid_request"


def test_new_pool_still_sees_the_row(svc):
    tenant, _task = svc.create_tenant(fresh_slug(), "Acme")
    from app.service import Service

    other = Service(svc.pool)
    assert other.get_tenant(tenant["id"])["slug"] == tenant["slug"]
