import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


def make_pool(database_url: str) -> ConnectionPool:
    pool = ConnectionPool(
        database_url,
        min_size=1,
        max_size=10,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    pool.open()
    pool.wait(timeout=10)
    return pool


def apply_schema(conn) -> None:
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    for chunk in text.split(";"):
        stmt = chunk.strip()
        if stmt:
            conn.execute(stmt)


def wait_for_postgres(database_url: str, attempts: int = 30) -> None:
    last = None
    for _ in range(attempts):
        try:
            with psycopg.connect(database_url, connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            return
        except psycopg.Error as exc:
            last = exc
            time.sleep(1)
    raise SystemExit(f"database not reachable: {last}")
