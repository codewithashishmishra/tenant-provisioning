CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT tenants_slug_key UNIQUE (slug),
    CONSTRAINT tenants_status_check CHECK (
        status IN ('provisioning', 'active', 'updating', 'destroying', 'destroyed', 'failed')
    )
);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    type TEXT NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants (id),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT tasks_type_check CHECK (type IN ('deploy', 'update', 'destroy')),
    CONSTRAINT tasks_status_check CHECK (
        status IN ('accepted', 'in_progress', 'done', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS tasks_tenant_id_idx ON tasks (tenant_id);

-- The status guards are the rule. This index is the backstop for a race.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_task
    ON tasks (tenant_id)
    WHERE status IN ('accepted', 'in_progress');

CREATE TABLE IF NOT EXISTS outbox (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS outbox_unpublished_idx
    ON outbox (created_at)
    WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS progress_updates (
    update_id UUID PRIMARY KEY,
    task_id UUID NOT NULL,
    status TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
);
