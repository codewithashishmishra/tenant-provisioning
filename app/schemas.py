import re

from pydantic import BaseModel, ConfigDict

from app.clock import to_iso
from app.errors import invalid_request

SLUG_RE = re.compile(r"^[a-z][-a-z0-9]{1,26}[a-z0-9]$")

TENANT_STATUSES = {
    "provisioning",
    "active",
    "updating",
    "destroying",
    "destroyed",
    "failed",
}
TASK_STATUSES = {"accepted", "in_progress", "done", "failed"}
TASK_TYPES = {"deploy", "update", "destroy"}


class CreateTenantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str
    name: str


class PatchTenantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: int


def check_slug(slug: str) -> str:
    if not isinstance(slug, str) or SLUG_RE.fullmatch(slug) is None:
        raise invalid_request("slug must match ^[a-z][-a-z0-9]{1,26}[a-z0-9]$")
    return slug


def check_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise invalid_request("name is required")
    cleaned = name.strip()
    if len(cleaned) > 200:
        raise invalid_request("name is too long")
    return cleaned


def check_page(limit: int | None, offset: int | None) -> tuple[int, int]:
    if limit is None:
        limit = 20
    if offset is None:
        offset = 0
    if limit < 1 or limit > 100:
        raise invalid_request("limit must be between 1 and 100")
    if offset < 0:
        raise invalid_request("offset must be 0 or more")
    return limit, offset


def check_choice(value: str | None, allowed: set[str], label: str) -> str | None:
    if value is None or value == "":
        return None
    if value not in allowed:
        raise invalid_request(f"unknown {label}")
    return value


def public_tenant(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "slug": row["slug"],
        "name": row["name"],
        "status": row["status"],
        "version": row["version"],
        "created_at": to_iso(row["created_at"]),
        "updated_at": to_iso(row["updated_at"]),
    }


def public_task(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "tenant_id": str(row["tenant_id"]),
        "status": row["status"],
        "created_at": to_iso(row["created_at"]),
        "updated_at": to_iso(row["updated_at"]),
    }
