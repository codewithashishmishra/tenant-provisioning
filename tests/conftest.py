import os

# Keep pytest off the demo database and off the demo queues.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://control:control@localhost:5433/control_test",
)
os.environ.setdefault("TASK_QUEUE", "provisioning.tasks.tests")
os.environ.setdefault("PROGRESS_QUEUE", "provisioning.progress.tests")

import pytest

from app.config import load_settings
from app.db import apply_schema, make_pool


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def svc(settings):
    pool = make_pool(settings.database_url)
    with pool.connection() as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE progress_updates, outbox, tasks, tenants")
        conn.commit()
    from app.service import Service

    service = Service(pool)
    yield service
    pool.close()
