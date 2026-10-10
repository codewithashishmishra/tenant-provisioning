import pika

from app.messages import dump


def amqp_params(url: str) -> pika.URLParameters:
    params = pika.URLParameters(url)
    params.heartbeat = 30
    params.blocked_connection_timeout = 30
    params.connection_attempts = 1
    params.retry_delay = 0
    return params


def connect(url: str) -> pika.BlockingConnection:
    return pika.BlockingConnection(amqp_params(url))


def _queue(channel, name: str) -> None:
    channel.queue_declare(queue=name + ".dlq", durable=True)
    channel.queue_declare(
        queue=name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": name + ".dlq",
        },
    )


def declare(channel, task_queue: str, progress_queue: str) -> None:
    _queue(channel, task_queue)
    _queue(channel, progress_queue)


def publish_json(channel, queue: str, payload: dict, message_id: str) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=dump(payload),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
            message_id=message_id,
        ),
    )
