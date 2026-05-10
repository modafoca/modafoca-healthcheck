"""Tests for HealthCheck core: registration, parallel run, cache, sanitizer."""
from __future__ import annotations

import re
import time

import pytest

from modafoca_healthcheck import HealthCheck
from modafoca_healthcheck.core import _sanitize


# --- registration -----------------------------------------------------------

def test_init_requires_service():
    with pytest.raises(ValueError):
        HealthCheck(service="")


def test_init_rejects_negative_ttl():
    with pytest.raises(ValueError):
        HealthCheck(service="x", cache_ttl=-1)


def test_add_requires_name():
    h = HealthCheck(service="x")
    with pytest.raises(ValueError):
        h.add("", lambda: ("ok", None))


def test_add_rejects_duplicates():
    h = HealthCheck(service="x")
    h.add("dup", lambda: ("ok", None))
    with pytest.raises(ValueError):
        h.add("dup", lambda: ("ok", None))


def test_add_returns_self_for_chaining():
    h = HealthCheck(service="x")
    out = h.add("a", lambda: ("ok", None)).add("b", lambda: ("ok", None))
    assert out is h


# --- run() shape ------------------------------------------------------------

def test_run_with_no_checks_is_ok():
    h = HealthCheck(service="empty")
    payload = h.run()
    assert payload["status"] == "ok"
    assert payload["service"] == "empty"
    assert payload["version"] == "unknown"
    assert payload["checks"] == {}
    assert payload["failed"] == []
    assert isinstance(payload["duration_ms"], int)
    assert payload["duration_ms"] >= 0
    # ISO-8601 with Z
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", payload["timestamp"])


def test_run_includes_version():
    h = HealthCheck(service="x", version="1.2.3")
    assert h.run()["version"] == "1.2.3"


def test_run_one_ok():
    h = HealthCheck(service="x").add("a", lambda: ("ok", None))
    payload = h.run()
    assert payload["status"] == "ok"
    assert payload["checks"]["a"]["status"] == "ok"
    assert "error" not in payload["checks"]["a"]
    assert payload["failed"] == []


def test_run_one_fail_makes_top_level_degraded():
    h = HealthCheck(service="x").add("a", lambda: ("fail", "boom"))
    payload = h.run()
    assert payload["status"] == "degraded"
    assert payload["checks"]["a"]["status"] == "fail"
    assert payload["checks"]["a"]["error"] == "boom"
    assert payload["failed"] == ["a"]


def test_run_multiple_mixed():
    h = (
        HealthCheck(service="x")
        .add("a", lambda: ("ok", None))
        .add("b", lambda: ("fail", "down"))
        .add("c", lambda: ("ok", None))
    )
    payload = h.run()
    assert payload["status"] == "degraded"
    assert set(payload["checks"].keys()) == {"a", "b", "c"}
    assert sorted(payload["failed"]) == ["b"]


def test_run_all_fail():
    h = (
        HealthCheck(service="x")
        .add("a", lambda: ("fail", "x"))
        .add("b", lambda: ("fail", "y"))
    )
    payload = h.run()
    assert payload["status"] == "degraded"
    assert sorted(payload["failed"]) == ["a", "b"]


# --- exception capture ------------------------------------------------------

def test_check_that_raises_is_captured_as_fail():
    def explode():
        raise RuntimeError("oh no")

    h = HealthCheck(service="x").add("boom", explode)
    payload = h.run()
    assert payload["status"] == "degraded"
    assert payload["checks"]["boom"]["status"] == "fail"
    assert "RuntimeError" in payload["checks"]["boom"]["error"]
    assert payload["failed"] == ["boom"]


def test_check_returning_malformed_is_captured_as_fail():
    h = HealthCheck(service="x").add("bad", lambda: "not-a-tuple")  # type: ignore[arg-type]
    payload = h.run()
    assert payload["checks"]["bad"]["status"] == "fail"
    assert "malformed" in payload["checks"]["bad"]["error"]


def test_one_failing_check_does_not_abort_siblings():
    def explode():
        raise RuntimeError("x")

    h = (
        HealthCheck(service="x")
        .add("good", lambda: ("ok", None))
        .add("boom", explode)
        .add("also-good", lambda: ("ok", None))
    )
    payload = h.run()
    assert payload["checks"]["good"]["status"] == "ok"
    assert payload["checks"]["also-good"]["status"] == "ok"
    assert payload["checks"]["boom"]["status"] == "fail"


# --- parallelism ------------------------------------------------------------

def test_checks_run_in_parallel():
    """Three 0.3s sleepy checks should complete in roughly 0.3s, not 0.9s."""

    def slow_ok():
        time.sleep(0.3)
        return ("ok", None)

    h = (
        HealthCheck(service="x")
        .add("a", slow_ok)
        .add("b", slow_ok)
        .add("c", slow_ok)
    )
    started = time.monotonic()
    payload = h.run()
    elapsed = time.monotonic() - started

    assert payload["status"] == "ok"
    # Allow generous slack for CI variance — 0.7s would still prove parallelism
    # vs the 0.9s lower bound of serial execution.
    assert elapsed < 0.7, f"expected parallel (~0.3s), got {elapsed:.2f}s"


# --- cache ------------------------------------------------------------------

def test_cache_returns_same_payload_within_ttl():
    calls = {"n": 0}

    def counter():
        calls["n"] += 1
        return ("ok", None)

    h = HealthCheck(service="x", cache_ttl=10).add("c", counter)
    first = h.run()
    second = h.run()
    assert calls["n"] == 1  # second call hit cache
    assert second is first  # same object


def test_cache_bypassed_with_fresh_true():
    calls = {"n": 0}

    def counter():
        calls["n"] += 1
        return ("ok", None)

    h = HealthCheck(service="x", cache_ttl=10).add("c", counter)
    h.run()
    h.run(fresh=True)
    assert calls["n"] == 2


def test_cache_disabled_when_ttl_is_zero():
    calls = {"n": 0}

    def counter():
        calls["n"] += 1
        return ("ok", None)

    h = HealthCheck(service="x", cache_ttl=0).add("c", counter)
    h.run()
    h.run()
    assert calls["n"] == 2


def test_cache_expires():
    calls = {"n": 0}

    def counter():
        calls["n"] += 1
        return ("ok", None)

    h = HealthCheck(service="x", cache_ttl=0.05).add("c", counter)
    h.run()
    time.sleep(0.1)
    h.run()
    assert calls["n"] == 2


# --- sanitizer --------------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        "Authorization: Bearer abc123def456ghi789jkl012",
        "key=sk-ant-1234567890abcdef1234567890abcdef",
        "token sk-1234567890abcdefghijklmn",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_abcdefghijklmnopqrst123456789",
        "postgres://ian:s3cret@db.example.com/rayo",
        "redis://default:passwd@redis.example.com:6379/0",
        "JWT eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM",
    ],
)
def test_sanitize_redacts_credential_patterns(raw):
    cleaned = _sanitize(raw)
    assert "[REDACTED]" in cleaned
    assert "abc123def456" not in cleaned  # Bearer
    assert "1234567890abcdef" not in cleaned  # sk-ant
    assert "abcdefghijkl" not in cleaned  # ghp_ / github_pat_
    assert "s3cret" not in cleaned  # postgres pw
    assert "passwd" not in cleaned  # redis pw


def test_sanitize_truncates_long_messages():
    long = "x" * 500
    cleaned = _sanitize(long)
    assert cleaned is not None
    assert len(cleaned) <= 200
    assert cleaned.endswith("...")


def test_sanitize_handles_none_and_empty():
    assert _sanitize(None) is None
    assert _sanitize("") == ""


def test_sanitized_error_in_payload():
    def explode():
        raise RuntimeError("failed with token sk-ant-secretkey1234567890abcdef")

    h = HealthCheck(service="x").add("boom", explode)
    payload = h.run()
    assert "secretkey" not in payload["checks"]["boom"]["error"]
    assert "REDACTED" in payload["checks"]["boom"]["error"]
