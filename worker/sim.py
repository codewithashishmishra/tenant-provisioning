import argparse
import logging
import os
import random
import time
import uuid

from app.broker import connect, declare, publish_json
from app.config import load_settings
from app.messages import PoisonMessage, parse_task, progress_payload

log = logging.getLogger("worker")


def outcome_for(fail_rate: float) -> str:
    # Dice roll for the simulator. Not used for anything secret.
    if random.random() < fail_rate:  # nosec B311
        return "failed"
    return "done"


def pause(min_ms: int, max_ms: int, sleep=time.sleep) -> None:
    if max_ms <= 0:
        return
    if max_ms == min_ms:
        sleep(min_ms / 1000)
        return
    sleep(random.randint(min_ms, max_ms) / 1000)  # nosec B311


def handle_task(
    channel,
    progress_queue: str,
    body: bytes,
    fail_rate: float,
    min_ms: int,
    max_ms: int,
    sleep=time.sleep,
) -> str:
    try:
        task = parse_task(body)
    except PoisonMessage:
        log.warning("dropping bad task message")
        return "dlq"

    task_id = task["id"]
    pause(min_ms, max_ms, sleep)
    update_id = uuid.uuid4()
    publish_json(
        channel,
        progress_queue,
        progress_payload(update_id, task_id, "in_progress"),
        str(update_id),
    )
    pause(min_ms, max_ms, sleep)
    outcome = outcome_for(fail_rate)
    update_id = uuid.uuid4()
    publish_json(
        channel,
        progress_queue,
        progress_payload(update_id, task_id, outcome),
        str(update_id),
    )
    log.info("task %s finished %s", task_id, outcome)
    return "ack"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Simulate tenant provisioning work")
    parser.add_argument(
        "--fail-rate",
        type=float,
        default=float(os.environ.get("FAIL_RATE", "0")),
    )
    parser.add_argument(
        "--min-delay-ms",
        type=int,
        default=int(os.environ.get("MIN_DELAY_MS", "200")),
    )
    parser.add_argument(
        "--max-delay-ms",
        type=int,
        default=int(os.environ.get("MAX_DELAY_MS", "800")),
    )
    parser.add_argument("--amqp-url", default=os.environ.get("AMQP_URL"))
    parser.add_argument("--task-queue", default=os.environ.get("TASK_QUEUE"))
    parser.add_argument("--progress-queue", default=os.environ.get("PROGRESS_QUEUE"))
    args = parser.parse_args(argv)
    settings = load_settings()
    if not args.amqp_url:
        args.amqp_url = settings.amqp_url
    if not args.task_queue:
        args.task_queue = settings.task_queue
    if not args.progress_queue:
        args.progress_queue = settings.progress_queue
    if not 0 <= args.fail_rate <= 1:
        parser.error("--fail-rate must be between 0 and 1")
    if args.min_delay_ms < 0 or args.max_delay_ms < args.min_delay_ms:
        parser.error("--max-delay-ms must be >= --min-delay-ms, and both >= 0")
    return args


def run(args) -> None:
    delay = 1
    while True:
        connection = None
        try:
            connection = connect(args.amqp_url)
            channel = connection.channel()
            declare(channel, args.task_queue, args.progress_queue)
            channel.basic_qos(prefetch_count=1)
            delay = 1
            log.info(
                "worker up fail_rate=%s delay=%s-%sms",
                args.fail_rate,
                args.min_delay_ms,
                args.max_delay_ms,
            )

            def on_message(ch, method, _properties, body):
                try:
                    result = handle_task(
                        ch,
                        args.progress_queue,
                        body,
                        args.fail_rate,
                        args.min_delay_ms,
                        args.max_delay_ms,
                    )
                except Exception:
                    log.exception("worker handler crashed")
                    time.sleep(1)
                    ch.basic_nack(method.delivery_tag, requeue=True)
                    return
                if result == "ack":
                    ch.basic_ack(method.delivery_tag)
                else:
                    ch.basic_nack(method.delivery_tag, requeue=False)

            channel.basic_consume(args.task_queue, on_message, auto_ack=False)
            channel.start_consuming()
        except Exception:
            log.exception("worker dropped, retrying in %ss", delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)
        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    log.warning("worker close failed", exc_info=True)


def main(argv=None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run(parse_args(argv))


if __name__ == "__main__":
    main()
