from psycopg.types.json import Jsonb

# Callers own the transaction. These functions only run SQL.


def insert_tenant(conn, row: dict) -> dict:
    return conn.execute(
        """
        INSERT INTO tenants (id, slug, name, status, version, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, slug, name, status, version, created_at, updated_at
        """,
        (
            row["id"],
            row["slug"],
            row["name"],
            row["status"],
            row["version"],
            row["created_at"],
            row["updated_at"],
        ),
    ).fetchone()


def insert_task(conn, row: dict) -> dict:
    return conn.execute(
        """
        INSERT INTO tasks (id, type, tenant_id, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, type, tenant_id, status, created_at, updated_at
        """,
        (
            row["id"],
            row["type"],
            row["tenant_id"],
            row["status"],
            row["created_at"],
            row["updated_at"],
        ),
    ).fetchone()


def insert_outbox(conn, outbox_id, task_id, payload: dict, now) -> None:
    conn.execute(
        """
        INSERT INTO outbox (id, task_id, payload, created_at, published_at)
        VALUES (%s, %s, %s, %s, NULL)
        """,
        (outbox_id, task_id, Jsonb(payload), now),
    )


def lock_tenant(conn, tenant_id) -> dict | None:
    return conn.execute(
        """
        SELECT id, slug, name, status, version, created_at, updated_at
        FROM tenants
        WHERE id = %s
        FOR UPDATE
        """,
        (tenant_id,),
    ).fetchone()


def get_tenant(conn, tenant_id) -> dict | None:
    return conn.execute(
        """
        SELECT id, slug, name, status, version, created_at, updated_at
        FROM tenants
        WHERE id = %s
        """,
        (tenant_id,),
    ).fetchone()


def list_tenants(conn, status, limit: int, offset: int) -> list[dict]:
    if status is None:
        return conn.execute(
            """
            SELECT id, slug, name, status, version, created_at, updated_at
            FROM tenants
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ).fetchall()
    return conn.execute(
        """
        SELECT id, slug, name, status, version, created_at, updated_at
        FROM tenants
        WHERE status = %s
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (status, limit, offset),
    ).fetchall()


def mark_updating(conn, tenant_id, name: str, now) -> dict:
    return conn.execute(
        """
        UPDATE tenants
        SET name = %s,
            status = 'updating',
            version = version + 1,
            updated_at = %s
        WHERE id = %s
        RETURNING id, slug, name, status, version, created_at, updated_at
        """,
        (name, now, tenant_id),
    ).fetchone()


def mark_destroying(conn, tenant_id, now) -> dict:
    return conn.execute(
        """
        UPDATE tenants
        SET status = 'destroying',
            version = version + 1,
            updated_at = %s
        WHERE id = %s
        RETURNING id, slug, name, status, version, created_at, updated_at
        """,
        (now, tenant_id),
    ).fetchone()


def set_tenant_status(conn, tenant_id, status: str, now) -> dict | None:
    return conn.execute(
        """
        UPDATE tenants
        SET status = %s,
            version = version + 1,
            updated_at = %s
        WHERE id = %s
        RETURNING id, slug, name, status, version, created_at, updated_at
        """,
        (status, now, tenant_id),
    ).fetchone()


def lock_task(conn, task_id) -> dict | None:
    return conn.execute(
        """
        SELECT id, type, tenant_id, status, created_at, updated_at
        FROM tasks
        WHERE id = %s
        FOR UPDATE
        """,
        (task_id,),
    ).fetchone()


def get_task(conn, task_id) -> dict | None:
    return conn.execute(
        """
        SELECT id, type, tenant_id, status, created_at, updated_at
        FROM tasks
        WHERE id = %s
        """,
        (task_id,),
    ).fetchone()


def list_tasks(conn, tenant_id, status, limit: int, offset: int) -> list[dict]:
    if tenant_id is not None and status is not None:
        return conn.execute(
            """
            SELECT id, type, tenant_id, status, created_at, updated_at
            FROM tasks
            WHERE tenant_id = %s AND status = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (tenant_id, status, limit, offset),
        ).fetchall()
    if tenant_id is not None:
        return conn.execute(
            """
            SELECT id, type, tenant_id, status, created_at, updated_at
            FROM tasks
            WHERE tenant_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (tenant_id, limit, offset),
        ).fetchall()
    if status is not None:
        return conn.execute(
            """
            SELECT id, type, tenant_id, status, created_at, updated_at
            FROM tasks
            WHERE status = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (status, limit, offset),
        ).fetchall()
    return conn.execute(
        """
        SELECT id, type, tenant_id, status, created_at, updated_at
        FROM tasks
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    ).fetchall()


def set_task_status(conn, task_id, status: str, now) -> None:
    conn.execute(
        """
        UPDATE tasks
        SET status = %s, updated_at = %s
        WHERE id = %s
        """,
        (status, now, task_id),
    )


def claim_progress(conn, update_id, task_id, status: str, now) -> bool:
    row = conn.execute(
        """
        INSERT INTO progress_updates (update_id, task_id, status, applied_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (update_id) DO NOTHING
        RETURNING update_id
        """,
        (update_id, task_id, status, now),
    ).fetchone()
    return row is not None


def lock_unpublished(conn, limit: int) -> list[dict]:
    return conn.execute(
        """
        SELECT id, task_id, payload
        FROM outbox
        WHERE published_at IS NULL
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT %s
        """,
        (limit,),
    ).fetchall()


def mark_published(conn, outbox_id, now) -> None:
    conn.execute(
        "UPDATE outbox SET published_at = %s WHERE id = %s",
        (now, outbox_id),
    )
