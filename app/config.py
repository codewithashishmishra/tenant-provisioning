import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    amqp_url: str
    task_queue: str
    progress_queue: str
    http_host: str
    http_port: int


def load_settings() -> Settings:
    # Defaults point at the compose ports when you run the process on the host.
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql://control:control@localhost:5433/control",
        ),
        amqp_url=os.environ.get("AMQP_URL", "amqp://guest:guest@localhost:5672/"),
        task_queue=os.environ.get("TASK_QUEUE", "provisioning.tasks"),
        progress_queue=os.environ.get("PROGRESS_QUEUE", "provisioning.progress"),
        http_host=os.environ.get("HTTP_HOST", "0.0.0.0"),
        http_port=int(os.environ.get("HTTP_PORT", "8000")),
    )
