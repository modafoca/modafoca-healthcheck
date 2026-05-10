"""Tests for the Postgres health check.

psycopg isn't installed during CI (the `[postgres]` extra is optional).
We inject a fake `psycopg` module so the lazy `import psycopg` resolves
to our mock.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest

from modafoca_healthcheck.checks import postgres_check


DSN = "postgresql://app:secret@db.example/rayo"


def _make_fake_psycopg(*, fetchone_result=(1,), connect_raises=None,
                       execute_raises=None):
    """Build a fake `psycopg` module with controllable behavior."""
    fake = types.ModuleType("psycopg")

    class OperationalError(Exception):
        pass

    class FakeCursor:
        def execute(self, sql, params=None):
            if execute_raises is not None:
                raise execute_raises

        def fetchone(self):
            return fetchone_result

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def connect(dsn, connect_timeout=None):
        if connect_raises is not None:
            raise connect_raises
        return FakeConnection()

    fake.connect = connect
    fake.OperationalError = OperationalError
    return fake


# --- factory validation -----------------------------------------------------

def test_factory_rejects_empty_dsn():
    with pytest.raises(ValueError):
        postgres_check(dsn="")


def test_factory_rejects_bad_timeout():
    with pytest.raises(ValueError):
        postgres_check(dsn=DSN, timeout=0)


# --- extra missing path -----------------------------------------------------

def test_missing_extra_returns_clear_error():
    with patch.dict(sys.modules, {"psycopg": None}):
        status, error = postgres_check(DSN)()
    assert status == "fail"
    assert "postgres" in error
    assert "install" in error.lower()


# --- happy path -------------------------------------------------------------

def test_happy_path_returns_ok():
    fake = _make_fake_psycopg()
    with patch.dict(sys.modules, {"psycopg": fake}):
        assert postgres_check(DSN)() == ("ok", None)


# --- failure modes ----------------------------------------------------------

def test_unexpected_result_is_fail():
    fake = _make_fake_psycopg(fetchone_result=(42,))
    with patch.dict(sys.modules, {"psycopg": fake}):
        status, error = postgres_check(DSN)()
    assert status == "fail"
    assert "unexpected" in error.lower()


def test_operational_error_is_fail_with_reason():
    fake = _make_fake_psycopg()
    # Build the exception with our fake's class so the isinstance check works
    op_err = fake.OperationalError("could not connect: host unreachable")
    fake_with_err = _make_fake_psycopg(connect_raises=op_err)
    # Need the same OperationalError class on both — use the new one's class
    fake_with_err.OperationalError = type(op_err)
    with patch.dict(sys.modules, {"psycopg": fake_with_err}):
        status, error = postgres_check(DSN)()
    assert status == "fail"
    assert "host unreachable" in error


def test_generic_exception_is_fail():
    fake = _make_fake_psycopg(connect_raises=RuntimeError("boom"))
    with patch.dict(sys.modules, {"psycopg": fake}):
        status, error = postgres_check(DSN)()
    assert status == "fail"
    assert "RuntimeError" in error
