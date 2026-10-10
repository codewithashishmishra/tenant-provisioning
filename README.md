# Tenant provisioning control plane

When a tenant is created, the API saves it and a deploy task. A worker picks up that task, pretends to provision, and sends progress back. The API updates the tenant from those messages.

```
client -> API -> Postgres
                 outbox -> provisioning.tasks -> worker
                 worker -> provisioning.progress -> API -> Postgres
```

Postgres holds tenants, tasks, and the outbox. RabbitMQ has two queues. The API process serves HTTP, publishes tasks, and consumes progress. The worker is a separate process.

## Run

```bash
docker compose up --build
```

- API: http://localhost:8000
- Postgres: localhost:5433
- RabbitMQ: localhost:5672
- RabbitMQ UI: http://localhost:15672 (guest / guest)

Postgres is on 5433 so it does not use port 5432. The passwords in the compose file are only for this local stack.

Tests:

```bash
docker compose run --rm tests
```

That runs ruff, the format check, bandit, and pytest. Tests use the database `control_test`.

## What a create does

`POST /tenants` writes the tenant, a deploy task, and an outbox row in one transaction. After the commit, a loop publishes the outbox row to `provisioning.tasks`. If the process dies before the publish, the row is still there and the next boot sends it.

The worker waits, sends `in_progress`, waits again, then sends `done` or `failed`. Default fail rate is 0. Delay is a few hundred milliseconds so you can watch a full deploy.

Progress messages use `update_id`. The same id twice changes nothing. If the task is already `done` or `failed`, a late `in_progress` is ignored.

`version` starts at 1 and goes up when the tenant row changes. A patch must send the version you last read. Two patches with the same version cannot both succeed.

Slugs stay unique, including after a tenant is destroyed.

## Try it

Create:

```bash
curl -s -X POST http://localhost:8000/tenants \
  -H "content-type: application/json" \
  -d "{\"slug\":\"acme\",\"name\":\"Acme\"}"
```

The tenant starts as `provisioning`. The task starts as `accepted`. Then the worker moves the task to `in_progress` and `done`, and the tenant becomes `active`.

Check them:

```bash
curl -s http://localhost:8000/tenants/<tenant-id>
curl -s http://localhost:8000/tasks/<task-id>
curl -s "http://localhost:8000/tasks?tenant_id=<tenant-id>"
```

Patch (only while `active`). Use the version from the GET:

```bash
curl -s -X PATCH http://localhost:8000/tenants/<tenant-id> \
  -H "content-type: application/json" \
  -d "{\"name\":\"Acme Inc\",\"version\":2}"
```

Delete (only while `active` or `failed`):

```bash
curl -s -X DELETE http://localhost:8000/tenants/<tenant-id>
```

Slug must match `^[a-z][-a-z0-9]{1,26}[a-z0-9]$`.

Lists take `limit` and `offset`. Tenants can be filtered with `status`. Tasks can be filtered with `tenant_id` and `status`.

Errors look like this:

```json
{"error":{"code":"tenant_not_found","message":"tenant not found"}}
```

- `tenant_not_found`, `task_not_found`: 404
- `tenant_already_exists`, `tenant_update_not_allowed`, `tenant_version_conflict`: 409
- `invalid_request`: 400

## Queues

Task message, queue `provisioning.tasks`:

```json
{"id":"<task-id>","type":"deploy","tenant_id":"<tenant-id>","status":"accepted"}
```

`type` is `deploy`, `update`, or `destroy`.

Progress message, queue `provisioning.progress`:

```json
{"update_id":"<uuid>","task_id":"<task-id>","status":"in_progress"}
```

`status` is `in_progress`, `done`, or `failed`. A bad message goes to `provisioning.progress.dlq`. The consumer keeps running.

## Make a deploy fail

Stop the normal worker first so only one worker is consuming.

```bash
docker compose stop worker
docker compose run --rm worker python -m worker.sim --fail-rate 1 --min-delay-ms 200 --max-delay-ms 400
```

Create a tenant. The task should end `failed` and the tenant `failed`. Ctrl-C when you are done. `docker compose start worker` brings the normal worker back.

## Send a late progress message

After a task is `done`, this sends `in_progress` for it. The task should stay `done` and the tenant should stay `active`.

```bash
docker compose run --rm worker python -m scripts.publish_progress --task-id <task-id> --status in_progress
```

Or with rabbitmqadmin. Use a new `update_id` each time:

```bash
docker compose exec rabbitmq rabbitmqadmin publish \
  routing_key=provisioning.progress \
  payload='{"update_id":"11111111-1111-1111-1111-111111111111","task_id":"<task-id>","status":"in_progress"}'
```

Sending the same `update_id` again changes nothing.

## States

Tenant: create puts it in `provisioning`. Deploy done makes it `active`. Deploy failed makes it `failed`. Patch from `active` makes it `updating`, then `active` or `failed`. Delete from `active` or `failed` makes it `destroying`, then `destroyed` or `failed`.

Task: `accepted`, then `in_progress`, then `done` or `failed`. `done` and `failed` stay there.
