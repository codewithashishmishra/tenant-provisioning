import logging

from app import repo
from app.broker import connect, declare, publish_json
from app.clock import utcnow

log = logging.getLogger("controlplane.publisher")


def publish_pending(conn, channel, queue: str, limit: int = 20) -> int:
    # Only committed outbox rows are visible here. A rolled back request has none.
    with conn.transaction():
        rows = repo.lock_unpublished(conn, limit)
        now = utcnow()
        for row in rows:
            payload = row["payload"]
            publish_json(channel, queue, payload, str(payload["id"]))
            repo.mark_published(conn, row["id"], now)
        return len(rows)


def run_publisher(settings, pool, stop) -> None:
    delay = 1
    while not stop.is_set():
        connection = None
        try:
            connection = connect(settings.amqp_url)
            channel = connection.channel()
            declare(channel, settings.task_queue, settings.progress_queue)
            delay = 1
            while not stop.is_set():
                with pool.connection() as conn:
                    count = publish_pending(conn, channel, settings.task_queue)
                if count == 0:
                    stop.wait(0.3)
        except Exception:
            log.exception("publisher dropped, retrying in %ss", delay)
            stop.wait(delay)
            delay = min(delay * 2, 30)
        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    log.warning("publisher close failed", exc_info=True)
