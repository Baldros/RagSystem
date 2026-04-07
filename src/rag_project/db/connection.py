from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql


class DatabaseConnectionError(RuntimeError):
    def __init__(self, message: str, *, missing_database: bool = False) -> None:
        super().__init__(message)
        self.missing_database = missing_database


class Database:
    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        try:
            with psycopg.connect(self._dsn, connect_timeout=self._connect_timeout_seconds) as conn:
                try:
                    register_vector(conn)
                except psycopg.ProgrammingError as exc:
                    if "vector type not found" not in str(exc).lower():
                        raise
                yield conn
        except psycopg.OperationalError as exc:
            raise DatabaseConnectionError(
                self._build_connection_error_message(exc),
                missing_database=self._is_missing_database_error(exc),
            ) from exc

    def execute_sql_file(self, path: Path) -> None:
        with path.open("r", encoding="utf-8") as handle:
            sql = handle.read()
        with self.connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(sql)
                except psycopg.Error as exc:
                    raise RuntimeError(self._build_sql_execution_error_message(exc)) from exc
            conn.commit()

    def ping(self) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.fetchone()

    def ensure_database_exists(self) -> bool:
        parsed = urlparse(self._dsn)
        database_name = parsed.path.lstrip("/")
        if not database_name:
            raise RuntimeError("Target PostgreSQL database name is empty in the DSN.")

        maintenance_dsn = self._maintenance_dsn(parsed)
        try:
            with psycopg.connect(maintenance_dsn, connect_timeout=self._connect_timeout_seconds) as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("select 1 from pg_database where datname = %s", (database_name,))
                    exists = cur.fetchone() is not None
                    if exists:
                        return False
                    cur.execute(sql.SQL("create database {}").format(sql.Identifier(database_name)))
                    return True
        except psycopg.OperationalError as exc:
            raise DatabaseConnectionError(
                self._build_connection_error_message(exc),
                missing_database=False,
            ) from exc

    def _build_connection_error_message(self, exc: Exception) -> str:
        parsed = urlparse(self._dsn)
        host = parsed.hostname or "unknown-host"
        port = parsed.port or 5432
        database_name = parsed.path.lstrip("/") or "unknown-db"
        user = parsed.username or "unknown-user"
        message = (
            "Could not connect to PostgreSQL.\n"
            f"Target: user={user} host={host} port={port} db={database_name}\n"
            "What to check:\n"
            "1. PostgreSQL is installed and the service is running.\n"
            "2. The database exists, or the configured user can create it automatically.\n"
            "3. The user/password in --db-dsn are correct.\n"
            "4. Port 5432 is open and reachable.\n"
            "5. If you only want to crawl and generate local artifacts for now, use --filesystem-only.\n"
            f"Original error: {exc}"
        )
        return message.encode("ascii", errors="replace").decode("ascii")

    @staticmethod
    def _build_sql_execution_error_message(exc: Exception) -> str:
        message = str(exc)
        lowered = message.lower()
        if 'extension "vector" is not available' in lowered or 'extensão "vector" não está disponível' in lowered:
            return (
                "PostgreSQL is running, but the pgvector extension is not installed on the server.\n"
                "What to check:\n"
                "1. Install pgvector for your PostgreSQL version.\n"
                "2. Restart PostgreSQL if the installer requires it.\n"
                "3. Run the build command again so the schema can execute `create extension if not exists vector`.\n"
                "4. If you only want local crawl artifacts for now, use --filesystem-only."
            )
        return message.encode("ascii", errors="replace").decode("ascii")

    @staticmethod
    def _maintenance_dsn(parsed_dsn) -> str:
        username = parsed_dsn.username or ""
        password = parsed_dsn.password or ""
        host = parsed_dsn.hostname or "localhost"
        port = parsed_dsn.port or 5432

        auth = username
        if password:
            auth = f"{auth}:{password}"
        if auth:
            auth = f"{auth}@"

        return f"postgresql://{auth}{host}:{port}/postgres"

    @staticmethod
    def _is_missing_database_error(exc: Exception) -> bool:
        error_text = str(exc).lower()
        return (
            "does not exist" in error_text
            or "nao existe" in error_text
            or "n?o existe" in error_text
            or "n\ufffdo existe" in error_text
        )
