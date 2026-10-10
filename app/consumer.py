import logging
import time

import psycopg

from app.broker import connect, declare
from app.errors import AppError
from app.messages import PoisonMessage, parse_progress

log = logging.getLogger("controlplane.consumer")


def handle_message(svc, body: bytes, attempts: int = 5, sleep=time.sleep) -> str:
    try:
        update_id, task_id, status = parse_progress(body)
    except PoisonMessage:
        log.warning("dropping bad progress message")
        return "dlq"

    for attempt in range(attempts):
        try:
            result = svc.apply_progress(update_id, task_id, status)
            log.info("progress %s on task %s -> %s", status, task_id, result)
            return "ack"
        except AppError as exc:
            log.warning("progress rejected: %s", exc.code)
            return "dlq"
        except psycopg.Error:
            log.exception("progress db error, attempt %s", attempt + 1)
            if attempt == attempts - 1:
                return "retry"
            sleep(0.2 * (2**attempt))
    return "retry"


def run_consumer(settings, svc, stop) -> None:
    delay = 1
    while not stop.is_set():
        connection = None
        try:
            connection = connect(settings.amqp_url)
            channel = connection.channel()
            declare(channel, settings.task_queue, settings.progress_queue)
            channel.basic_qos(prefetch_count=1)
            delay = 1

            def on_message(ch, method, _properties, body):
                try:
                    result = handle_message(svc, body)
                except Exception:
                    log.exception("consumer handler crashed")
                    time.sleep(1)
                    ch.basic_nack(method.delivery_tag, requeue=True)
                    return
                if result == "ack":
                    ch.basic_ack(method.delivery_tag)
                elif result == "dlq":
                    ch.basic_nack(method.delivery_tag, requeue=False)
                else:
                    time.sleep(1)
                    ch.basic_nack(method.delivery_tag, requeue=True)

            channel.basic_consume(settings.progress_queue, on_message, auto_ack=False)
            channel.start_consuming()
        except Exception:
            if stop.is_set():
                break
            log.exception("consumer dropped, retrying in %ss", delay)
            stop.wait(delay)
            delay = min(delay * 2, 30)
        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    log.warning("consumer close failed", exc_info=True)
