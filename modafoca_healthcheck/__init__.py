"""modafoca-healthcheck — standardized /health for MODAFOCA services.

Public API:

    from modafoca_healthcheck import HealthCheck
    from modafoca_healthcheck.checks import http_check
    from modafoca_healthcheck.fastapi import register_health_router

Build a HealthCheck per service, register dependency probes, attach to a
web framework. Mission Control's pulse pings the resulting /health and
classifies the dot color from the HTTP status (200 = green, 503 = red).
"""
from .core import HealthCheck

__version__ = "0.2.0"
__all__ = ["HealthCheck", "__version__"]
