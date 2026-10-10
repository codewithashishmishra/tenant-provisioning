import logging
import uuid

from psycopg.errors import UniqueViolation

from app import repo
from app.clock import utcnow
from app.errors import (
    invalid_request,
    task_not_found,
    tenant_already_exists,
    tenant_not_found,
    tenant_update_not_allowed,
    tenant_version_conflict,
)
from app.messages import task_payload
from app.schemas import (
    TASK_STATUSES,
    TENANT_STATUSES,
    check_choice,
    check_name,
    check_page,
    check_slug,
    public_task,
    public_tenant,
)

log = logging.getLogger("controlplane.service")

# (task type, terminal status) -> (tenant status we expect, tenant status we set)
TERMINAL = {
    ("deploy", "done"): ("provisioning", "active"),
    ("deploy", "failed"): ("provisioning", "failed"),
    ("update", "done"): ("updating", "active"),
    ("update", "failed"): ("updating", "failed"),
    ("destroy", "done"): ("destroying", "destroyed"),
    ("destroy", "failed"): ("destroying", "failed"),
}


def as_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise invalid_request("id must be a uuid") from None


def raise_for_unique(exc: UniqueViolation) -> None:
    name = exc.diag.constraint_name
    if name == "tenants_slug_key":
        raise tenant_already_exists() from None
    if name == "one_open_task":
        raise tenant_update_not_allowed() from None
    raise exc


class Service:
    def __init__(self, pool):
        self.pool = pool

    def create_tenant(self, slug: str, name: str) -> tuple[dict, dict]:
        slug = check_slug(slug)
        name = check_name(name)
        now = utcnow()
        tenant_id = uuid.uuid4()
        task_id = uuid.uuid4()
        with self.pool.connection() as conn:
            try:
                with conn.transaction():
                    tenant = repo.insert_tenant(
                        conn,
                        {
                            "id": tenant_id,
                            "slug": slug,
                            "name": name,
                            "status": "provisioning",
                            "version": 1,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    task = repo.insert_task(
                        conn,
                        {
                            "id": task_id,
                            "type": "deploy",
                            "tenant_id": tenant_id,
                            "status": "accepted",
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    repo.insert_outbox(
                        conn,
                        uuid.uuid4(),
                        task_id,
                        task_payload(task_id, "deploy", tenant_id),
                        now,
                    )
            except UniqueViolation as exc:
                raise_for_unique(exc)
        return public_tenant(tenant), public_task(task)

    def get_tenant(self, tenant_id) -> dict:
        tenant_id = as_uuid(tenant_id)
        with self.pool.connection() as conn:
            with conn.transaction():
                row = repo.get_tenant(conn, tenant_id)
        if row is None:
            raise tenant_not_found()
        return public_tenant(row)

    def list_tenants(self, status, limit, offset) -> dict:
        status = check_choice(status, TENANT_STATUSES, "tenant status")
        limit, offset = check_page(limit, offset)
        with self.pool.connection() as conn:
            with conn.transaction():
                rows = repo.list_tenants(conn, status, limit, offset)
        return {
            "items": [public_tenant(row) for row in rows],
            "limit": limit,
            "offset": offset,
        }

    def update_tenant(self, tenant_id, name: str, version: int) -> tuple[dict, dict]:
        tenant_id = as_uuid(tenant_id)
        name = check_name(name)
        if not isinstance(version, int):
            raise invalid_request("version is required")
        now = utcnow()
        task_id = uuid.uuid4()
        with self.pool.connection() as conn:
            try:
                with conn.transaction():
                    current = repo.lock_tenant(conn, tenant_id)
                    if current is None:
                        raise tenant_not_found()
                    # Version first, so two patches with the same version conflict
                    # instead of both passing a status check.
                    if current["version"] != version:
                        raise tenant_version_conflict()
                    if current["status"] != "active":
                        raise tenant_update_not_allowed()
                    tenant = repo.mark_updating(conn, tenant_id, name, now)
                    task = repo.insert_task(
                        conn,
                        {
                            "id": task_id,
                            "type": "update",
                            "tenant_id": tenant_id,
                            "status": "accepted",
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    repo.insert_outbox(
                        conn,
                        uuid.uuid4(),
                        task_id,
                        task_payload(task_id, "update", tenant_id),
                        now,
                    )
            except UniqueViolation as exc:
                raise_for_unique(exc)
        return public_tenant(tenant), public_task(task)

    def delete_tenant(self, tenant_id) -> tuple[dict, dict]:
        tenant_id = as_uuid(tenant_id)
        now = utcnow()
        task_id = uuid.uuid4()
        with self.pool.connection() as conn:
            try:
                with conn.transaction():
                    current = repo.lock_tenant(conn, tenant_id)
                    if current is None:
                        raise tenant_not_found()
                    if current["status"] not in ("active", "failed"):
                        raise tenant_update_not_allowed()
                    tenant = repo.mark_destroying(conn, tenant_id, now)
                    task = repo.insert_task(
                        conn,
                        {
                            "id": task_id,
                            "type": "destroy",
                            "tenant_id": tenant_id,
                            "status": "accepted",
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    repo.insert_outbox(
                        conn,
                        uuid.uuid4(),
                        task_id,
                        task_payload(task_id, "destroy", tenant_id),
                        now,
                    )
            except UniqueViolation as exc:
                raise_for_unique(exc)
        return public_tenant(tenant), public_task(task)

    def get_task(self, task_id) -> dict:
        task_id = as_uuid(task_id)
        with self.pool.connection() as conn:
            with conn.transaction():
                row = repo.get_task(conn, task_id)
        if row is None:
            raise task_not_found()
        return public_task(row)

    def list_tasks(self, tenant_id, status, limit, offset) -> dict:
        if tenant_id is not None and tenant_id != "":
            tenant_id = as_uuid(tenant_id)
        else:
            tenant_id = None
        status = check_choice(status, TASK_STATUSES, "task status")
        limit, offset = check_page(limit, offset)
        with self.pool.connection() as conn:
            with conn.transaction():
                rows = repo.list_tasks(conn, tenant_id, status, limit, offset)
        return {
            "items": [public_task(row) for row in rows],
            "limit": limit,
            "offset": offset,
        }

    def apply_progress(self, update_id, task_id, status: str) -> str:
        update_id = as_uuid(update_id)
        task_id = as_uuid(task_id)
        if status not in ("in_progress", "done", "failed"):
            raise invalid_request("status must be in_progress, done, or failed")
        now = utcnow()
        with self.pool.connection() as conn:
            with conn.transaction():
                claimed = repo.claim_progress(conn, update_id, task_id, status, now)
                if not claimed:
                    return "duplicate"
                task = repo.lock_task(conn, task_id)
                if task is None:
                    raise task_not_found()
                # done and failed stick. A late in_progress is recorded and ignored.
                if task["status"] in ("done", "failed"):
                    return "ignored"
                if status == "in_progress":
                    if task["status"] == "accepted":
                        repo.set_task_status(conn, task_id, "in_progress", now)
                        return "applied"
                    return "ignored"
                repo.set_task_status(conn, task_id, status, now)
                self._move_tenant(conn, task, status, now)
                return "applied"

    def _move_tenant(self, conn, task: dict, outcome: str, now) -> None:
        expected, nxt = TERMINAL[(task["type"], outcome)]
        tenant = repo.lock_tenant(conn, task["tenant_id"])
        if tenant is None or tenant["status"] != expected:
            log.warning(
                "task %s finished but tenant %s was %s, left it",
                task["id"],
                task["tenant_id"],
                None if tenant is None else tenant["status"],
            )
            return
        repo.set_tenant_status(conn, tenant["id"], nxt, now)
