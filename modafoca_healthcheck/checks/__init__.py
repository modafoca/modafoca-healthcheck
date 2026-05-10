"""Built-in checks for common dependencies.

Each check is a *factory* that returns a parameterless callable conforming
to the CheckFn protocol — ``() -> (status, error)``. Pass it to
``HealthCheck.add(name, factory(...))``.

In v0.1.0 only ``http_check`` shipped. v0.2.0 adds five service-specific
checks. The SDK-backed ones (``pinecone``, ``postgres``, ``redis``) lazy-
import their library so this module imports cleanly even without the
optional extras installed — the ImportError surfaces at first probe.
"""
from .anthropic import anthropic_check
from .base import CheckFn
from .http import http_check
from .pinecone import pinecone_check
from .postgres import postgres_check
from .redis import redis_check
from .supabase import supabase_check

__all__ = [
    "CheckFn",
    "anthropic_check",
    "http_check",
    "pinecone_check",
    "postgres_check",
    "redis_check",
    "supabase_check",
]
