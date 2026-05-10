"""FastAPI integration — drop-in /health endpoint backed by HealthCheck.

Usage:

    from fastapi import FastAPI
    from modafoca_healthcheck import HealthCheck
    from modafoca_healthcheck.fastapi import register_health_router

    app = FastAPI()
    health = HealthCheck(service="rayo", version="1.4.2", cache_ttl=30)
    health.add(...)
    register_health_router(app, health)

The endpoint is declared as a sync function (``def``, not ``async def``)
so FastAPI runs it on its threadpool — HealthCheck.run() blocks on
network I/O, and we don't want to stall the event loop.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .core import HealthCheck

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_health_router(
    app: "FastAPI",
    health: HealthCheck,
    path: str = "/health",
) -> None:
    """Add a GET <path> route that runs ``health`` and returns the standard JSON.

    Returns 200 when status is "ok", 503 when "degraded".
    Supports ``?fresh=true`` (or 1/yes) to bypass the cache for ad-hoc deep probes.
    """
    # Imported here so the lib can be imported without fastapi installed.
    from fastapi import Query
    from fastapi.responses import JSONResponse

    def health_endpoint(
        fresh: bool = Query(
            default=False,
            description="Bypass the cache and re-probe all dependencies.",
        ),
    ) -> JSONResponse:
        result = health.run(fresh=fresh)
        status_code = 200 if result["status"] == "ok" else 503
        return JSONResponse(content=result, status_code=status_code)

    app.add_api_route(
        path,
        health_endpoint,
        methods=["GET"],
        name="health",
        summary=f"Health check for {health.service}",
        response_description="Standard health JSON; 200 if ok, 503 if degraded.",
    )
