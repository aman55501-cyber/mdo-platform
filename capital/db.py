"""Database access. One short-lived connection per call.

The web app connects read-only (the session is set read-only before any query). Jobs open a writer
explicitly. wb is not exposed over the REST API, so this talks to Postgres directly via DATABASE_URL
(use the Supabase *session* pooler string, which works from hosts without IPv6).
"""
from __future__ import annotations

from typing import Any

from .config import database_url


class DB:
    def __init__(self, url: str | None = None, *, readonly: bool = True) -> None:
        self._url = url
        self.readonly = readonly

    def _connect(self):
        import psycopg  # imported lazily so tests and tooling do not need a driver
        from psycopg.rows import dict_row

        conn = psycopg.connect(self._url or database_url(), row_factory=dict_row, autocommit=True, connect_timeout=10)
        conn.execute("set statement_timeout = 20000")
        if self.readonly:
            conn.execute("set default_transaction_read_only = on")
        return conn

    def query(self, sql: str, params: Any = None) -> list[dict]:
        with self._connect() as conn:
            return list(conn.execute(sql, params).fetchall())

    def execute(self, sql: str, params: Any = None) -> int:
        if self.readonly:
            raise PermissionError("this connection is read-only")
        with self._connect() as conn:
            return conn.execute(sql, params).rowcount
