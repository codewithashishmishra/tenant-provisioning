import json
import uuid

import psycopg
import pytest

from app import repo
from app.broker import connect, declare
from app.consumer import handle_message
from app.messages import dump, progress_payload, task_payload
from app.publisher import publish_pending
from tests.support import fresh_slug


def _counts(svc) -> tuple[int, int, int]:
    with svc.pool.connection() as conn:
        with conn.transaction():
            tenants = conn.execute("SELECT count(*) AS n FROM tenants").fetchone()["n"]
            tasks = conn.execute("SELECT count(*) AS n FROM tasks").fetchone()["n"]
            outbox = conn.execute("SELECT count(*) AS n FROM outbox").fetchone()["n"]
    return tenants, tasks, outbox


def test_duplicate_progress_is_a_no_op(svc):
    _tenant, task = svc.create_tenant(fresh_slug(), "Acme")
    update_id = uuid.uuid4()
    assert svc.apply_progress(update_id, task["id"], "in_progress") == "applied"
    assert svc.apply_progress(update_id, task["id"], "in_progress") == "duplicate"
    assert svc.get_task(task["id"])["status"] == "in_progress"


def test_late_in_progress_does_not_regress(svc):
    tenant, task = svc.create_tenant(fresh_slug(), "Acme")
    svc.apply_progress(uuid.uuid4(), task["id"], "done")
    assert svc.apply_progress(uuid.uuid4(), task["id"], "in_progress") == "ignored"
    assert svc.get_task(task["id"])["status"] == "done"
    assert svc.get_tenant(tenant["id"])["status"] == "active"
    # a second terminal result does not bump the tenant again
    version = svc.get_tenant(tenant["id"])["version"]
    assert svc.apply_progress(uuid.uuid4(), task["id"], "failed") == "ignored"
    assert svc.get_tenant(tenant["id"])["version"] == version
    assert svc.get_tenant(tenant["id"])["status"] == "active"


def test_second_in_progress_does_not_move_the_task(svc):
    _tenant, task = svc.create_tenant(fresh_slug(), "Acme")
    svc.apply_progress(uuid.uuid4(), task["id"], "in_progress")
    assert svc.apply_progress(uuid.uuid4(), task["id"], "in_progress") == "ignored"
    assert svc.get_task(task["id"])["status"] == "in_progress"


def test_missing_task_is_rejected(svc):
    from app.errors import AppError

    with pytest.raises(AppError) as caught:
        svc.apply_progress(uuid.uuid4(), uuid.uuid4(), "done")
    assert caught.value.code == "task_not_found"


def test_failed_outbox_insert_keeps_nothing(svc, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("outbox write failed")

    monkeypatch.setattr(repo, "insert_outbox", boom)
    with pytest.raises(RuntimeError):
        svc.create_tenant(fresh_slug(), "Acme")
    assert _counts(svc) == (0, 0, 0)


def test_publish_pending_marks_the_row(svc):
    _tenant, task = svc.create_tenant(fresh_slug(), "Acme")

    class Sink:
        def __init__(self):
            self.bodies = []

        def basic_publish(self, exchange, routing_key, body, properties=None):
            self.bodies.append(json.loads(body))

    sink = Sink()
    with svc.pool.connection() as conn:
        sent = publish_pending(conn, sink, "provisioning.tasks.tests")
    assert sent == 1
    assert sink.bodies[0]["id"] == task["id"]
    assert sink.bodies[0]["status"] == "accepted"
    with svc.pool.connection() as conn:
        sent_again = publish_pending(conn, sink, "provisioning.tasks.tests")
    assert sent_again == 0


def test_publish_pending_reaches_rabbit(svc, settings):
    _tenant, task = svc.create_tenant(fresh_slug(), "Acme")
    connection = connect(settings.amqp_url)
    try:
        channel = connection.channel()
        declare(channel, settings.task_queue, settings.progress_queue)
        channel.queue_purge(settings.task_queue)
        with svc.pool.connection() as conn:
            assert publish_pending(conn, channel, settings.task_queue) == 1
        _method, _props, body = channel.basic_get(settings.task_queue, auto_ack=True)
        assert json.loads(body)["id"] == task["id"]
        assert json.loads(body)["tenant_id"] == task["tenant_id"]
    finally:
        connection.close()


def test_poison_progress_is_dead_lettered(svc):
    assert handle_message(svc, b"nope") == "dlq"
    assert handle_message(svc, b'{"update_id": "x"}') == "dlq"


def test_db_blip_is_retried(svc):
    tenant, task = svc.create_tenant(fresh_slug(), "Acme")
    body = dump(progress_payload(uuid.uuid4(), task["id"], "in_progress"))

    class Flaky:
        def __init__(self, real):
            self.real = real
            self.calls = 0

        def apply_progress(self, *args):
            self.calls += 1
            if self.calls == 1:
                raise psycopg.OperationalError("db down")
            return self.real.apply_progress(*args)

    flaky = Flaky(svc)
    assert handle_message(flaky, body, sleep=lambda _s: None) == "ack"
    assert flaky.calls == 2
    assert svc.get_task(task["id"])["status"] == "in_progress"
    assert svc.get_tenant(tenant["id"])["status"] == "provisioning"
    assert svc.get_tenant(tenant["id"])["version"] == 1


def test_db_blip_that_sticks_is_requeued():
    body = dump(progress_payload(uuid.uuid4(), uuid.uuid4(), "done"))

    class Down:
        def apply_progress(self, *_args):
            raise psycopg.OperationalError("still down")

    assert handle_message(Down(), body, attempts=3, sleep=lambda _s: None) == "retry"


def test_task_payload_shape():
    payload = task_payload(uuid.uuid4(), "deploy", uuid.uuid4())
    assert set(payload) == {"id", "type", "tenant_id", "status"}
    assert payload["status"] == "accepted"
