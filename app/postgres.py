from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row

from app.database import Database


def verified_dsn(value: str) -> str:
    url = urlsplit(value)
    if url.scheme not in {"postgres", "postgresql"} or not url.hostname:
        raise ValueError("QUORUM_DATABASE_URL must be a PostgreSQL URL")
    options = dict(parse_qsl(url.query))
    for name in ("sslmode", "sslcert", "sslkey", "sslrootcert", "options"):
        options.pop(name, None)
    if url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        options["sslmode"] = "verify-full"
        options["sslrootcert"] = "system"
    return urlunsplit(url._replace(query=urlencode(options)))


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, parameters=()):
        if isinstance(parameters, dict):
            sql = re.sub(r":([a-z_]+)", r"%(\1)s", sql)
        else:
            sql = sql.replace("?", "%s")
        return self.raw.execute(sql, parameters)

    def executescript(self, sql):
        # The inherited schema consists only of CREATE TABLE statements.
        for statement in sql.split(";"):
            if statement.strip():
                self.raw.execute(statement)


class PostgresDatabase(Database):
    def __init__(self, dsn: str, owner: str):
        self.dsn = verified_dsn(dsn)
        # Only a server-derived hash is interpolated as a schema identifier.
        self.schema = "quorum_" + hashlib.sha256(owner.encode()).hexdigest()[:24]

    @contextmanager
    def _connect(self):
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=15) as connection:
            connection.execute("SET statement_timeout='15s'")
            connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
            connection.execute(f'SET LOCAL search_path TO "{self.schema}"')
            yield Connection(connection)
