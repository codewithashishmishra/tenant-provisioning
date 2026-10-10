import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import AppError
from app.schemas import CreateTenantBody, PatchTenantBody
from app.service import Service

log = logging.getLogger("controlplane.api")


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def create_app(svc: Service) -> FastAPI:
    app = FastAPI(title="tenant control plane")
    app.state.svc = svc

    @app.exception_handler(AppError)
    def on_app_error(_request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    def on_bad_body(_request: Request, exc: RequestValidationError):
        message = "invalid request"
        errors = exc.errors()
        if errors:
            loc = [str(part) for part in errors[0].get("loc", []) if part != "body"]
            detail = errors[0].get("msg", "invalid request")
            message = f"{'.'.join(loc)}: {detail}" if loc else detail
        return JSONResponse(status_code=400, content=error_body("invalid_request", message))

    @app.exception_handler(Exception)
    def on_unexpected(_request: Request, exc: Exception):
        log.exception("request failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "internal error"),
        )

    @app.post("/tenants", status_code=201)
    def create_tenant(body: CreateTenantBody, request: Request):
        tenant, task = request.app.state.svc.create_tenant(body.slug, body.name)
        return {"tenant": tenant, "task": task}

    @app.get("/tenants")
    def list_tenants(
        request: Request,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ):
        return request.app.state.svc.list_tenants(status, limit, offset)

    @app.get("/tenants/{tenant_id}")
    def get_tenant(tenant_id: str, request: Request):
        return request.app.state.svc.get_tenant(tenant_id)

    @app.patch("/tenants/{tenant_id}")
    def patch_tenant(tenant_id: str, body: PatchTenantBody, request: Request):
        tenant, task = request.app.state.svc.update_tenant(tenant_id, body.name, body.version)
        return {"tenant": tenant, "task": task}

    @app.delete("/tenants/{tenant_id}", status_code=202)
    def delete_tenant(tenant_id: str, request: Request):
        tenant, task = request.app.state.svc.delete_tenant(tenant_id)
        return {"tenant": tenant, "task": task}

    @app.get("/tasks")
    def list_tasks(
        request: Request,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ):
        return request.app.state.svc.list_tasks(tenant_id, status, limit, offset)

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str, request: Request):
        return request.app.state.svc.get_task(task_id)

    return app
