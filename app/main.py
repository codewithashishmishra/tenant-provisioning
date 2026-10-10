import logging
import threading

import uvicorn

from app.api import create_app
from app.config import load_settings
from app.consumer import run_consumer
from app.db import apply_schema, make_pool, wait_for_postgres
from app.publisher import run_publisher
from app.service import Service

log = logging.getLogger("controlplane")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = load_settings()
    wait_for_postgres(settings.database_url)
    pool = make_pool(settings.database_url)
    with pool.connection() as conn:
        apply_schema(conn)
        conn.commit()

    svc = Service(pool)
    app = create_app(svc)
    stop = threading.Event()
    threading.Thread(
        target=run_publisher,
        args=(settings, pool, stop),
        name="publisher",
        daemon=True,
    ).start()
    threading.Thread(
        target=run_consumer,
        args=(settings, svc, stop),
        name="consumer",
        daemon=True,
    ).start()
    log.info("listening on %s:%s", settings.http_host, settings.http_port)
    uvicorn.run(app, host=settings.http_host, port=settings.http_port, log_level="info")


if __name__ == "__main__":
    main()
