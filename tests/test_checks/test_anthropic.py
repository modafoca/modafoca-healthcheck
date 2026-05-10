"""Tests for the Anthropic API health check."""
from __future__ import annotations

import pytest
import responses

from modafoca_healthcheck.checks import anthropic_check


KEY = "sk-ant-fakekey1234567890abcdef"
URL = "https://api.anthropic.com/v1/models"


# --- factory validation -----------------------------------------------------

def test_factory_rejects_empty_key():
    with pytest.raises(ValueError):
        anthropic_check(api_key="")


def test_factory_rejects_bad_timeout():
    with pytest.raises(ValueError):
        anthropic_check(api_key=KEY, timeout=0)


# --- happy path -------------------------------------------------------------

@responses.activate
def test_200_is_ok():
    responses.add(responses.GET, URL, status=200, json={"data": []})
    check = anthropic_check(KEY)
    assert check() == ("ok", None)


@responses.activate
def test_required_headers_are_set():
    """x-api-key and anthropic-version are required by the API."""
    responses.add(responses.GET, URL, status=200, json={"data": []})
    anthropic_check(KEY)()
    headers = responses.calls[0].request.headers
    assert headers["x-api-key"] == KEY
    assert headers["anthropic-version"] == "2023-06-01"


# --- failure modes ----------------------------------------------------------

@responses.activate
def test_401_is_auth_failure():
    responses.add(responses.GET, URL, status=401)
    status, error = anthropic_check(KEY)()
    assert status == "fail"
    assert "auth" in error.lower()
    assert "401" in error


@responses.activate
def test_429_is_rate_limited():
    responses.add(responses.GET, URL, status=429)
    status, error = anthropic_check(KEY)()
    assert status == "fail"
    assert "rate" in error.lower()


@responses.activate
def test_500_is_fail_with_status():
    responses.add(responses.GET, URL, status=500)
    status, error = anthropic_check(KEY)()
    assert status == "fail"
    assert "500" in error


@responses.activate
def test_custom_base_url_is_used():
    """Useful for staging or air-gapped fixture servers."""
    base = "https://api-test.example.com"
    responses.add(responses.GET, f"{base}/v1/models", status=200, json={"data": []})
    check = anthropic_check(KEY, base_url=base)
    assert check() == ("ok", None)
