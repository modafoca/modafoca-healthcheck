"""Tests for the generic http_check factory."""
from __future__ import annotations

import pytest
import responses

from modafoca_healthcheck.checks import http_check


def test_construction_validates_url():
    with pytest.raises(ValueError):
        http_check(url="")


def test_construction_validates_timeout():
    with pytest.raises(ValueError):
        http_check(url="https://x.example", timeout=0)


@responses.activate
def test_200_is_ok():
    responses.add(responses.GET, "https://api.example/health", status=200)
    check = http_check("https://api.example/health")
    assert check() == ("ok", None)


@responses.activate
def test_302_followed_to_200_is_ok():
    responses.add(
        responses.GET,
        "https://api.example/",
        status=302,
        headers={"Location": "https://api.example/login"},
    )
    responses.add(responses.GET, "https://api.example/login", status=200)
    check = http_check("https://api.example/")
    assert check() == ("ok", None)


@responses.activate
def test_404_is_fail_with_status():
    responses.add(responses.GET, "https://api.example/health", status=404)
    check = http_check("https://api.example/health")
    status, error = check()
    assert status == "fail"
    assert "404" in error


@responses.activate
def test_500_is_fail():
    responses.add(responses.GET, "https://api.example/health", status=500)
    check = http_check("https://api.example/health")
    status, error = check()
    assert status == "fail"
    assert "500" in error


@responses.activate
def test_expected_status_codes_strict_match():
    responses.add(responses.GET, "https://api.example/teapot", status=418)
    check = http_check("https://api.example/teapot", expected_status_codes=[418])
    assert check() == ("ok", None)


@responses.activate
def test_expected_status_codes_rejects_others():
    responses.add(responses.GET, "https://api.example/teapot", status=200)
    check = http_check("https://api.example/teapot", expected_status_codes=[418])
    status, error = check()
    assert status == "fail"
    assert "200" in error
    assert "418" in error  # error mentions expected


def test_timeout_is_captured():
    """Use a non-routable address to provoke a real timeout quickly.

    10.255.255.1 is reserved for documentation and almost always blackholes.
    A 0.5s timeout means the test takes ~0.5s.
    """
    check = http_check("http://10.255.255.1/", timeout=0.5)
    status, error = check()
    assert status == "fail"
    # Either timeout or connection error depending on platform — both are
    # "the network ate the request" which is what we want to catch.
    assert any(s in error.lower() for s in ("timeout", "connection"))


@responses.activate
def test_method_can_be_overridden():
    responses.add(responses.HEAD, "https://api.example/", status=200)
    check = http_check("https://api.example/", method="HEAD")
    assert check() == ("ok", None)
