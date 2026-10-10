# What this is

A small control plane that records tenants and the async work done on them.

A tenant is one customer environment. The API creates it, updates it, and deletes it. The real provisioning is not in this process. A worker simulates that and sends progress back.

A task is one unit of that work. Types are deploy, update, and destroy. The HTTP API does not let a client insert a task. A task is created only because a tenant call asked for a change.

Postgres keeps the rows, so a restart does not forget tenants. RabbitMQ is the queue between the API and the worker.

## Definitions

Tenant id. Generated here. The client does not choose it.

Slug. Short name, unique forever, including after the tenant is destroyed. Pattern is `^[a-z][-a-z0-9]{1,26}[a-z0-9]$`, which is 3 to 28 characters and fits a k8s namespace.

Name. Required. Blank is rejected. Leading and trailing spaces are stripped.

Tenant status. provisioning, active, updating, destroying, destroyed, failed.

Version. Integer on the tenant. Starts at 1. Increases when the tenant row changes. Patch must send the version it last read. That is the optimistic lock.

Task id. Generated here. The same id is on the message we publish.

Task status. accepted, then in_progress, then done or failed. done and failed stop there.

Open task. A task in accepted or in_progress. The state rules allow only one of those per tenant. A unique index backs that up if two requests race.

Outbox. A row written in the same transaction as the task. The publisher reads it only after commit, then sends it.

update_id. Id on a progress message, chosen by the worker. The consumer saves it. A second delivery of the same id does nothing.

## Requirements covered

- Create, list, get, patch, and delete tenants.
- List and get tasks. No create or update or delete for tasks over HTTP.
- Create sets the tenant to provisioning and writes a deploy task in accepted, then publishes that task after the commit.
- Patch is allowed only from active, and only with the current version. The tenant becomes updating and an update task is written.
- Delete is allowed only from active or failed. The tenant becomes destroying and a destroy task is written.
- The worker sends in_progress, then done or failed.
- deploy done moves the tenant to active. update done moves it to active. destroy done moves it to destroyed. Any failed outcome moves it to failed.
- Two creates with the same slug: one success, the other tenant_already_exists. Destroyed slugs still count.
- Two patches with the same version: one success, the other tenant_version_conflict.
- Wrong status on patch or delete: tenant_update_not_allowed.
- Unknown tenant: tenant_not_found. Unknown task: task_not_found.
- Errors are a JSON body with a code, and an HTTP status that matches.
- The same progress message twice is safe.
- in_progress after done does not move the task backwards.
- A bad message is dead-lettered. A database blip is retried. The consumer process stays up.
- Worker fail rate and delay are startup flags.
- One command boots Postgres, RabbitMQ, the API, and the worker. One command runs lint, format check, bandit, and tests.

## How I built it

1. Requirements. I wrote down the tenant states, the task states, which call is allowed from which state, and the error codes. I left out auth and anything else the spec does not ask for.

2. Design. Postgres for the rows, RabbitMQ for the two directions. Outbox so a message cannot leave before the commit. Version column so two patches cannot both win. Unique slug so two creates cannot both win.

3. API. `/tenants` and `/tasks`. Mutations return the tenant and the new task. Reads are list and get. Every error uses `error.code` and `error.message`.

4. Build. SQL in the repo module. State rules in the service module. Publisher and consumer are threads in the API process. The worker is its own module and its own container.

5. Test. Legal and illegal state moves, the slug race, the version race, a duplicate progress id, a stale in_progress, and a rolled back outbox write. The test command also runs the linter, the formatter check, and bandit.

6. Run. `docker compose up --build` starts the stack. The README has the curl examples, the failing worker, and the stale-message command.
