"""Tests for the Supabase REST health check."""
from __future__ import annotations

import pytest
import responses

from modafoca_healthcheck.checks import supabase_check


URL = "https://abc123.supabase.co"
KEY = "fake-anon-key"


# --- factory validation -----------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    {"url": "", "key": KEY},
    {"url": URL, "key": ""},
])
def test_factory_rejects_missing_args(kwargs):
    with pytest.raises(ValueError):
        supabase_check(**kwargs)


def test_factory_rejects_bad_timeout():
    with pytest.raises(ValueError):
        supabase_check(url=URL, key=KEY, timeout=0)


# --- happy path -------------------------------------------------------------

@responses.activate
def test_200_is_ok():
    responses.add(responses.GET, f"{URL}/rest/v1/", status=200, json={})
    check = supabase_check(URL, KEY)
    assert check() == ("ok", None)


@responses.activate
def test_trailing_slash_in_url_is_normalized():
    responses.add(responses.GET, f"{URL}/rest/v1/", status=200, json={})
    check = supabase_check(URL + "///", KEY)
    assert check() == ("ok", None)


@responses.activate
def test_apikey_header_is_set():
    """Probe must include the apikey header — Supabase rejects without it."""
    responses.add(responses.GET, f"{URL}/rest/v1/", status=200, json={})
    check = supabase_check(URL, KEY)
    check()
    assert responses.calls[0].request.headers["apikey"] == KEY


# --- failure modes ----------------------------------------------------------

@responses.activate
def test_401_is_auth_failure():
    responses.add(responses.GET, f"{URL}/rest/v1/", status=401)
    status, error = supabase_check(URL, KEY)()
    assert status == "fail"
    assert "auth" in error.lower()
    assert "401" in error


@responses.activate
def test_403_is_auth_failure():
    responses.add(responses.GET, f"{URL}/rest/v1/", status=403)
    status, error = supabase_check(URL, KEY)()
    assert status == "fail"
    assert "auth" in error.lower()


@responses.activate
def test_504_paused_project_is_fail():
    """A paused Supabase project returns 504 from the REST root."""
    responses.add(responses.GET, f"{URL}/rest/v1/", status=504)
    status, error = supabase_check(URL, KEY)()
    assert status == "fail"
    assert "504" in error
