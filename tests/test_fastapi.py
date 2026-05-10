"""Tests for the FastAPI router integration."""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modafoca_healthcheck import HealthCheck
from modafoca_healthcheck.fastapi import register_health_router


def make_app(health: HealthCheck, path: str = "/health") -> TestClient:
    app = FastAPI()
    register_health_router(app, health, path=path)
    return TestClient(app)


def test_returns_200_when_ok():
    h = HealthCheck(service="t", version="0.0.1").add("a", lambda: ("ok", None))
    client = make_app(h)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "t"
    assert body["version"] == "0.0.1"
    assert body["checks"]["a"]["status"] == "ok"
    assert body["failed"] == []


def test_returns_503_when_degraded():
    h = (
        HealthCheck(service="t")
        .add("a", lambda: ("ok", None))
        .add("b", lambda: ("fail", "down"))
    )
    client = make_app(h)
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["failed"] == ["b"]


def test_fresh_query_param_bypasses_cache():
    calls = {"n": 0}

    def counter():
        calls["n"] += 1
        return ("ok", None)

    h = HealthCheck(service="t", cache_ttl=10).add("c", counter)
    client = make_app(h)
    client.get("/health")
    assert calls["n"] == 1
    client.get("/health")  # cache hit
    assert calls["n"] == 1
    client.get("/health?fresh=1")  # bypass
    assert calls["n"] == 2
    client.get("/health?fresh=true")  # alias
    assert calls["n"] == 3
    client.get("/health?fresh=no")  # falsy → cache hit
    assert calls["n"] == 3


def test_custom_path():
    h = HealthCheck(service="t").add("a", lambda: ("ok", None))
    client = make_app(h, path="/_status")
    assert client.get("/_status").status_code == 200
    assert client.get("/health").status_code == 404


def test_response_is_json_with_correct_keys():
    h = HealthCheck(service="t", version="9.9.9").add("a", lambda: ("ok", None))
    client = make_app(h)
    body = client.get("/health").json()
    expected = {"status", "service", "version", "timestamp", "duration_ms", "checks", "failed"}
    assert set(body.keys()) == expected
