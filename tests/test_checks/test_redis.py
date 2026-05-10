"""Tests for the Redis health check.

redis isn't installed during CI (the `[redis]` extra is optional). We
inject a fake `redis` module so the lazy `import redis` inside the
check resolves to our mock.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest

from modafoca_healthcheck.checks import redis_check


URL = "redis://default:password@redis.example:6379/0"


def _make_fake_redis(*, ping_returns=True, ping_raises=None,
                     from_url_raises=None):
    fake = types.ModuleType("redis")

    class RedisError(Exception):
        pass

    class ConnectionError(RedisError):
        pass

    class TimeoutError(RedisError):
        pass

    class AuthenticationError(RedisError):
        pass

    class FakeClient:
        def ping(self):
            if ping_raises is not None:
                raise ping_raises
            return ping_returns

    def from_url(url, **kwargs):
        if from_url_raises is not None:
            raise from_url_raises
        return FakeClient()

    fake.from_url = from_url
    fake.RedisError = RedisError
    fake.ConnectionError = ConnectionError
    fake.TimeoutError = TimeoutError
    fake.AuthenticationError = AuthenticationError
    return fake


# --- factory validation -----------------------------------------------------

def test_factory_rejects_empty_url():
    with pytest.raises(ValueError):
        redis_check(url="")


def test_factory_rejects_bad_timeout():
    with pytest.raises(ValueError):
        redis_check(url=URL, timeout=0)


# --- extra missing path -----------------------------------------------------

def test_missing_extra_returns_clear_error():
    with patch.dict(sys.modules, {"redis": None}):
        status, error = redis_check(URL)()
    assert status == "fail"
    assert "redis" in error
    assert "install" in error.lower()


# --- happy path -------------------------------------------------------------

def test_happy_path_returns_ok():
    fake = _make_fake_redis()
    with patch.dict(sys.modules, {"redis": fake}):
        assert redis_check(URL)() == ("ok", None)


# --- failure modes ----------------------------------------------------------

def test_falsy_ping_is_fail():
    fake = _make_fake_redis(ping_returns=False)
    with patch.dict(sys.modules, {"redis": fake}):
        status, error = redis_check(URL)()
    assert status == "fail"
    assert "PING" in error or "falsy" in error.lower()


def test_authentication_error_is_fail():
    fake = _make_fake_redis()
    fake_err = fake.AuthenticationError("WRONGPASS")
    fake_with_err = _make_fake_redis(ping_raises=fake_err)
    fake_with_err.AuthenticationError = type(fake_err)
    fake_with_err.RedisError = fake.RedisError  # keep parent chain consistent
    with patch.dict(sys.modules, {"redis": fake_with_err}):
        status, error = redis_check(URL)()
    assert status == "fail"
    assert "auth" in error.lower()


def test_connection_error_is_fail():
    fake = _make_fake_redis()
    conn_err = fake.ConnectionError("refused")
    fake_with_err = _make_fake_redis(ping_raises=conn_err)
    fake_with_err.ConnectionError = type(conn_err)
    fake_with_err.RedisError = fake.RedisError
    with patch.dict(sys.modules, {"redis": fake_with_err}):
        status, error = redis_check(URL)()
    assert status == "fail"
    assert "connection" in error.lower()


def test_timeout_error_is_fail():
    fake = _make_fake_redis()
    to_err = fake.TimeoutError("timed out")
    fake_with_err = _make_fake_redis(ping_raises=to_err)
    fake_with_err.TimeoutError = type(to_err)
    fake_with_err.RedisError = fake.RedisError
    with patch.dict(sys.modules, {"redis": fake_with_err}):
        status, error = redis_check(URL)()
    assert status == "fail"
    assert "timeout" in error.lower()
