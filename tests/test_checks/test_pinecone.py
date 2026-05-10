"""Tests for the Pinecone health check.

Pinecone's SDK isn't installed during CI (the `[pinecone]` extra is
optional). We inject a fake `pinecone` module into sys.modules so the
lazy `from pinecone import Pinecone` inside the check resolves to our
mock — without depending on the real SDK.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest

from modafoca_healthcheck.checks import pinecone_check


def _make_fake_pinecone(stats_or_exc=None):
    """Build a fake `pinecone` module.

    `stats_or_exc` controls Index().describe_index_stats():
      * None → returns dict (happy path)
      * Exception class → raised
      * Exception instance → raised
    """
    fake = types.ModuleType("pinecone")

    class FakeIndex:
        def describe_index_stats(self):
            if stats_or_exc is None:
                return {"dimension": 1536, "total_vector_count": 100}
            if isinstance(stats_or_exc, type) and issubclass(stats_or_exc, BaseException):
                raise stats_or_exc("boom")
            if isinstance(stats_or_exc, BaseException):
                raise stats_or_exc
            return stats_or_exc

    class FakePinecone:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def Index(self, name):  # noqa: N802 (matches SDK)
            return FakeIndex()

    fake.Pinecone = FakePinecone
    return fake


# --- factory validation -----------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    {"api_key": "", "index": "x"},
    {"api_key": "k", "index": ""},
])
def test_factory_rejects_missing_args(kwargs):
    with pytest.raises(ValueError):
        pinecone_check(**kwargs)


def test_factory_rejects_bad_timeout():
    with pytest.raises(ValueError):
        pinecone_check(api_key="k", index="i", timeout=0)


# --- extra missing path -----------------------------------------------------

def test_missing_extra_returns_clear_error():
    # Ensure pinecone is NOT in sys.modules so the import fails.
    with patch.dict(sys.modules, {"pinecone": None}):
        # `None` in sys.modules triggers ImportError on `from pinecone import X`
        check = pinecone_check(api_key="k", index="i")
        status, error = check()
    assert status == "fail"
    assert "pinecone" in error
    assert "install" in error.lower()


# --- happy path -------------------------------------------------------------

def test_happy_path_returns_ok():
    fake = _make_fake_pinecone()
    with patch.dict(sys.modules, {"pinecone": fake}):
        check = pinecone_check(api_key="k", index="my-index")
        assert check() == ("ok", None)


# --- failure modes ----------------------------------------------------------

def test_sdk_exception_is_captured_as_fail():
    class NotFoundException(Exception):
        pass

    fake = _make_fake_pinecone(NotFoundException)
    with patch.dict(sys.modules, {"pinecone": fake}):
        status, error = pinecone_check(api_key="k", index="missing")()
    assert status == "fail"
    assert "NotFoundException" in error


def test_generic_exception_is_captured_as_fail():
    fake = _make_fake_pinecone(RuntimeError("connection failed"))
    with patch.dict(sys.modules, {"pinecone": fake}):
        status, error = pinecone_check(api_key="k", index="any")()
    assert status == "fail"
    assert "RuntimeError" in error
