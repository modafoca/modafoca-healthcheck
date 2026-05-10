"""Postgres health check — connect and SELECT 1.

Requires the ``[postgres]`` extra (psycopg 3). Connection is opened
with a connect_timeout so a downed DB doesn't stall the /health endpoint
for the libpq default (5+ minutes on some platforms).

The query is the canonical ``SELECT 1`` — it doesn't touch any
application tables, doesn't take any locks, and fits in a single TCP
round-trip on a warm connection.
"""
from __future__ import annotations

from typing import Optional

from .base import CheckFn


def postgres_check(dsn: str, timeout: float = 5.0) -> CheckFn:
    """Return a check that opens a fresh Postgres connection and selects 1.

    Args:
        dsn: full Postgres connection string. ``postgresql://user:pass@host:port/db``.
        timeout: connect timeout in seconds. Default 5.

    Returns:
        A no-arg callable returning (status, error).
    """
    if not dsn:
        raise ValueError("dsn is required")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    def check() -> tuple[str, Optional[str]]:
        try:
            import psycopg  # type: ignore[import-not-found]
        except ImportError:
            return (
                "fail",
                "postgres extra not installed; "
                "pip install 'modafoca-healthcheck[postgres]'",
            )

        try:
            # Cast to int — libpq's connect_timeout is integer seconds.
            with psycopg.connect(dsn, connect_timeout=max(int(timeout), 1)) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    row = cur.fetchone()
                    if not row or row[0] != 1:
                        return ("fail", "SELECT 1 returned unexpected result")
        except psycopg.OperationalError as e:
            return ("fail", str(e)[:120].strip())
        except Exception as e:
            return ("fail", type(e).__name__)
        return ("ok", None)

    return check
