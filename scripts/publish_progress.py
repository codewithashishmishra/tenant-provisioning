"""Publish one progress message.

Handy when you want a stale update, for example in_progress after the task is already done.
"""

import argparse
import os
import uuid

from app.broker import connect, declare, publish_json
from app.config import load_settings
from app.messages import progress_payload


def parse_args(argv=None):
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Publish one provisioning progress message")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--status", required=True, choices=["in_progress", "done", "failed"])
    parser.add_argument("--update-id", default=None)
    parser.add_argument("--amqp-url", default=os.environ.get("AMQP_URL", settings.amqp_url))
    parser.add_argument(
        "--progress-queue",
        default=os.environ.get("PROGRESS_QUEUE", settings.progress_queue),
    )
    parser.add_argument(
        "--task-queue",
        default=os.environ.get("TASK_QUEUE", settings.task_queue),
    )
    args = parser.parse_args(argv)
    try:
        uuid.UUID(args.task_id)
    except ValueError:
        parser.error("--task-id must be a uuid")
    if args.update_id is None:
        args.update_id = str(uuid.uuid4())
    else:
        try:
            uuid.UUID(args.update_id)
        except ValueError:
            parser.error("--update-id must be a uuid")
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    connection = connect(args.amqp_url)
    try:
        channel = connection.channel()
        declare(channel, args.task_queue, args.progress_queue)
        payload = progress_payload(args.update_id, args.task_id, args.status)
        publish_json(channel, args.progress_queue, payload, args.update_id)
    finally:
        connection.close()
    print(f"published {args.status} update_id={args.update_id} task_id={args.task_id}")


if __name__ == "__main__":
    main()
