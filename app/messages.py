import json
import uuid


class PoisonMessage(Exception):
    pass


def task_payload(task_id, task_type, tenant_id, status="accepted") -> dict:
    return {
        "id": str(task_id),
        "type": task_type,
        "tenant_id": str(tenant_id),
        "status": status,
    }


def progress_payload(update_id, task_id, status) -> dict:
    return {
        "update_id": str(update_id),
        "task_id": str(task_id),
        "status": status,
    }


def dump(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def parse_progress(body: bytes) -> tuple[uuid.UUID, uuid.UUID, str]:
    try:
        data = json.loads(body)
        update_id = uuid.UUID(str(data["update_id"]))
        task_id = uuid.UUID(str(data["task_id"]))
        status = data["status"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PoisonMessage("bad progress message") from exc
    if status not in ("in_progress", "done", "failed"):
        raise PoisonMessage("bad progress status")
    return update_id, task_id, status


def parse_task(body: bytes) -> dict:
    try:
        data = json.loads(body)
        uuid.UUID(str(data["id"]))
        uuid.UUID(str(data["tenant_id"]))
        if data.get("type") not in ("deploy", "update", "destroy"):
            raise ValueError("type")
        if data.get("status") != "accepted":
            raise ValueError("status")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PoisonMessage("bad task message") from exc
    return data
