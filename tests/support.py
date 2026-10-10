import uuid

from app.service import Service


def fresh_slug(prefix: str = "tn") -> str:
    return prefix + uuid.uuid4().hex[:10]


def arrive_active(svc: Service, name: str = "Acme") -> dict:
    _tenant, task = svc.create_tenant(fresh_slug(), name)
    svc.apply_progress(uuid.uuid4(), task["id"], "in_progress")
    svc.apply_progress(uuid.uuid4(), task["id"], "done")
    return svc.get_tenant(_tenant["id"])


def arrive_deploy_failed(svc: Service) -> dict:
    tenant, task = svc.create_tenant(fresh_slug(), "Acme")
    svc.apply_progress(uuid.uuid4(), task["id"], "in_progress")
    svc.apply_progress(uuid.uuid4(), task["id"], "failed")
    return svc.get_tenant(tenant["id"])
